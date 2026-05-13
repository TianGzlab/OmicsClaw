"""Skill orchestration helpers — output media collection + auto-routing
banner / disambiguation rendering.

Carved out of ``bot/core.py`` per ADR 0001. **Reduced scope**: this slice
moves only the externally-tested public API (``OutputMediaPaths`` +
``_collect_output_media_paths``; the auto-routing banner / disambiguation
formatters and ``_AUTO_DISAMBIGUATE_GAP``). The remaining skill-execution
machinery the issue spec lists (``_run_omics_skill_step``,
``_run_skill_via_shared_runner``, ``_lookup_skill_info``,
``_resolve_param_hint_info``, ``_infer_skill_for_method``,
``_build_method_preview``, ``_build_param_hint``, the
``_auto_capture_*`` async helpers, the env-error parsing helpers, and
``_resolve_last_output_dir`` / ``_read_result_json`` /
``_update_preprocessing_state`` / ``_format_next_steps``) stays in
``bot.core`` for now — they have no external test imports and moving the
~700 LOC en bloc would require many late-import surgery passes that buy
no immediate win. A follow-up issue can complete the migration once the
agent-loop slice (#121) has consolidated the LLM client globals.

The functions in this module are pure formatters; ``_format_auto_*``
late-imports ``_skill_registry`` from ``bot.core`` to look up skill
descriptions for the disambiguation block.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputMediaPaths:
    figure_paths: list[Path]
    table_paths: list[Path]
    notebook_paths: list[Path]
    media_items: list[dict]


def _collect_output_media_paths(out_dir: Path) -> OutputMediaPaths:
    figure_paths: list[Path] = []
    table_paths: list[Path] = []
    notebook_paths: list[Path] = []
    media_items: list[dict] = []

    if not out_dir.exists():
        return OutputMediaPaths(figure_paths, table_paths, notebook_paths, media_items)

    for f in sorted(out_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix in (".md", ".html"):
            media_items.append({"type": "document", "path": str(f)})
        elif f.suffix == ".ipynb":
            media_items.append({"type": "document", "path": str(f)})
            notebook_paths.append(f)
        elif f.suffix == ".png":
            media_items.append({"type": "photo", "path": str(f)})
            figure_paths.append(f)
        elif f.suffix == ".csv":
            media_items.append({"type": "document", "path": str(f)})
            table_paths.append(f)

    return OutputMediaPaths(figure_paths, table_paths, notebook_paths, media_items)


# Auto-routing disambiguation block: emitted when the capability resolver's
# top-2 candidates are within ~``_AUTO_DISAMBIGUATE_GAP`` of each other.
# Tuned against ``capability_resolver._candidate_score`` output magnitudes
# (single keyword match is worth ~0.85 points; an alias hit is worth ~10).
_AUTO_DISAMBIGUATE_GAP = 2.0


def _format_auto_disambiguation(decision, query_text: str) -> str:
    """Return a human-readable disambiguation block for close-tie auto routing."""
    from bot.core import _skill_registry  # late import — defined later in bot.core

    candidates = list(decision.skill_candidates or [])[:3]
    if not candidates:
        return ""
    reg = _skill_registry()
    lines = [
        "🤔 **Auto-routing found multiple close candidates** — I won't execute yet.",
        f"Query: `{query_text.strip()[:200]}`",
        "",
        "**Top candidates (score — higher is better):**",
    ]
    for i, c in enumerate(candidates, 1):
        info = reg.skills.get(c.skill, {}) or {}
        desc = (info.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 140:
            desc = desc[:137] + "…"
        reason = c.reasons[0] if c.reasons else ""
        lines.append(f"{i}. `{c.skill}` (score {c.score:.2f}) — {desc}")
        if reason:
            lines.append(f"   matched: {reason}")
    lines.extend([
        "",
        "**Next step:** re-invoke `omicsclaw` with `skill='<chosen alias above>'` "
        "and the same `mode`/`query`. Pick based on the user's data modality "
        "(H&E+coordinates → spatial; h5ad single-cell counts → singlecell; "
        "bulk counts csv → bulkrna; raw MS/LC-MS → proteomics/metabolomics).",
    ])
    return "\n".join(lines)


def _format_auto_route_banner(decision) -> str:
    """Return a short banner prepended to tool output when auto routing chose a skill."""
    chosen = decision.chosen_skill
    conf = float(getattr(decision, "confidence", 0.0) or 0.0)
    candidates = list(decision.skill_candidates or [])
    alts = [c.skill for c in candidates[1:3] if c.skill != chosen]
    alt_str = f" Close alternatives: {', '.join(alts)}." if alts else ""
    return (
        f"📍 Auto-routed to `{chosen}` (confidence {conf:.2f}).{alt_str} "
        "If this doesn't match the user's intent, re-invoke with an explicit `skill`.\n---\n"
    )


# ===========================================================================
# Memory auto-capture, env-error parsing, output state, skill execution.
# Migrated from bot/core.py per ADR 0001 (#119 reduced-scope follow-up).
#
# These were the internal helpers that no external test imports directly —
# the regression net (tests/test_bot_*.py + tests/test_oauth_regressions.py
# + tests/test_app_server.py + tests/test_notebook_files.py + tests/bot/)
# is the contract.
# ===========================================================================

import asyncio
import logging
import re
import threading
from datetime import datetime

from omicsclaw.common.report import build_output_dir_name
from omicsclaw.common.user_guidance import (
    extract_user_guidance_lines,
    render_guidance_block,
    strip_user_guidance_lines,
)
from omicsclaw.core.registry import registry
from omicsclaw.runtime.skill_lookup import lookup_skill_info

logger = logging.getLogger("omicsclaw.bot.skill_orchestration")


# ---------------------------------------------------------------------------
# Memory auto-capture helpers
# ---------------------------------------------------------------------------


async def _auto_capture_dataset(session_id: str, input_path: str, data_type: str = ""):
    """Auto-capture dataset memory when a file is processed."""
    from bot.core import OMICSCLAW_DIR, memory_store
    if not memory_store or not session_id or not input_path:
        return

    try:
        from omicsclaw.memory.compat import DatasetMemory

        try:
            rel_path = str(Path(input_path).relative_to(OMICSCLAW_DIR))
        except ValueError:
            rel_path = Path(input_path).name

        n_obs = None
        n_vars = None
        try:
            suffix = Path(input_path).suffix.lower()
            if suffix in (".h5ad",):
                import h5py
                with h5py.File(input_path, "r") as h5:
                    if "obs" in h5 and hasattr(h5["obs"], "attrs"):
                        shape = h5["obs"].attrs.get("_index", h5["obs"].attrs.get("encoding-type", None))
                    if "X" in h5:
                        x = h5["X"]
                        if hasattr(x, "shape"):
                            n_obs, n_vars = x.shape
        except Exception:
            pass

        ds_mem = DatasetMemory(
            file_path=rel_path,
            platform=data_type or None,
            n_obs=n_obs,
            n_vars=n_vars,
            preprocessing_state="raw",
        )
        await memory_store.save_memory(session_id, ds_mem)
        logger.debug(f"Auto-captured dataset: {rel_path}")
    except Exception as e:
        logger.warning(f"Auto-capture dataset failed: {e}")


async def _auto_capture_analysis(session_id: str, skill: str, args: dict, output_dir: Path, success: bool):
    """Auto-capture analysis memory after skill execution."""
    from bot.core import memory_store
    if not memory_store or not session_id:
        return

    try:
        from omicsclaw.memory.compat import AnalysisMemory

        method = args.get("method", "default")
        input_path = args.get("file_path", "")

        source_dataset_id = ""
        try:
            datasets = await memory_store.get_memories(session_id, "dataset", limit=1)
            if datasets:
                source_dataset_id = datasets[0].memory_id
        except Exception:
            pass

        memory = AnalysisMemory(
            source_dataset_id=source_dataset_id if source_dataset_id else "",
            skill=skill,
            method=method,
            parameters={"input": input_path} if input_path else {},
            output_path=str(output_dir) if output_dir else "",
            status="completed" if success else "failed"
        )

        await memory_store.save_memory(session_id, memory)
        logger.debug(f"Auto-captured analysis: {skill} ({method})")
    except Exception as e:
        logger.warning(f"Auto-capture analysis failed: {e}")


# ---------------------------------------------------------------------------
# Env-error parsing
# ---------------------------------------------------------------------------


_ENV_ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"compiled using NumPy 1\.x",                    "NumPy 版本冲突"),
    (r"cannot be run in\s+NumPy\s+\d",               "NumPy 版本冲突"),
    (r"downgrade to ['\"]?numpy[<>=]",                "NumPy 版本冲突"),
    (r"CUDA.*out of memory|out of memory.*CUDA",      "GPU 显存不足"),
    (r"Rscript[:\s]+command not found",               "R 未安装或不在 PATH 中"),
    (r"Rscript.*not found",                           "R 未安装或不在 PATH 中"),
    (r"cannot find R",                                "R 未安装或不在 PATH 中"),
    (r"there is no package called",                   "缺少 R 包"),
    (r"No space left on device",                      "服务器磁盘空间不足"),
    (r"(?<!\w)Killed(?!\w)",                          "进程被 OOM Killer 终止（内存不足）"),
    (r"cannot allocate.*memory|MemoryError",          "内存不足"),
    (r"ModuleNotFoundError",                          "缺少 Python 包"),
    (r"ImportError",                                  "缺少 Python 包（版本冲突或未安装）"),
]


def _extract_env_snippet(full_err: str) -> str:
    """Show the beginning (package/file name) and end (error message) of stderr."""
    lines = [l for l in full_err.strip().splitlines() if l.strip()]
    if len(lines) <= 15:
        return full_err.strip()
    head = "\n".join(lines[:6])
    tail = "\n".join(lines[-8:])
    return f"{head}\n...\n{tail}"


def _extract_fix_hint(label: str, err: str) -> str:
    """Return a specific, actionable fix command based on the error type and content."""
    if "NumPy" in label:
        return "pip install 'numpy<2'  # 或: conda install 'numpy<2'"
    if "R 未安装" in label:
        return "conda install -c conda-forge r-base  # 或: sudo apt install r-base"
    if "磁盘" in label:
        return "df -h  # 检查磁盘空间，清理 output/ 或 /tmp 下的大文件"
    if "OOM" in label:
        return "增加服务器内存，或减小输入数据规模后重试"
    if "GPU" in label:
        return "减少 batch_size，或在 extra_args 中加 --device cpu 使用 CPU 模式"
    if "内存不足" in label:
        return "增加服务器内存，或减小输入数据规模后重试"
    if "R 包" in label:
        r_pkgs = re.findall(r"there is no package called '([^']+)'", err)
        if r_pkgs:
            install_cmd = ", ".join(f'"{p}"' for p in r_pkgs)
            return f"Rscript -e 'install.packages(c({install_cmd}))'"
        return "Rscript -e 'install.packages(\"<包名>\")' # 检查上方报错确认具体包名"
    m = re.search(r"No module named ['\"]?([a-zA-Z0-9_\-\.]+)['\"]?", err)
    if m:
        pkg = m.group(1).split(".")[0]
        return f"pip install {pkg}  # 或: conda install {pkg}"
    return "pip install <缺少的包名>  # 检查上方报错确认具体包名"


def _classify_env_error(err: str) -> str | None:
    """Return a user-friendly message if the error is environment-related, else None."""
    for pattern, label in _ENV_ERROR_PATTERNS:
        if re.search(pattern, err, re.IGNORECASE):
            snippet = _extract_env_snippet(err)
            fix = _extract_fix_hint(label, err)
            return (
                f"**环境错误（不是你的数据问题）: {label}**\n\n"
                "分析环境有配置问题，你的数据文件完全没问题。\n\n"
                f"**修复方法（在终端运行）:**\n```\n{fix}\n```\n\n"
                f"**技术详情:**\n```\n{snippet}\n```"
            )
    return None


# ---------------------------------------------------------------------------
# Output state helpers
# ---------------------------------------------------------------------------


async def _resolve_last_output_dir(session_id: str, skill: str) -> Path | None:
    """Find the most recent completed output directory for a skill from session memory."""
    from bot.core import memory_store
    if not memory_store or not session_id:
        return None
    try:
        from omicsclaw.memory.compat import AnalysisMemory
        analyses = await memory_store.get_memories(session_id, "analysis", limit=20)
        for mem in analyses:
            if (
                isinstance(mem, AnalysisMemory)
                and mem.skill == skill
                and mem.output_path
                and getattr(mem, "status", None) == "completed"
            ):
                p = Path(mem.output_path)
                if p.exists():
                    return p
    except Exception as e:
        logger.debug(f"_resolve_last_output_dir failed: {e}")
    return None


def _read_result_json(out_dir: Path) -> dict | None:
    """Read result.json from the skill output directory, return parsed dict or None."""
    result_path = out_dir / "result.json"
    if not result_path.exists():
        return None
    try:
        import json as _json
        return _json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug(f"Failed to read result.json: {e}")
        return None


async def _update_preprocessing_state(session_id: str, result_data: dict):
    """Update the current dataset's preprocessing_state from result.json data."""
    from bot.core import memory_store
    if not memory_store or not session_id:
        return
    new_state = result_data.get("preprocessing_state_after")
    if not new_state:
        return
    try:
        datasets = await memory_store.get_memories(session_id, "dataset", limit=1)
        if not datasets:
            return
        ds = datasets[0]
        if ds.preprocessing_state == new_state:
            return
        ds.preprocessing_state = new_state
        await memory_store.save_memory(session_id, ds)
        logger.info(f"Updated preprocessing_state: {new_state} for {ds.file_path}")
    except Exception as e:
        logger.warning(f"Failed to update preprocessing_state: {e}")


