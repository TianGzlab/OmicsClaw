#!/usr/bin/env python3
"""OmicsClaw — Multi-Omics Analysis Skills Runner.

Usage:
    python omicsclaw.py list
    python omicsclaw.py run <skill> --demo
    python omicsclaw.py run <skill> --input <data> --output <dir>
    python omicsclaw.py run spatial-pipeline --input <h5ad> --output <dir>
    python omicsclaw.py upload --input <data> --data-type <type>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

OMICSCLAW_DIR = Path(__file__).resolve().parent
SKILLS_DIR = OMICSCLAW_DIR / "skills"
EXAMPLES_DIR = OMICSCLAW_DIR / "examples"
DEFAULT_OUTPUT_ROOT = OMICSCLAW_DIR / "output"
SESSIONS_DIR = OMICSCLAW_DIR / "sessions"
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Terminal colours
# ---------------------------------------------------------------------------

_COLOUR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
BOLD = "\033[1m" if _COLOUR else ""
GREEN = "\033[32m" if _COLOUR else ""
YELLOW = "\033[33m" if _COLOUR else ""
RED = "\033[31m" if _COLOUR else ""
CYAN = "\033[36m" if _COLOUR else ""
RESET = "\033[0m" if _COLOUR else ""

# ---------------------------------------------------------------------------
# Skills and Domain metadata registry
# ---------------------------------------------------------------------------

if str(OMICSCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(OMICSCLAW_DIR))

from omicsclaw.core.registry import registry
registry.load_all()
SKILLS = registry.skills
DOMAINS = registry.domains

SPATIAL_PIPELINE = ["preprocess", "domains", "de", "genes", "statistics"]
# ---------------------------------------------------------------------------
# Backward compatibility helpers
# ---------------------------------------------------------------------------

def resolve_skill_alias(skill_name: str) -> str:
    """Resolve short alias to full domain:skill format.

    For backward compatibility, allows:
    - 'preprocess' -> 'spatial-preprocessing' (legacy alias)
    - 'spatial-preprocessing' -> 'spatial-preprocessing' (direct match)
    """
    # Direct match
    if skill_name in SKILLS:
        return skill_name

    # Check legacy aliases
    for skill_key, skill_info in SKILLS.items():
        legacy_aliases = skill_info.get("legacy_aliases", [])
        if skill_name in legacy_aliases:
            return skill_key

    # Domain:skill format
    if ":" in skill_name:
        domain, skill = skill_name.split(":", 1)
        if skill in SKILLS:
            return skill

    return skill_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def list_skills(domain_filter: str | None = None) -> dict:
    """按 Domain 分组打印所有可用技能，并返回 SKILLS 字典。"""
    print(f"\n{BOLD}OmicsClaw Skills{RESET}")
    if domain_filter:
        print(f"{BOLD}{'=' * 60}{RESET}")
        print(f"Filtering by domain: {CYAN}{domain_filter}{RESET}\n")
    else:
        print(f"{BOLD}{'=' * 60}{RESET}\n")

    # 1. 按 domain 分组构建索引
    domain_skills: dict[str, list[tuple[str, dict]]] = {}
    for alias, info in SKILLS.items():
        d = info.get("domain", "other")
        domain_skills.setdefault(d, []).append((alias, info))

    # 2. 按 DOMAINS 中定义的顺序依次输出
    for domain_key, domain_info in DOMAINS.items():
        if domain_filter and domain_key != domain_filter:
            continue
        skills_in_domain = domain_skills.get(domain_key, [])
        if not skills_in_domain:
            continue

        domain_name = domain_info.get("name", domain_key.title())
        data_types = domain_info.get("primary_data_types", [])
        types_str = ", ".join(f".{t}" if t != "*" else "*" for t in data_types)

        # 领域标题
        print(f"{BOLD}{YELLOW}📂 {domain_name}{RESET}  "
              f"{CYAN}[{types_str}]{RESET}")
        print(f"   {'─' * 54}")

        for alias, info in skills_in_domain:
            script = info["script"]
            status = f"{GREEN}ready{RESET}" if script.exists() else f"{YELLOW}planned{RESET}"
            desc = info.get("description", "")
            print(f"   {CYAN}{alias:<18}{RESET} [{status}] {desc}")

        print()

    # 3. 展示未在 DOMAINS 中注册的动态发现技能
    known_domains = set(DOMAINS.keys())
    extra = [(a, i) for a, i in SKILLS.items() if i.get("domain", "other") not in known_domains]
    if extra:
        print(f"{BOLD}{YELLOW}📂 Other (Dynamically Discovered){RESET}")
        print(f"   {'─' * 54}")
        for alias, info in extra:
            script = info["script"]
            status = f"{GREEN}ready{RESET}" if script.exists() else f"{YELLOW}planned{RESET}"
            desc = info.get("description", "")
            print(f"   {CYAN}{alias:<18}{RESET} [{status}] {desc}")
        print()

    total = len(SKILLS)
    print(f"{BOLD}Total: {total} skills across {len(DOMAINS)} domains{RESET}\n")
    return SKILLS


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def upload_session(
    input_path: str,
    data_type: str = "generic",
    species: str = "human",
) -> dict:
    """Create a SpatialSession from an h5ad file."""
    if str(OMICSCLAW_DIR) not in sys.path:
        sys.path.insert(0, str(OMICSCLAW_DIR))
    from omicsclaw.common.session import SpatialSession

    session = SpatialSession.from_h5ad(
        input_path, data_type=data_type, species=species,
    )
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sid = session.metadata["session_id"]
    session_path = SESSIONS_DIR / f"{sid}.json"
    session.save(session_path)
    return {
        "success": True,
        "session_path": str(session_path),
        "session_id": sid,
        "data_type": data_type,
    }


# ---------------------------------------------------------------------------
# Skill execution
# ---------------------------------------------------------------------------


def run_skill(
    skill_name: str,
    *,
    input_path: str | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
    extra_args: list[str] | None = None,
    timeout: int = 600,
) -> dict:
    """Run a single skill via subprocess."""

    # Resolve legacy aliases
    skill_name = resolve_skill_alias(skill_name)

    # Handle pipeline alias
    if skill_name == "spatial-pipeline":
        return _run_spatial_pipeline(
            input_path=input_path,
            output_dir=output_dir,
            session_path=session_path,
            timeout=timeout,
        )

    skill_info = SKILLS.get(skill_name)
    if skill_info is None:
        return _err(skill_name, f"Unknown skill '{skill_name}'. Available: {list(SKILLS.keys())}")

    script_path: Path = skill_info["script"]
    if not script_path.exists():
        return _err(skill_name, f"Script not found: {script_path}")

    # Resolve input from session if needed
    resolved_input = input_path
    if session_path and not input_path and not demo:
        if str(OMICSCLAW_DIR) not in sys.path:
            sys.path.insert(0, str(OMICSCLAW_DIR))
        from omicsclaw.common.session import SpatialSession
        session = SpatialSession.load(session_path)
        if session.h5ad_path:
            resolved_input = session.h5ad_path

    # Resolve input to absolute path so subprocess cwd doesn't matter
    if resolved_input:
        resolved_input = str(Path(resolved_input).resolve())

    # Output directory
    if output_dir:
        out_dir = Path(output_dir).resolve()
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = DEFAULT_OUTPUT_ROOT / f"{skill_name}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build command
    cmd = [PYTHON, str(script_path)]
    if demo:
        cmd.extend(skill_info["demo_args"])
    elif resolved_input:
        cmd.extend(["--input", str(resolved_input)])
    else:
        return _err(skill_name, "No --input, --demo, or --session provided.")

    cmd.extend(["--output", str(out_dir)])

    # Print execution info with domain
    domain = skill_info.get("domain", "unknown")
    domain_display = DOMAINS.get(domain, {}).get("name", domain.title())
    mode_str = f"{CYAN}demo mode{RESET}" if demo else f"input: {resolved_input}"
    print(f"\n{BOLD}Running {domain_display} skill:{RESET} {GREEN}{skill_name}{RESET} ({mode_str})")
    print(f"{BOLD}Output:{RESET} {out_dir}\n")

    # SEC INT-001: filter extra_args against per-skill allowlist
    if extra_args:
        allowed = skill_info.get("allowed_extra_flags", set())
        blocked = {"--input", "--output", "--demo"}
        filtered: list[str] = []
        i = 0
        while i < len(extra_args):
            flag = extra_args[i].split("=")[0]
            if flag in blocked:
                i += 2 if "=" not in extra_args[i] and i + 1 < len(extra_args) else i + 1
                continue
            if flag in allowed:
                filtered.append(extra_args[i])
                if "=" not in extra_args[i] and i + 1 < len(extra_args) and not extra_args[i + 1].startswith("-"):
                    filtered.append(extra_args[i + 1])
                    i += 1
            i += 1
        cmd.extend(filtered)

    # Execute
    t0 = time.time()
    try:
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = str(OMICSCLAW_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script_path.parent),
            env=env,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        return _err(skill_name, f"Timed out after {timeout}s", duration=duration)
    except Exception as e:
        duration = time.time() - t0
        return _err(skill_name, str(e), duration=duration)

    duration = time.time() - t0

    # Collect output files
    output_files = sorted(
        [f.name for f in out_dir.rglob("*") if f.is_file()]
    ) if out_dir.exists() else []

    result = {
        "skill": skill_name,
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output_dir": str(out_dir),
        "files": output_files,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_seconds": round(duration, 2),
    }

    # Update session if provided
    if session_path and result["success"]:
        _store_result_in_session(session_path, skill_name, out_dir)

    return result


def _run_spatial_pipeline(
    input_path: str | None = None,
    output_dir: str | None = None,
    session_path: str | None = None,
    timeout: int = 600,
) -> dict:
    """Run the standard spatial analysis pipeline end-to-end."""
    if not input_path and not session_path:
        return _err("spatial-pipeline", "Requires --input or --session.")

    if output_dir:
        out_dir = Path(output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = DEFAULT_OUTPUT_ROOT / f"spatial_pipeline_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, Any] = {}
    current_input = input_path

    for skill_name in SPATIAL_PIPELINE:
        skill_out = out_dir / skill_name
        print(f"  Running {skill_name}...")
        result = run_skill(
            skill_name=skill_name,
            input_path=current_input,
            output_dir=str(skill_out),
            session_path=session_path,
            timeout=timeout,
        )
        all_results[skill_name] = {
            "success": result["success"],
            "duration": result["duration_seconds"],
        }
        if not result["success"]:
            print(f"  {RED}FAILED{RESET}: {skill_name}")
            if result.get("stderr"):
                print(f"    {result['stderr'][:200]}")
            break

        # Chain: use processed h5ad from previous step as next input
        processed = skill_out / "processed.h5ad"
        if processed.exists():
            current_input = str(processed)

    summary = {
        "pipeline": SPATIAL_PIPELINE,
        "results": all_results,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = out_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    succeeded = sum(1 for r in all_results.values() if r["success"])
    return {
        "skill": "spatial-pipeline",
        "success": succeeded == len(SPATIAL_PIPELINE),
        "exit_code": 0 if succeeded == len(SPATIAL_PIPELINE) else 1,
        "output_dir": str(out_dir),
        "files": [f.name for f in out_dir.rglob("*") if f.is_file()],
        "stdout": f"Pipeline: {succeeded}/{len(SPATIAL_PIPELINE)} skills succeeded.",
        "stderr": "",
        "duration_seconds": sum(r["duration"] for r in all_results.values()),
    }


def _store_result_in_session(
    session_path: str, skill_name: str, out_dir: Path,
) -> None:
    """Store skill result back into the session JSON."""
    try:
        if str(OMICSCLAW_DIR) not in sys.path:
            sys.path.insert(0, str(OMICSCLAW_DIR))
        from omicsclaw.common.session import SpatialSession

        result_json = out_dir / "result.json"
        if not result_json.exists():
            return
        session = SpatialSession.load(session_path)
        result_data = json.loads(result_json.read_text())
        session.add_skill_result(skill_name, result_data, output_dir=str(out_dir))

        processed = out_dir / "processed.h5ad"
        if processed.exists():
            session.h5ad_path = str(processed)
            session.mark_step(skill_name)

        session.save(session_path)
    except Exception:
        pass


def _err(skill: str, msg: str, duration: float = 0) -> dict:
    return {
        "skill": skill,
        "success": False,
        "exit_code": -1,
        "output_dir": None,
        "files": [],
        "stdout": "",
        "stderr": msg,
        "duration_seconds": round(duration, 2),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="OmicsClaw — Multi-Omics Skills Runner",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    list_p = sub.add_parser("list", help="List available skills")
    list_p.add_argument("--domain", help="Filter by domain (e.g., spatial, singlecell, genomics)")

    # env
    env_p = sub.add_parser("env", help="Check installed OmicsClaw dependency tiers")

    # upload
    upload_p = sub.add_parser("upload", help="Create a spatial session from h5ad data")
    upload_p.add_argument("--input", required=True, dest="input_path")
    upload_p.add_argument("--data-type", default="generic")
    upload_p.add_argument("--species", default="human")

    # run
    run_p = sub.add_parser("run", help="Run a skill")
    run_p.add_argument("skill", help="Skill alias (e.g. preprocess, domains) or 'spatial-pipeline'")
    run_p.add_argument("--demo", action="store_true")
    run_p.add_argument("--input", dest="input_path")
    run_p.add_argument("--output", dest="output_dir")
    run_p.add_argument("--session", dest="session_path")
    run_p.add_argument("--timeout", type=int, default=600)
    # Skill-specific flags (forwarded to the skill script)
    run_p.add_argument("--data-type", dest="data_type")
    run_p.add_argument("--species")
    run_p.add_argument("--method")
    run_p.add_argument("--n-domains", type=int)
    run_p.add_argument("--resolution", type=float)
    run_p.add_argument("--min-genes", type=int)
    run_p.add_argument("--min-cells", type=int)
    run_p.add_argument("--max-mt-pct", type=float)
    run_p.add_argument("--n-top-hvg", type=int)
    run_p.add_argument("--n-pcs", type=int)
    run_p.add_argument("--n-neighbors", type=int)
    run_p.add_argument("--leiden-resolution", type=float)
    run_p.add_argument("--groupby")
    run_p.add_argument("--group1")
    run_p.add_argument("--group2")
    run_p.add_argument("--n-top-genes", type=int)
    run_p.add_argument("--genes")
    run_p.add_argument("--reference")
    run_p.add_argument("--model")
    run_p.add_argument("--cell-type-key")
    run_p.add_argument("--analysis-type")
    run_p.add_argument("--cluster-key")
    run_p.add_argument("--feature")
    run_p.add_argument("--fdr-threshold", type=float)
    run_p.add_argument("--gene-set")
    run_p.add_argument("--source")
    run_p.add_argument("--condition-key")
    run_p.add_argument("--sample-key")
    run_p.add_argument("--reference-condition")
    run_p.add_argument("--batch-key")
    run_p.add_argument("--reference-slice")
    run_p.add_argument("--reference-key")
    run_p.add_argument("--mode")
    run_p.add_argument("--root-cell")
    run_p.add_argument("--n-states", type=int)
    run_p.add_argument("--query")
    run_p.add_argument("--pipeline")
    # domains-specific
    run_p.add_argument("--spatial-weight", type=float)
    run_p.add_argument("--rad-cutoff", type=float)
    run_p.add_argument("--lambda-param", type=float)
    run_p.add_argument("--refine", action="store_true")
    # communication-specific
    run_p.add_argument("--n-perms", type=int)
    # deconv-specific
    run_p.add_argument("--n-epochs", type=int)
    # cnv-specific
    run_p.add_argument("--window-size", type=int)
    run_p.add_argument("--step", type=int)
    run_p.add_argument("--reference-cat", nargs="+")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "list":
        list_skills(domain_filter=getattr(args, "domain", None))
        sys.exit(0)

    if args.command == "env":
        from omicsclaw.core.dependency_manager import get_installed_tiers
        tiers = get_installed_tiers()
        
        print(f"\n{BOLD}OmicsClaw Environment Status{RESET}")
        print(f"{BOLD}{'=' * 40}{RESET}")
        
        core_status = f"{GREEN}✅ Installed{RESET}" if tiers.get("core") else f"{RED}❌ Missing{RESET}"
        print(f"Core System:      {core_status}")
        
        print(f"\n{BOLD}Domain Tiers:{RESET}")
        for tier in ["spatial", "singlecell", "genomics", "proteomics", "metabolomics"]:
            is_installed = tiers.get(tier, False)
            if is_installed:
                status = f"{GREEN}✅ Installed{RESET}"
            else:
                status = f"{RED}❌ Missing{RESET} (Run: pip install -e \".[{tier}]\")"
            print(f"- {tier.capitalize():<15} {status}")
            
        print(f"\n{BOLD}Standalone Layer:{RESET}")
        sd_installed = tiers.get("spatial-domains", False)
        sd_status = f"{GREEN}✅ Installed{RESET}" if sd_installed else f"{RED}❌ Missing{RESET} (Run: pip install -e \".[spatial-domains]\")"
        print(f"- Spatial-Domains {sd_status} (Deep learning spatial domain methods, e.g., SpaGCN)")
        
        print(f"\nTo install all complete functionalities:\n  pip install -e \".[full]\"\n")
        sys.exit(0)

    if args.command == "upload":
        result = upload_session(
            args.input_path,
            data_type=args.data_type,
            species=args.species,
        )
        if result["success"]:
            print(f"{GREEN}Session created:{RESET} {result['session_path']}")
        else:
            print(f"{RED}Upload failed{RESET}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    if args.command == "run":
        # Collect extra args from skill-specific flags
        extra: list[str] = []
        flag_map = {
            "data_type": "--data-type",
            "species": "--species",
            "method": "--method",
            "n_domains": "--n-domains",
            "resolution": "--resolution",
            "min_genes": "--min-genes",
            "min_cells": "--min-cells",
            "max_mt_pct": "--max-mt-pct",
            "n_top_hvg": "--n-top-hvg",
            "n_pcs": "--n-pcs",
            "n_neighbors": "--n-neighbors",
            "leiden_resolution": "--leiden-resolution",
            "groupby": "--groupby",
            "group1": "--group1",
            "group2": "--group2",
            "n_top_genes": "--n-top-genes",
            "genes": "--genes",
            "reference": "--reference",
            "model": "--model",
            "cell_type_key": "--cell-type-key",
            "analysis_type": "--analysis-type",
            "cluster_key": "--cluster-key",
            "feature": "--feature",
            "fdr_threshold": "--fdr-threshold",
            "gene_set": "--gene-set",
            "source": "--source",
            "condition_key": "--condition-key",
            "sample_key": "--sample-key",
            "reference_condition": "--reference-condition",
            "batch_key": "--batch-key",
            "reference_slice": "--reference-slice",
            "reference_key": "--reference-key",
            "mode": "--mode",
            "root_cell": "--root-cell",
            "n_states": "--n-states",
            "query": "--query",
            "pipeline": "--pipeline",
            # domains-specific
            "spatial_weight": "--spatial-weight",
            "rad_cutoff": "--rad-cutoff",
            "lambda_param": "--lambda-param",
            # communication-specific
            "n_perms": "--n-perms",
            # deconv-specific
            "n_epochs": "--n-epochs",
            # cnv-specific
            "window_size": "--window-size",
            "step": "--step",
        }
        # flags whose values are file paths — resolve to absolute so subprocess cwd doesn't matter
        _FILE_PATH_FLAGS = {"reference", "reference_slice", "model"}

        for attr, flag in flag_map.items():
            val = getattr(args, attr, None)
            if val is not None:
                if attr in _FILE_PATH_FLAGS:
                    val = str(Path(val).resolve())
                extra.extend([flag, str(val)])

        # boolean flags
        if getattr(args, "refine", False):
            extra.append("--refine")
        # nargs="+" args
        if getattr(args, "reference_cat", None):
            extra.extend(["--reference-cat"] + args.reference_cat)

        result = run_skill(
            args.skill,
            input_path=args.input_path,
            output_dir=args.output_dir,
            demo=args.demo,
            session_path=args.session_path,
            extra_args=extra if extra else None,
            timeout=args.timeout,
        )

        if result["success"]:
            print(f"{GREEN}Success{RESET}: {result['skill']}")
            if result.get("output_dir"):
                print(f"  Output: {result['output_dir']}")
            if result.get("stdout"):
                print(result["stdout"], end="")
        else:
            print(f"{RED}Failed{RESET}: {result['skill']}", file=sys.stderr)
            if result.get("stderr"):
                print(result["stderr"], file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