def _format_next_steps(result_data: dict) -> str:
    """Format next_steps from result.json data into a user-friendly recommendation block."""
    next_steps = result_data.get("next_steps")
    if not next_steps:
        return ""
    if isinstance(next_steps, list) and all(isinstance(s, str) for s in next_steps):
        lines = ["\n**Suggested next steps:**"]
        for step in next_steps:
            lines.append(f"- {step}")
        return "\n".join(lines)
    if isinstance(next_steps, list) and all(isinstance(s, dict) for s in next_steps):
        lines = ["\n**Suggested next steps:**"]
        for step in next_steps:
            skill_name = step.get("skill", "")
            desc = step.get("description", "")
            priority = step.get("priority", "")
            tag = f" ({priority})" if priority else ""
            if skill_name and desc:
                lines.append(f"- **{skill_name}** — {desc}{tag}")
            elif skill_name:
                lines.append(f"- **{skill_name}**{tag}")
            else:
                lines.append(f"- {desc}{tag}")
        lines.append("\nTell me which one you'd like to run!")
        return "\n".join(lines)
    return ""


# ---------------------------------------------------------------------------
# Skill execution + lookup
# ---------------------------------------------------------------------------


def _normalize_extra_args(extra_args) -> list[str]:
    if not extra_args or not isinstance(extra_args, list):
        return []
    filtered = []
    skip_next = False
    for arg in extra_args:
        if skip_next:
            skip_next = False
            continue
        if arg == "--output":
            skip_next = True
            continue
        if arg.startswith("--output="):
            continue
        if arg.startswith("--"):
            eq_pos = arg.find("=")
            if eq_pos > 0:
                flag_part = arg[:eq_pos].replace("_", "-")
                arg = flag_part + arg[eq_pos:]
            else:
                arg = arg.replace("_", "-")
        filtered.append(arg)
    return filtered


async def _run_omics_skill_step(
    *,
    skill_key: str,
    input_path: str | None,
    mode: str,
    method: str = "",
    data_type: str = "",
    batch_key: str = "",
    n_epochs: int | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    import uuid

    from bot.core import OUTPUT_DIR

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / build_output_dir_name(
        skill_key,
        ts,
        method=method,
        unique_suffix=uuid.uuid4().hex[:8],
    )

    return await _run_skill_via_shared_runner(
        skill_key=skill_key,
        input_path=input_path,
        session_path=None,
        mode=mode,
        method=method,
        data_type=data_type,
        batch_key=batch_key,
        n_epochs=n_epochs,
        extra_args=extra_args,
        out_dir=out_dir,
    )


async def _run_skill_via_shared_runner(
    *,
    skill_key: str,
    input_path: str | None,
    session_path: str | None,
    mode: str,
    method: str = "",
    data_type: str = "",
    batch_key: str = "",
    n_epochs: int | None = None,
    extra_args: list[str] | None = None,
    out_dir: Path,
) -> dict:
    from omicsclaw.core import skill_runner
    from omicsclaw.core.skill_result import SkillRunResult

    runner_skill = "spatial-pipeline" if skill_key == "pipeline" else skill_key
    skill_info = _lookup_skill_info(runner_skill)
    canonical_skill = skill_info.get("alias") or runner_skill

    forwarded_args: list[str] = []
    if method:
        forwarded_args.extend(["--method", method])
    if data_type:
        forwarded_args.extend(["--data-type", data_type])
    if batch_key:
        forwarded_args.extend(["--batch-key", batch_key])
    if n_epochs is not None:
        # The legacy alias ``spatial-domain-identification`` was the only skill
        # that wanted ``--epochs`` instead of ``--n-epochs``, but the registry
        # now resolves that alias to canonical ``spatial-domains`` before we
        # land here — the conditional was dead code. ``argv_builder``'s
        # ``--epochs`` ↔ ``--n-epochs`` rewrite (see
        # ``omicsclaw/core/runtime/argv_builder.py``) handles whichever flag
        # each skill's ``allowed_extra_flags`` actually accepts.
        forwarded_args.extend(["--n-epochs", str(int(n_epochs))])
    forwarded_args.extend(_normalize_extra_args(extra_args))

    def _emit_stdout(line: str) -> None:
        logger.info("[%s:stdout] %s", canonical_skill, line)

    def _emit_stderr(line: str) -> None:
        logger.info("[%s:stderr] %s", canonical_skill, line)

    cancel_event = threading.Event()

    def _run() -> SkillRunResult:
        return skill_runner.run_skill(
            runner_skill,
            input_path=str(input_path) if input_path else None,
            output_dir=str(out_dir),
            demo=mode == "demo",
            session_path=session_path,
            extra_args=forwarded_args or None,
            stdout_callback=_emit_stdout,
            stderr_callback=_emit_stderr,
            cancel_event=cancel_event,
        )

    try:
        run_result = await asyncio.to_thread(_run)
    except asyncio.CancelledError:
        cancel_event.set()
        raise
    stdout_str = run_result.stdout
    stderr_str = run_result.stderr
    guidance_block = render_guidance_block(extract_user_guidance_lines(stderr_str))
    clean_stderr = strip_user_guidance_lines(stderr_str)
    clean_stdout = strip_user_guidance_lines(stdout_str)
    error_text = clean_stderr[-1500:] if clean_stderr else clean_stdout[-1500:] if clean_stdout else "unknown error"
    returncode = run_result.adapter_exit_code
    output_dir = run_result.output_path or out_dir
    return {
        "success": run_result.success,
        "returncode": returncode,
        "out_dir": output_dir,
        "output_dir": str(output_dir),
        "stdout": stdout_str,
        "stderr": stderr_str,
        "guidance_block": guidance_block,
        "error_text": error_text,
    }


# Re-export from the canonical home (omicsclaw.runtime.skill_lookup) so
# existing ``bot.skill_orchestration._lookup_skill_info`` / ``bot.core``
# call sites keep working without churn.
_lookup_skill_info = lookup_skill_info


def _resolve_param_hint_info(skill_key: str, method: str) -> tuple[str, dict, dict]:
    """Return (method_lower, tip_info, skill_info) from SKILL.md param_hints."""
    method_lower = (method or "").lower().strip()
    if not method_lower:
        return "", {}, {}

    try:
        skill_info = _lookup_skill_info(skill_key, force_reload=False)
        hints = skill_info.get("param_hints", {}) if skill_info else {}
        tip_info = hints.get(method_lower)

        if not tip_info:
            skill_info = _lookup_skill_info(skill_key, force_reload=True)
            hints = skill_info.get("param_hints", {}) if skill_info else {}
            tip_info = hints.get(method_lower)

        logger.info(
            "param_hint lookup: skill_key=%s, method=%s, skill_found=%s, hints_keys=%s",
            skill_key,
            method_lower,
            bool(skill_info),
            list(hints.keys()) if hints else "EMPTY",
        )
        return method_lower, (tip_info or {}), (skill_info or {})
    except Exception as e:
        logger.warning("param_hint loading failed: %s", e)
        return method_lower, {}, {}


def _infer_skill_for_method(method: str, preferred_domain: str = "") -> str:
    """Infer a skill alias from method name using registry param_hints."""
    method_lower = (method or "").strip().lower()
    if not method_lower:
        return ""
    try:
        from bot.core import _skill_registry
        skill_registry = _skill_registry()

        candidates: list[str] = []
        for alias, info in skill_registry.skills.items():
            if alias != info.get("alias", alias):
                continue
            if preferred_domain and info.get("domain", "") != preferred_domain:
                continue
            hints = info.get("param_hints", {}) or {}
            if method_lower in hints:
                candidates.append(alias)

        if len(candidates) == 1:
            return candidates[0]
        return sorted(candidates)[0] if candidates else ""
    except Exception:
        return ""


def _build_method_preview(
    *,
    skill_key: str,
    method: str,
    n_obs: int | None,
    has_spatial: bool,
    has_x_pca: bool,
    has_raw: bool,
    has_counts_layer: bool,
    platform: str,
) -> str:
    """Build pre-run suitability + default parameter preview for inspect_data."""
    method_lower, tip_info, skill_info = _resolve_param_hint_info(skill_key, method)
    if not method_lower or not tip_info:
        return ""

    checks: list[str] = []
    seen_checks: set[str] = set()

    def _add_check(line: str) -> None:
        if line not in seen_checks:
            checks.append(line)
            seen_checks.add(line)

    suitable = True

    requires = tip_info.get("requires", []) if isinstance(tip_info, dict) else []
    requires_tokens = {str(r).strip().lower() for r in requires}

    if "spatial" in platform.lower() and "obsm.spatial" not in requires_tokens:
        if has_spatial:
            _add_check("- `obsm['spatial']`: found ✅")
        else:
            _add_check("- `obsm['spatial']`: missing ❌ (spatial methods usually require this)")
            suitable = False

    for req in requires:
        req_token = str(req).strip().lower()
        if req_token == "obsm.spatial":
            ok = has_spatial
            text = "`obsm['spatial']`"
        elif req_token == "obsm.x_pca":
            ok = has_x_pca
            text = "`obsm['X_pca']`"
        elif req_token == "raw":
            ok = has_raw
            text = "`adata.raw`"
        elif req_token == "layers.counts":
            ok = has_counts_layer
            text = "`layers['counts']`"
        elif req_token == "raw_or_counts":
            ok = has_raw or has_counts_layer
            text = "`adata.raw` or `layers['counts']`"
        else:
            _add_check(f"- Requirement `{req}`: please verify manually")
            continue

        if ok:
            _add_check(f"- Requirement {text}: found ✅")
        else:
            _add_check(f"- Requirement {text}: missing ⚠️")
            suitable = False

    if has_x_pca:
        _add_check("- `obsm['X_pca']`: found ✅")
    if isinstance(n_obs, int):
        size_note = f"{n_obs:,} cells/spots"
        if n_obs > 30000 and "epochs" in (tip_info.get("params", []) or []):
            size_note += " (large; start with fewer epochs)"
        _add_check(f"- Dataset size: {size_note}")

    defaults = tip_info.get("defaults", {}) if isinstance(tip_info, dict) else {}
    param_lines = []
    recommended_args = [f"--method {method_lower}"]
    for p in tip_info.get("params", []):
        default_val = defaults.get(p, "default")
        if (
            p == "epochs"
            and isinstance(n_obs, int)
            and n_obs > 30000
        ):
            default_text = f"{default_val} (for large data, try 50-100 first)"
            recommended_val = 50
        else:
            default_text = str(default_val)
            recommended_val = default_val
        param_lines.append(f"- `{p}`: {default_text}")

        if recommended_val != "default":
            cli_flag = f"--{p.replace('_', '-')}"
            recommended_args.append(f"{cli_flag} {recommended_val}")

    suitability_text = "✅ Suitable for a first run" if suitable else "❌ Not suitable yet"
    canonical_alias = skill_info.get("alias", skill_key) if skill_info else skill_key

    lines = [
        "### Method Suitability & Parameter Preview",
        f"- Requested skill: `{canonical_alias}`",
        f"- Requested method: `{method_lower}`",
        f"- Suitability: {suitability_text}",
    ]
    if checks:
        lines.append("- Checks:")
        lines.extend([f"  {c}" for c in checks])
    if param_lines:
        lines.append("- Default parameter preview:")
        lines.extend([f"  {p}" for p in param_lines])
    lines.append(f"- Tuning priority: {tip_info.get('priority', 'N/A')}")
    lines.append(f"- Suggested first run: `{ ' '.join(recommended_args) }`")
    return "\n".join(lines)


def _build_param_hint(skill_key: str, method: str, cmd: list[str]) -> str:
    """Build a two-tier parameter card from SKILL.md-declared param_hints."""
    method_lower, tip_info, skill_info = _resolve_param_hint_info(skill_key, method)
    if not tip_info:
        hints = skill_info.get("param_hints", {}) if skill_info else {}
        logger.info("param_hint: no hints for method '%s' in %s", method_lower, list(hints.keys()))
        return ""

    params_found = {}
    for i, arg in enumerate(cmd):
        if arg.startswith("--") and i + 1 < len(cmd) and not cmd[i + 1].startswith("--"):
            params_found[arg.lstrip("-").replace("-", "_")] = cmd[i + 1]

    defaults_map: dict = tip_info.get("defaults", {})

    def _fmt_param(key: str) -> str:
        if key in params_found:
            return f"{key}={params_found[key]}"
        dval = defaults_map.get(key)
        return f"{key}={dval}" if dval is not None else f"{key}=default"

    core_keys: list[str] = tip_info.get("params", [])
    adv_keys: list[str] = tip_info.get("advanced_params", [])

    lines = [f"📋 **{skill_key} · {method_lower}**", ""]

    if core_keys:
        lines.append("核心参数: " + " | ".join(_fmt_param(k) for k in core_keys))
    if adv_keys:
        lines.append("高级参数: " + " | ".join(_fmt_param(k) for k in adv_keys))

    priority = tip_info.get("priority", "")
    if priority:
        lines.append(f"调参优先级: {priority.replace(' -> ', ' → ')}")

    for t in tip_info.get("tips", []):
        lines.append(f"  · {t}")

    lines.append("")
    lines.append(
        "[PARAM CARD: show the parameter lines above verbatim to the user — "
        "do not paraphrase, abbreviate, or omit the 高级参数 line]"
    )
    lines.append("")
    return "\n".join(lines)
