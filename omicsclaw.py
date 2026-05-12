#!/usr/bin/env python3
"""OmicsClaw — Multi-Omics Analysis Skills Runner.

Usage:
    python omicsclaw.py list
    python omicsclaw.py run <skill> --demo
    python omicsclaw.py run <skill> --input <data> --output <dir>
    python omicsclaw.py run spatial-pipeline --input <h5ad> --output <dir>
    python omicsclaw.py upload --input <data> --data-type <type>

Interactive CLI/TUI:
    python omicsclaw.py interactive               # Rich CLI (prompt_toolkit)
    python omicsclaw.py interactive --ui tui      # Full-screen Textual TUI
    python omicsclaw.py interactive -p "..."      # Single-shot mode
    python omicsclaw.py interactive --session <id> # Resume session
    python omicsclaw.py tui                       # Alias for --ui tui

MCP Server Management:
    python omicsclaw.py mcp list
    python omicsclaw.py mcp add <name> <command> [args]
    python omicsclaw.py mcp remove <name>
    python omicsclaw.py mcp config
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _configure_stdio_error_handling(*streams: Any) -> None:
    """Avoid hard failures when a terminal cannot encode Unicode output."""
    targets = streams if streams else (sys.stdout, sys.stderr)
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (OSError, ValueError):
            continue

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
DIM = "\033[2m" if _COLOUR else ""
GREEN = "\033[32m" if _COLOUR else ""
YELLOW = "\033[33m" if _COLOUR else ""
BLUE = "\033[34m" if _COLOUR else ""
MAGENTA = "\033[35m" if _COLOUR else ""
RED = "\033[31m" if _COLOUR else ""
CYAN = "\033[36m" if _COLOUR else ""
RESET = "\033[0m" if _COLOUR else ""

_APP_SERVER_INSTALL_HINT = 'pip install -e ".[desktop]"'
_MEMORY_SERVER_INSTALL_HINT = 'pip install -e ".[memory]"'

# ---------------------------------------------------------------------------
# Skills and Domain metadata registry
# ---------------------------------------------------------------------------

if str(OMICSCLAW_DIR) not in sys.path:
    sys.path.insert(0, str(OMICSCLAW_DIR))

from omicsclaw import __version__
from omicsclaw.common.report import (
    build_output_dir_name,
)
from omicsclaw.core.skill_runner import (
    resolve_skill_alias,
    run_skill,
)
from omicsclaw.core.registry import registry
registry.load_all()
SKILLS = registry.skills
DOMAINS = registry.domains

SPATIAL_PIPELINE = [
    "spatial-preprocess",
    "spatial-domains",
    "spatial-de",
    "spatial-genes",
    "spatial-statistics",
]


def _module_available(module_name: str) -> bool:
    """Return True when a Python module is importable in this environment."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def _ensure_server_dependencies(
    *,
    command_name: str,
    requirements: list[tuple[str, str]],
    install_hint: str,
) -> None:
    """Fail fast with a clear install hint for optional server dependencies."""
    missing = [pip_name for module_name, pip_name in requirements if not _module_available(module_name)]
    if not missing:
        return

    print(
        f"{RED}Error:{RESET} `{command_name}` requires optional dependencies that are not installed: "
        f"{', '.join(missing)}",
        file=sys.stderr,
    )
    print(f"Install with: {install_hint}", file=sys.stderr)
    print("Minimal alternative: pip install fastapi uvicorn", file=sys.stderr)
    raise SystemExit(1)


def _oauth_cli_choices() -> list[str]:
    """argparse ``choices`` for the ``auth`` subcommand's provider argument.

    Derived from ``OAUTH_PROVIDERS`` at parser-build time. Falls back to a
    minimal hardcoded set if ccproxy_manager is unavailable (the command
    will then error out gracefully inside the handler).
    """
    try:
        from omicsclaw.core.ccproxy_manager import oauth_cli_aliases
        return oauth_cli_aliases()
    except Exception:
        return ["claude", "anthropic", "openai", "codex"]


def _handle_auth_command(args) -> None:
    """Dispatch ``omicsclaw auth {login,logout,status} [claude|openai]``.

    Thin wrapper over the ``ccproxy`` CLI: we only handle provider-name
    aliasing (``claude`` -> ``claude_api``, ``openai`` -> ``codex``) and a
    multi-provider status view. All OAuth flow logic lives in ccproxy.
    """
    try:
        from omicsclaw.core.ccproxy_manager import (
            OAUTH_PROVIDERS,
            ccproxy_diagnostic_hint,
            ccproxy_executable,
            check_ccproxy_auth,
            get_oauth_provider,
            is_ccproxy_available,
            oauth_install_hint,
        )
    except Exception as exc:
        print(f"{RED}Error importing ccproxy_manager: {exc}{RESET}", file=sys.stderr)
        sys.exit(2)

    if not is_ccproxy_available():
        print(
            f"{RED}ccproxy is not installed (from this Python's perspective).{RESET}",
            file=sys.stderr,
        )
        print(ccproxy_diagnostic_hint(), file=sys.stderr)
        print(f"Install: {CYAN}{oauth_install_hint()}{RESET}", file=sys.stderr)
        sys.exit(2)

    op = getattr(args, "auth_command", None)
    target_alias = getattr(args, "provider", None)

    if op is None:
        print(
            f"Usage: {CYAN}python omicsclaw.py auth [login|logout|status] "
            f"[claude|openai]{RESET}"
        )
        sys.exit(1)

    if op == "status" and not target_alias:
        print(f"\n{BOLD}ccproxy OAuth status{RESET}")
        print(f"{BOLD}{'=' * 50}{RESET}")
        for p in OAUTH_PROVIDERS.values():
            ok, msg = check_ccproxy_auth(p.ccproxy_target)
            mark = f"{GREEN}OK{RESET}" if ok else f"{YELLOW}--{RESET}"
            print(f"  [{mark}] {p.omics_name:<10} {msg}")
        sys.exit(0)

    if not target_alias:
        print(
            f"{RED}Error:{RESET} `{op}` requires a provider "
            f"(one of: claude, openai).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Look up the full provider row from any alias (claude/anthropic/codex/
    # openai/claude_api). get_oauth_provider raises ValueError for unknown
    # aliases — the argparse choices already reject those, but belt-and-
    # braces is cheap here.
    try:
        provider = get_oauth_provider(target_alias)
    except ValueError as exc:
        print(f"{RED}Error:{RESET} {exc}", file=sys.stderr)
        sys.exit(1)

    import subprocess as _sp

    rc = _sp.call([ccproxy_executable(), "auth", op, provider.ccproxy_target])
    sys.exit(rc)

# Canonical workflow order per domain — skills are displayed in this sequence.
# Skills not listed here appear at the end in alphabetical order.
_WORKFLOW_ORDER: dict[str, list[str]] = {
    "spatial": [
        "spatial-preprocess",
        "spatial-integrate",
        "spatial-register",
        "spatial-domains",
        "spatial-annotate",
        "spatial-deconv",
        "spatial-de",
        "spatial-condition",
        "spatial-genes",
        "spatial-statistics",
        "spatial-enrichment",
        "spatial-communication",
        "spatial-trajectory",
        "spatial-velocity",
        "spatial-cnv",
    ],
    "singlecell": [
        "sc-qc",
        "sc-ambient-removal",
        "sc-doublet-detection",
        "sc-filter",
        "sc-preprocessing",
        "sc-batch-integration",
        "sc-cell-annotation",
        "sc-markers",
        "sc-de",
        "sc-pathway-scoring",
        "sc-cell-communication",
        "sc-grn",
        "sc-pseudotime",
        "sc-velocity",
    ],
    "genomics": [
        "genomics-qc",
        "genomics-alignment",
        "genomics-variant-calling",
        "genomics-sv-detection",
        "genomics-cnv-calling",
        "genomics-vcf-operations",
        "genomics-variant-annotation",
        "genomics-assembly",
        "genomics-epigenomics",
        "genomics-phasing",
    ],
    "proteomics": [
        "proteomics-data-import",
        "proteomics-ms-qc",
        "proteomics-identification",
        "proteomics-quantification",
        "proteomics-de",
        "proteomics-ptm",
        "proteomics-enrichment",
        "proteomics-structural",
    ],
    "metabolomics": [
        "metabolomics-xcms-preprocessing",
        "metabolomics-peak-detection",
        "metabolomics-annotation",
        "metabolomics-quantification",
        "metabolomics-normalization",
        "metabolomics-de",
        "metabolomics-pathway-enrichment",
        "metabolomics-statistics",
    ],
    "bulkrna": [
        "bulkrna-read-qc",
        "bulkrna-read-alignment",
        "bulkrna-qc",
        "bulkrna-geneid-mapping",
        "bulkrna-batch-correction",
        "bulkrna-de",
        "bulkrna-splicing",
        "bulkrna-enrichment",
        "bulkrna-deconvolution",
        "bulkrna-coexpression",
        "bulkrna-ppi-network",
        "bulkrna-survival",
        "bulkrna-trajblend",
    ],
}
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

    # 1. 按 domain 分组构建索引（跳过 legacy alias 条目，避免重复显示）
    domain_skills: dict[str, list[tuple[str, dict]]] = {}
    for alias, info in SKILLS.items():
        # Legacy aliases point to the same dict but under a different key; skip them.
        if alias != info.get("alias", alias):
            continue
        d = info.get("domain", "other")
        domain_skills.setdefault(d, []).append((alias, info))

    # 2. 按 DOMAINS 中定义的顺序依次输出
    for domain_key, domain_info in DOMAINS.items():
        if domain_filter and domain_key != domain_filter:
            continue
        skills_in_domain = domain_skills.get(domain_key, [])
        if not skills_in_domain:
            continue

        # Sort skills by canonical workflow order; unlisted skills go to the end.
        order = _WORKFLOW_ORDER.get(domain_key, [])
        order_index = {name: i for i, name in enumerate(order)}
        skills_in_domain.sort(
            key=lambda pair: (order_index.get(pair[0], len(order)), pair[0])
        )

        domain_name = domain_info.get("name", domain_key.title())
        data_types = domain_info.get("primary_data_types", [])
        types_str = ", ".join(f".{t}" if t != "*" else "*" for t in data_types)

        # 领域标题
        print(f"{BOLD}{YELLOW}[{domain_name}]{RESET}  "
              f"{CYAN}[{types_str}]{RESET}")
        print(f"   {'-' * 54}")

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
        print(f"{BOLD}{YELLOW}[Other (Dynamically Discovered)]{RESET}")
        print(f"   {'-' * 54}")
        for alias, info in extra:
            script = info["script"]
            status = f"{GREEN}ready{RESET}" if script.exists() else f"{YELLOW}planned{RESET}"
            desc = info.get("description", "")
            print(f"   {CYAN}{alias:<18}{RESET} [{status}] {desc}")
        print()

    total = sum(1 for a, i in SKILLS.items() if a == i.get("alias", a))
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
# Workspace mode helpers (inspired by EvoScientist --mode / --name design)
# ---------------------------------------------------------------------------

RUNS_DIR = DEFAULT_OUTPUT_ROOT / "runs"


def _deduplicate_run_name(name: str, runs_dir: Path | None = None) -> str:
    """Return *name* if available, otherwise *name_1*, *name_2*, etc."""
    if runs_dir is None:
        runs_dir = RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)
    if not (runs_dir / name).exists():
        return name
    i = 1
    while (runs_dir / f"{name}_{i}").exists():
        i += 1
    return f"{name}_{i}"


def _resolve_workspace(
    workspace_dir: str | None,
    mode: str | None,
    run_name: str | None,
) -> str | None:
    """Resolve the effective workspace directory.

    - ``--workspace <dir>`` always wins (explicit override).
    - ``--mode daemon`` uses workspace_dir or project root (persistent).
    - ``--mode run`` creates an isolated ``output/runs/<name_or_ts>/`` dir.
    - ``--name`` gives the run directory a human-friendly name (only with run mode).
    """
    import os
    import re

    # Validate: --name only with --mode run
    if run_name and mode != "run":
        print(f"{RED}Error: --name can only be used with --mode run{RESET}",
              file=sys.stderr)
        sys.exit(1)

    # Sanitize run name
    if run_name and not re.fullmatch(r"[A-Za-z0-9_-]+", run_name):
        print(f"{RED}Error: --name may only contain letters, digits, hyphens, and underscores{RESET}",
              file=sys.stderr)
        sys.exit(1)

    # Explicit --workspace always wins
    if workspace_dir:
        ws = os.path.abspath(os.path.expanduser(workspace_dir))
        os.makedirs(ws, exist_ok=True)
        return ws

    if mode == "run":
        if run_name:
            session_id = _deduplicate_run_name(run_name)
        else:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        ws = str(RUNS_DIR / session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    if mode == "daemon":
        # Daemon mode: use project root (persistent)
        return str(OMICSCLAW_DIR)

    # No mode specified: return None (let downstream use default)
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class OmicsClawParser(argparse.ArgumentParser):
    """Custom parser for beautiful OmicsClaw CLI help output."""

    def print_help(self, file=None):
        if file is None:
            file = sys.stdout

        print(
            f"\n{BOLD}{CYAN}OmicsClaw{RESET} v{__version__} -- "
            "AI-powered Multi-Omics Analysis Platform\n",
            file=file,
        )
        print(f"{BOLD}Usage:{RESET} oc <command> [options]\n", file=file)

        print(f"{BOLD}{YELLOW}Core Commands{RESET}", file=file)
        print(f"  {GREEN}interactive{RESET}  AI interactive terminal (CLI mode) | Alias: {GREEN}chat{RESET}", file=file)
        print(f"  {GREEN}tui        {RESET}  Advanced full-screen Textual interface", file=file)
        print(f"  {GREEN}list       {RESET}  List all 89 available analysis skills", file=file)
        print(f"  {GREEN}run        {RESET}  Execute a specific skill (e.g., 'oc run preprocess')", file=file)
        print(f"  {GREEN}version    {RESET}  Show the current OmicsClaw version", file=file)

        print(f"\n{BOLD}{BLUE}Utility Commands{RESET}", file=file)
        print(f"  {GREEN}mcp           {RESET}  Manage external Model Context Protocol (MCP) servers", file=file)
        print(f"  {GREEN}doctor        {RESET}  Run environment and runtime diagnostics", file=file)
        print(f"  {GREEN}app-server    {RESET}  Start the desktop/web FastAPI backend for OmicsClaw-App", file=file)
        print(f"  {GREEN}memory-server {RESET}  Start the graph memory REST API server", file=file)
        print(f"  {GREEN}env           {RESET}  Check installed Python dependencies and system tiers", file=file)
        print(f"  {GREEN}onboard       {RESET}  Interactive setup wizard for LLM, runtime, memory, and channels", file=file)
        print(f"  {GREEN}upload        {RESET}  Upload/initialize session from existing .h5ad data", file=file)

        print(f"\n{BOLD}{MAGENTA}Global Options{RESET}", file=file)
        print(f"  {GREEN}-m, --mode {RESET}  Workspace mode: {CYAN}daemon{RESET} (persistent) | {CYAN}run{RESET} (isolated per-session)", file=file)
        print(f"  {GREEN}-n, --name {RESET}  Name for run session directory (requires --mode run)", file=file)
        print(f"  {GREEN}--workspace{RESET}  Override workspace directory for this session", file=file)
        print(f"  {GREEN}-V, --version{RESET}  Show the current OmicsClaw version", file=file)

        print(f"\n{BOLD}For specific command help, use:{RESET} oc <command> --help\n", file=file)

        print(f"{DIM}OmicsClaw project is under active development.{RESET}\n", file=file)


def main():
    _configure_stdio_error_handling()
    # Ensure .env is loaded for all subcommands (memory-server, etc.)
    from omicsclaw.common.runtime_env import load_project_dotenv

    load_project_dotenv(OMICSCLAW_DIR, override=False)

    parser = OmicsClawParser(
        description="OmicsClaw -- Multi-Omics Skills Runner",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"OmicsClaw {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version", help="Show the current OmicsClaw version")

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

    # onboard
    onboard_p = sub.add_parser("onboard", help="Run interactive setup wizard for LLM, runtime, memory, and channel configuration")

    # interactive / chat
    interactive_p = sub.add_parser("interactive", aliases=["chat"], help="Start interactive terminal chat with LLM and skills")
    interactive_p.add_argument("--session", dest="session_id", default=None,
                               help="Resume a saved session by ID (or prefix)")
    interactive_p.add_argument("-p", "--prompt", dest="prompt", default=None,
                               help="Single-shot prompt (non-interactive, print response and exit)")
    interactive_p.add_argument("--ui", choices=["cli", "tui"], default="cli",
                               help="UI backend: cli (default, prompt_toolkit) or tui (Textual full-screen)")
    interactive_p.add_argument("--model", default="", help="Override LLM model name")
    interactive_p.add_argument("--provider", default="", help="Override LLM provider (deepseek, openai, gemini, ...)")
    interactive_p.add_argument("--workspace", dest="workspace_dir", default=None,
                               help="Working directory for this session (default: project root)")
    interactive_p.add_argument("-m", "--mode", dest="mode", default=None,
                               choices=["daemon", "run"],
                               help="Workspace mode: 'daemon' (persistent, default) or 'run' (isolated per-session)")
    interactive_p.add_argument("-n", "--name", dest="run_name", default=None,
                               help="Name for this run session (used as directory name; requires --mode run)")

    # tui
    tui_p = sub.add_parser("tui", help="Start advanced full-screen Textual User Interface")
    tui_p.add_argument("--session", dest="session_id", default=None,
                       help="Resume a saved session by ID")
    tui_p.add_argument("--model", default="", help="Override LLM model name")
    tui_p.add_argument("--provider", default="", help="Override LLM provider")
    tui_p.add_argument("--workspace", dest="workspace_dir", default=None,
                       help="Working directory for this session")
    tui_p.add_argument("-m", "--mode", dest="mode", default=None,
                       choices=["daemon", "run"],
                       help="Workspace mode: 'daemon' (persistent) or 'run' (isolated per-session)")
    tui_p.add_argument("-n", "--name", dest="run_name", default=None,
                       help="Name for this run session (requires --mode run)")

    # mcp — manage external MCP servers
    mcp_p = sub.add_parser("mcp", help="Manage external MCP (Model Context Protocol) servers")
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command")
    # mcp list
    mcp_sub.add_parser("list", help="List configured MCP servers")
    # mcp add
    mcp_add_p = mcp_sub.add_parser("add", help="Add an MCP server")
    mcp_add_p.add_argument("name", help="Server name")
    # NB: positional dest cannot clash with the top-level subparser's
    # ``dest="command"`` — otherwise ``args.command`` is overwritten by the
    # MCP server command string and the ``if args.command == "mcp":`` branch
    # below silently never fires.
    mcp_add_p.add_argument("server_command", help="Command or URL")
    mcp_add_p.add_argument("args", nargs="*", help="Additional args for stdio transport")
    mcp_add_p.add_argument("--transport", choices=["stdio", "http", "sse", "websocket"], default=None)
    mcp_add_p.add_argument("--env", nargs="+", metavar="KEY=VAL", help="Environment variables")
    # mcp remove
    mcp_rm_p = mcp_sub.add_parser("remove", help="Remove an MCP server")
    mcp_rm_p.add_argument("name", help="Server name to remove")
    # mcp config — show config file path
    mcp_sub.add_parser("config", help="Show MCP config file path")

    # auth — manage OAuth login for Claude Pro/Max and OpenAI Codex via ccproxy
    auth_p = sub.add_parser(
        "auth",
        help="Manage OAuth login for Claude Pro/Max and OpenAI Codex (via ccproxy)",
    )
    auth_sub = auth_p.add_subparsers(dest="auth_command")
    for _op in ("login", "logout", "status"):
        _p = auth_sub.add_parser(_op, help=f"{_op.capitalize()} OAuth credentials")
        _p.add_argument(
            "provider",
            nargs="?",
            # Accept any alias of any OAuth-capable provider. Derived from
            # the ``OAUTH_PROVIDERS`` single source of truth in
            # ccproxy_manager, so adding a new row there auto-extends CLI.
            choices=_oauth_cli_choices(),
            help="Target provider (claude|anthropic|openai|codex; omit for `status` to show both)",
        )

    # memory-server — start graph memory REST API
    mem_p = sub.add_parser("memory-server", help="Start the graph memory REST API server")
    mem_p.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    mem_p.add_argument("--port", type=int, default=None, help="Port to bind (default: 8766)")

    app_p = sub.add_parser("app-server", help="Start the desktop/web FastAPI backend for OmicsClaw-App")
    app_p.add_argument("--host", default=None, help="Host to bind (default: 127.0.0.1)")
    app_p.add_argument("--port", type=int, default=None, help="Port to bind (default: 8765)")
    app_p.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode")

    doctor_p = sub.add_parser("doctor", help="Run environment and runtime diagnostics")
    doctor_p.add_argument(
        "--workspace",
        dest="workspace_dir",
        default=None,
        help="Workspace directory to validate (default: current working directory)",
    )

    # knowledge — build / search / stats / list for the knowledge base
    kb_p = sub.add_parser("knowledge", help="Manage the knowledge base (build, search, stats, list)")
    kb_sub = kb_p.add_subparsers(dest="kb_command")
    kb_build = kb_sub.add_parser("build", help="Build or rebuild the knowledge index")
    kb_build.add_argument("--path", dest="kb_path", default=None,
                          help="Path to knowledge_base directory (default: auto-detect)")
    kb_search = kb_sub.add_parser("search", help="Search the knowledge base")
    kb_search.add_argument("query", help="Search query")
    kb_search.add_argument("--domain", default=None, help="Filter by domain")
    kb_search.add_argument("--type", dest="doc_type", default=None, help="Filter by doc type")
    kb_search.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
    kb_stats = kb_sub.add_parser("stats", help="Show knowledge index statistics")
    kb_list = kb_sub.add_parser("list", help="List knowledge topics")
    kb_list.add_argument("--domain", default=None, help="Filter by domain")

    # replot — re-render R Enhanced plots from existing figure_data
    replot_p = sub.add_parser("replot", help="Re-render R Enhanced plots from existing output directory")
    replot_p.add_argument("skill", help="Skill alias (e.g. sc-de)")
    replot_p.add_argument("--output", dest="output_dir", required=True,
                          help="Existing output directory (must contain figure_data/)")
    replot_p.add_argument("--renderer", default=None,
                          help="Specific renderer to run (default: all for this skill)")
    replot_p.add_argument("--list-renderers", action="store_true",
                          help="List available renderers and their parameters, then exit")
    # Plot parameters forwarded as key=value to R
    replot_p.add_argument("--top-n", type=int, dest="top_n")
    replot_p.add_argument("--font-size", type=int, dest="font_size")
    replot_p.add_argument("--width", type=int, dest="width")
    replot_p.add_argument("--height", type=int, dest="height")
    replot_p.add_argument("--palette", type=str, dest="palette")
    replot_p.add_argument("--dpi", type=int, dest="dpi")
    replot_p.add_argument("--title", type=str, dest="title")

    # optimize — autoagent parameter optimization
    opt_p = sub.add_parser("optimize", help="Auto-optimize skill parameters via LLM meta-agent")
    opt_p.add_argument("skill", help="Skill to optimize (e.g. sc-batch-integration)")
    opt_p.add_argument("--input", dest="input_path")
    opt_p.add_argument("--output", dest="output_dir")
    opt_p.add_argument("--method", required=True, help="Method within the skill")
    opt_p.add_argument("--max-trials", type=int, default=20, help="Maximum optimization trials")
    opt_p.add_argument("--provider", default="", help="LLM provider for meta-agent")
    opt_p.add_argument("--llm-model", default="", help="LLM model for meta-agent")
    opt_p.add_argument("--batch-key", default=None)
    opt_p.add_argument("--labels-key", default=None)
    opt_p.add_argument("--demo", action="store_true")

    # run
    run_p = sub.add_parser("run", help="Run a skill")
    run_p.add_argument("skill", help="Skill alias (e.g. preprocess, domains) or 'spatial-pipeline'")
    run_p.add_argument("--demo", action="store_true")
    run_p.add_argument("--input", dest="input_paths", action="append", default=[],
                       metavar="INPUT",
                       help="Input file path (repeat for multi-sample skills, e.g. sc-multi-count)")
    run_p.add_argument("--sample-id", dest="sample_ids", action="append", default=[],
                       metavar="SAMPLE_ID",
                       help="Sample ID label (repeat once per --input for sc-multi-count)")
    run_p.add_argument("--output", dest="output_dir")
    run_p.add_argument("--session", dest="session_path")
    # Skill-specific flags (forwarded to the skill script)
    run_p.add_argument("--data-type", dest="data_type")
    run_p.add_argument("--species")
    run_p.add_argument("--method")
    run_p.add_argument("--n-domains", type=int)
    run_p.add_argument("--resolution", type=str, help="Resolution value or 'auto' for automatic selection")
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
    run_p.add_argument("--no-gpu", "--cpu", action="store_true",
                       help="Force CPU even when GPU is available")
    run_p.add_argument("--use-gpu", action="store_true",
                       help="(deprecated, GPU is now default for capable methods)")
    # cnv-specific
    run_p.add_argument("--window-size", type=int)
    run_p.add_argument("--step", type=int)
    run_p.add_argument("--reference-cat", nargs="+")
    # sc-perturb-specific
    run_p.add_argument("--control", dest="control_label")
    run_p.add_argument("--pert-key", dest="pert_key")
    run_p.add_argument("--split-by", dest="split_by")
    run_p.add_argument("--logfc-threshold", type=float, dest="logfc_threshold")
    run_p.add_argument("--pval-cutoff", type=float, dest="pval_cutoff")
    run_p.add_argument("--perturbation-type", dest="perturbation_type")
    # bulkrna-specific
    run_p.add_argument("--control-prefix", dest="control_prefix")
    run_p.add_argument("--treat-prefix", dest="treat_prefix")
    run_p.add_argument("--padj-cutoff", type=float)
    run_p.add_argument("--lfc-cutoff", type=float)
    run_p.add_argument("--dpsi-cutoff", type=float)
    run_p.add_argument("--gene-set-file")
    run_p.add_argument("--power", type=int)
    run_p.add_argument("--min-module-size", type=int)
    # bulkrna-batch-correction
    run_p.add_argument("--batch-info")
    # bulkrna-ppi-network
    run_p.add_argument("--score-threshold", type=int)
    run_p.add_argument("--top-n", type=int)
    # bulkrna-geneid-mapping
    run_p.add_argument("--from", dest="from_type")
    run_p.add_argument("--to", dest="to_type")
    run_p.add_argument("--on-duplicate")
    run_p.add_argument("--mapping-file")
    # bulkrna-survival
    run_p.add_argument("--clinical")
    run_p.add_argument("--cutoff-method")

    # Use parse_known_args so `run` can pass through skill-specific flags that
    # are not explicitly registered at the top-level CLI parser.
    args, unknown_args = parser.parse_known_args()

    # Only `run` consumes unknown args. All other commands, including
    # `optimize`, must fail fast on unrecognized flags so users do not assume
    # unsupported options were accepted.
    if getattr(args, "command", None) != "run" and unknown_args:
        parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "version":
        print(f"OmicsClaw {__version__}")
        sys.exit(0)

    if args.command == "list":
        list_skills(domain_filter=getattr(args, "domain", None))
        sys.exit(0)

    if args.command == "replot":
        try:
            from skills.singlecell._lib.viz.r import call_r_plot
            from skills.singlecell._lib.viz.r.renderer_params import RENDERER_PARAMS, SKILL_RENDERERS
        except ImportError:
            print(f"{RED}Error:{RESET} R Enhanced plotting dependencies not available.", file=sys.stderr)
            print("Replot is currently supported for single-cell (scRNA) skills only.", file=sys.stderr)
            sys.exit(1)

        skill_alias = resolve_skill_alias(args.skill)

        # --list-renderers: print schema and exit
        if args.list_renderers:
            renderers = SKILL_RENDERERS.get(skill_alias)
            if not renderers:
                print(f"{YELLOW}No R Enhanced renderers registered for '{skill_alias}'.{RESET}")
                sys.exit(0)
            print(f"\n{BOLD}R Enhanced renderers for {CYAN}{skill_alias}{RESET}{BOLD}:{RESET}\n")
            for rname in renderers:
                schema = RENDERER_PARAMS.get(rname, {})
                print(f"  {CYAN}{rname}{RESET}")
                if schema:
                    for pname, pinfo in schema.items():
                        default = pinfo.get("default")
                        default_str = f" (default: {default})" if default is not None else ""
                        print(f"    --{pname.replace('_', '-'):<22} [{pinfo['type']}]{default_str}  {pinfo['desc']}")
                else:
                    print("    (no tunable parameters)")
                print()
            sys.exit(0)

        # Validate output directory
        out_dir = Path(args.output_dir).resolve()
        figure_data_dir = out_dir / "figure_data"
        if not out_dir.exists():
            print(f"{RED}Error:{RESET} output directory does not exist: {out_dir}", file=sys.stderr)
            sys.exit(1)
        if not figure_data_dir.exists():
            print(f"{RED}Error:{RESET} figure_data/ not found in {out_dir}", file=sys.stderr)
            print("Re-run the original skill first to generate figure_data/.", file=sys.stderr)
            sys.exit(1)

        # Determine renderers to run
        all_renderers = SKILL_RENDERERS.get(skill_alias)
        if not all_renderers:
            print(f"{YELLOW}Warning:{RESET} No R Enhanced renderers registered for '{skill_alias}'.")
            sys.exit(0)

        if args.renderer:
            if args.renderer not in all_renderers:
                print(
                    f"{RED}Error:{RESET} Renderer '{args.renderer}' is not registered for '{skill_alias}'.\n"
                    f"Available: {', '.join(all_renderers)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            renderers_to_run = [args.renderer]
        else:
            renderers_to_run = all_renderers

        # Collect plot params from CLI (only set ones)
        plot_params: dict[str, str] = {}
        _replot_param_map = {
            "top_n":     "top_n",
            "font_size": "font_size",
            "width":     "width",
            "height":    "height",
            "palette":   "palette",
            "dpi":       "dpi",
            "title":     "title",
        }
        for attr, param_key in _replot_param_map.items():
            val = getattr(args, attr, None)
            if val is not None:
                plot_params[param_key] = str(val)

        # Run renderers
        r_figures_dir = out_dir / "figures" / "r_enhanced"
        r_figures_dir.mkdir(parents=True, exist_ok=True)

        succeeded: list[str] = []
        failed: list[str] = []

        print(f"\n{BOLD}Replotting {skill_alias} ({len(renderers_to_run)} renderer(s))...{RESET}\n")
        for renderer in renderers_to_run:
            # Determine output filename: reuse original name from SKILL_RENDERERS lookup,
            # or fall back to <renderer>.png
            # We need the filename — import the skill module lazily to get R_ENHANCED_PLOTS
            filename = f"{renderer}.png"
            skill_info = SKILLS.get(skill_alias)
            if skill_info:
                script_path = skill_info.get("script")
                if script_path and Path(script_path).exists():
                    try:
                        import importlib.util as _ilu
                        _spec = _ilu.spec_from_file_location("_skill_mod", str(script_path))
                        _mod = _ilu.module_from_spec(_spec)
                        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
                        r_enhanced_plots = getattr(_mod, "R_ENHANCED_PLOTS", {})
                        if renderer in r_enhanced_plots:
                            filename = r_enhanced_plots[renderer]
                    except Exception:
                        pass  # fall back to default filename

            out_path = r_figures_dir / filename
            print(f"  {DIM}{renderer}{RESET} -> {out_path.name} ...", end=" ", flush=True)
            import warnings as _warnings
            with _warnings.catch_warnings(record=True) as caught:
                _warnings.simplefilter("always")
                call_r_plot(renderer, figure_data_dir, out_path, params=plot_params or None)

            if out_path.exists():
                print(f"{GREEN}ok{RESET}")
                succeeded.append(str(out_path))
            else:
                warn_msg = str(caught[-1].message) if caught else "unknown error"
                print(f"{YELLOW}skipped{RESET}  ({warn_msg[:80]})")
                # Write full error to stderr so bot subprocess can classify it
                print(warn_msg, file=sys.stderr)
                failed.append(renderer)

        print()
        print(f"  {GREEN}{len(succeeded)} succeeded{RESET}", end="")
        if failed:
            print(f"  {YELLOW}{len(failed)} skipped{RESET}: {', '.join(failed)}")
        else:
            print()
        if succeeded:
            print(f"  Figures: {r_figures_dir}")
        # Exit 2 when all renderers failed — signals R env issue to bot
        if failed and not succeeded:
            sys.exit(2)
        sys.exit(0)

    if args.command == "optimize":
        from omicsclaw.autoagent import run_optimization

        # Collect fixed params from CLI flags
        fixed_params = {}
        if getattr(args, "batch_key", None):
            fixed_params["batch_key"] = args.batch_key
        if getattr(args, "labels_key", None):
            fixed_params["labels_key"] = args.labels_key

        def _print_event(event_type: str, data: dict) -> None:
            if event_type == "trial_start":
                params_str = ", ".join(f"{k}={v}" for k, v in data.get("params", {}).items())
                print(f"\n{BOLD}Trial #{data['trial_id']}{RESET}: [{params_str}]")
            elif event_type == "trial_complete":
                status = data.get("status", "")
                score = data.get("score", 0)
                color = GREEN if status in ("keep", "baseline") else RED if status == "discard" else YELLOW
                print(f"  Score: {score:.4f}  Status: {color}{status}{RESET}")
            elif event_type == "reasoning":
                reasoning = data.get("reasoning", "")
                if reasoning:
                    short = reasoning[:120] + ("..." if len(reasoning) > 120 else "")
                    print(f"  {CYAN}Reasoning:{RESET} {short}")
            elif event_type == "progress":
                completed = data.get("completed", 0)
                total = data.get("total", 0)
                best = data.get("best_score", "N/A")
                if isinstance(best, float):
                    best = f"{best:.4f}"
                print(f"  [{completed}/{total}] Best: {best}")
            elif event_type == "done":
                improvement = data.get("improvement_pct", 0)
                print(f"\n{GREEN}{BOLD}Optimization complete!{RESET}")
                print(f"  Improvement: {improvement:+.1f}%")
                best_trial = data.get("best_trial")
                if best_trial:
                    params_str = ", ".join(
                        f"{k}={v}" for k, v in best_trial.get("params", {}).items()
                    )
                    print(f"  Best params: {params_str}")
            elif event_type == "error":
                print(f"{RED}Error:{RESET} {data.get('message', '')}")

        result = run_optimization(
            skill_name=args.skill,
            method=args.method,
            input_path=getattr(args, "input_path", "") or "",
            output_dir=getattr(args, "output_dir", "") or "",
            cwd=os.getcwd(),
            max_trials=args.max_trials,
            fixed_params=fixed_params if fixed_params else None,
            llm_provider=args.provider,
            llm_model=args.llm_model,
            demo=getattr(args, "demo", False),
            on_event=_print_event,
        )

        if not result.get("success"):
            print(f"\n{RED}Optimization failed:{RESET} {result.get('error', 'Unknown error')}")
            sys.exit(1)

        print(f"\n{BOLD}Results saved to:{RESET} {result.get('output_dir', '')}")
        if result.get("reproduce_command"):
            print(f"{BOLD}Reproduce best:{RESET}")
            print(result["reproduce_command"])
        sys.exit(0)

    if args.command == "onboard":
        from bot.onboard import run_onboard
        run_onboard()
        sys.exit(0)

    if args.command in ("interactive", "chat"):
        _mode = getattr(args, "mode", None) or "daemon"
        _run_name = getattr(args, "run_name", None)
        _ws = getattr(args, "workspace_dir", None)
        _ws = _resolve_workspace(_ws, _mode, _run_name)
        from omicsclaw.interactive.interactive import run_interactive
        run_interactive(
            workspace_dir=_ws,
            session_id=getattr(args, "session_id", None),
            model=getattr(args, "model", ""),
            provider=getattr(args, "provider", ""),
            ui_backend=getattr(args, "ui", "cli"),
            prompt=getattr(args, "prompt", None),
            mode=_mode,
            run_name=_run_name,
        )
        sys.exit(0)

    if args.command == "tui":
        _mode = getattr(args, "mode", None) or "daemon"
        _run_name = getattr(args, "run_name", None)
        _ws = getattr(args, "workspace_dir", None)
        _ws = _resolve_workspace(_ws, _mode, _run_name)
        from omicsclaw.interactive.interactive import run_interactive
        run_interactive(
            workspace_dir=_ws,
            session_id=getattr(args, "session_id", None),
            model=getattr(args, "model", ""),
            provider=getattr(args, "provider", ""),
            ui_backend="tui",
            mode=_mode,
            run_name=_run_name,
        )
        sys.exit(0)

    if args.command == "mcp":
        from omicsclaw.interactive._mcp import (
            list_mcp_servers,
            add_mcp_server,
            remove_mcp_server,
            MCP_CONFIG_PATH,
        )
        mcp_cmd = getattr(args, "mcp_command", None) or "list"
        if mcp_cmd == "list":
            servers = list_mcp_servers()
            if not servers:
                print(f"{YELLOW}No MCP servers configured.{RESET}")
                print(f"{CYAN}Add with: oc mcp add <name> <command>{RESET}")
            else:
                print(f"\n{BOLD}MCP Servers{RESET}")
                print(f"{BOLD}{'=' * 50}{RESET}")
                for s in servers:
                    transport = s.get('transport', '?')
                    target = s.get('command') or s.get('url', '?')
                    print(f"  {CYAN}{s['name']:<20}{RESET} [{transport}] {target}")
            sys.exit(0)

        elif mcp_cmd == "add":
            env_dict: dict = {}
            for kv in (getattr(args, "env", None) or []):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    env_dict[k] = v
            try:
                entry = add_mcp_server(
                    args.name, args.server_command,
                    extra_args=args.args or None,
                    transport=getattr(args, "transport", None),
                    env=env_dict or None,
                )
                print(f"{GREEN}Added MCP server:{RESET} {args.name} ({entry['transport']})")
            except Exception as e:
                print(f"{RED}Error:{RESET} {e}", file=sys.stderr)
                sys.exit(1)
            sys.exit(0)

        elif mcp_cmd == "remove":
            from omicsclaw.interactive._mcp import remove_mcp_server
            if remove_mcp_server(args.name):
                print(f"{GREEN}Removed:{RESET} {args.name}")
            else:
                print(f"{RED}Not found:{RESET} {args.name}", file=sys.stderr)
                sys.exit(1)
            sys.exit(0)

        elif mcp_cmd == "config":
            print(f"MCP config file: {CYAN}{MCP_CONFIG_PATH}{RESET}")
            sys.exit(0)

        else:
            print(f"Usage: oc mcp [list|add|remove|config]")
            sys.exit(1)

    if args.command == "auth":
        _handle_auth_command(args)
        return

    if args.command == "memory-server":
        _ensure_server_dependencies(
            command_name="memory-server",
            requirements=[("fastapi", "fastapi"), ("uvicorn", "uvicorn")],
            install_hint=_MEMORY_SERVER_INSTALL_HINT,
        )
        if getattr(args, "host", None):
            os.environ["OMICSCLAW_MEMORY_HOST"] = args.host
        if getattr(args, "port", None):
            os.environ["OMICSCLAW_MEMORY_PORT"] = str(args.port)
        from omicsclaw.memory.server import main as _mem_main
        _mem_main()
        sys.exit(0)

    if args.command == "app-server":
        _ensure_server_dependencies(
            command_name="app-server",
            requirements=[
                ("fastapi", "fastapi"),
                ("uvicorn", "uvicorn"),
                ("nbformat", "nbformat"),
                ("jupyter_client", "jupyter_client"),
                ("ipykernel", "ipykernel"),
            ],
            install_hint=_APP_SERVER_INSTALL_HINT,
        )
        app_args: list[str] = []
        if getattr(args, "host", None):
            app_args.extend(["--host", args.host])
        if getattr(args, "port", None):
            app_args.extend(["--port", str(args.port)])
        if getattr(args, "reload", False):
            app_args.append("--reload")
        from omicsclaw.app.server import main as _app_main
        _app_main(app_args)
        sys.exit(0)

    if args.command == "env":
        from omicsclaw.core.dependency_manager import get_installed_tiers
        tiers = get_installed_tiers()
        
        print(f"\n{BOLD}OmicsClaw Environment Status{RESET}")
        print(f"{BOLD}{'=' * 40}{RESET}")
        
        core_status = f"{GREEN}[ok] Installed{RESET}" if tiers.get("core") else f"{RED}[X] Missing{RESET}"
        print(f"Core System:      {core_status}")
        
        print(f"\n{BOLD}Domain Tiers:{RESET}")
        for tier in ["spatial", "singlecell", "genomics", "proteomics", "metabolomics", "bulkrna"]:
            is_installed = tiers.get(tier, False)
            if is_installed:
                status = f"{GREEN}[ok] Installed{RESET}"
            else:
                status = f"{RED}[X] Missing{RESET} (Run: pip install -e \".[{tier}]\")"
            print(f"- {tier.capitalize():<15} {status}")
            
        print(f"\n{BOLD}Standalone Layer:{RESET}")
        standalone_layers = [
            ("Spatial-Domains",   "spatial-domains",   "Deep learning spatial domain methods, e.g., SpaGCN"),
            ("Spatial-Annotate",  "spatial-annotate",  "Cell type annotation, e.g., Tangram, scANVI"),
            ("Spatial-Deconv",    "spatial-deconv",    "Cell type deconvolution, e.g., Cell2Location, FlashDeconv"),
            ("Spatial-Trajectory","spatial-trajectory","Trajectory inference, e.g., CellRank, Palantir"),
            ("Spatial-Genes",     "spatial-genes",     "Spatially variable genes, e.g., SpatialDE"),
            ("Spatial-Statistics","spatial-statistics","Spatial statistics, e.g., Moran's I, Geary's C"),
            ("Spatial-Condition", "spatial-condition", "Condition comparison, e.g., PyDESeq2 pseudobulk"),
            ("Spatial-Velocity",  "spatial-velocity",  "RNA velocity analysis, e.g., scVelo, VeloVI"),
            ("Spatial-CNV",       "spatial-cnv",       "Copy number variation inference, e.g., inferCNVpy"),
            ("Spatial-Enrichment","spatial-enrichment", "Pathway enrichment, e.g., GSEApy"),
            ("Spatial-Comm",      "spatial-communication", "Cell communication, e.g., LIANA+, CellPhoneDB"),
            ("Spatial-Integrate", "spatial-integrate","Multi-sample integration, e.g., Harmony, BBKNN"),
            ("Spatial-Register",  "spatial-register","Spatial registration, e.g., PASTE"),
            ("BANKSY",            "banksy",            "BANKSY spatial domains (requires numpy<2.0, isolated env)"),
        ]
        for label, tier_key, desc in standalone_layers:
            sl_installed = tiers.get(tier_key, False)
            sl_status = f"{GREEN}[ok] Installed{RESET}" if sl_installed else f"{RED}[X] Missing{RESET} (Run: pip install -e \".[{tier_key}]\")"
            print(f"- {label:<18} {sl_status} ({desc})")
        
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

    if args.command == "doctor":
        from omicsclaw.diagnostics import build_doctor_report, render_doctor_report

        workspace_dir = str(Path(getattr(args, "workspace_dir", None) or Path.cwd()).resolve())
        report = build_doctor_report(
            omicsclaw_dir=str(OMICSCLAW_DIR),
            workspace_dir=workspace_dir,
            output_dir=str(DEFAULT_OUTPUT_ROOT),
        )
        print(render_doctor_report(report, markup=False))
        sys.exit(1 if report.failure_count else 0)

    if args.command == "knowledge":
        from omicsclaw.knowledge import KnowledgeAdvisor
        from pathlib import Path as _Path

        advisor = KnowledgeAdvisor()
        kb_cmd = getattr(args, "kb_command", None) or "stats"

        if kb_cmd == "build":
            kb_path = _Path(args.kb_path) if getattr(args, "kb_path", None) else None
            try:
                stats = advisor.build(kb_path)
                print(f"\n{GREEN}Knowledge base built successfully!{RESET}")
                print(f"  Documents: {stats['documents']}")
                print(f"  Chunks:    {stats['chunks']}")
                print(f"  Database:  {stats['db_path']}")
                print(f"\n{BOLD}By Domain:{RESET}")
                for domain, count in sorted(stats.get("domains", {}).items()):
                    print(f"  {domain:<15} {count}")
                print(f"\n{BOLD}By Type:{RESET}")
                for doc_type, count in sorted(stats.get("types", {}).items()):
                    print(f"  {doc_type:<20} {count}")
            except FileNotFoundError as e:
                print(f"{RED}Error:{RESET} {e}", file=sys.stderr)
                sys.exit(1)

        elif kb_cmd == "search":
            query = args.query
            result = advisor.search_formatted(
                query=query,
                domain=getattr(args, "domain", None),
                doc_type=getattr(args, "doc_type", None),
                limit=getattr(args, "limit", 5),
            )
            print(result)

        elif kb_cmd == "stats":
            stats = advisor.stats()
            if "error" in stats:
                print(f"{YELLOW}{stats['error']}{RESET}")
                print(f"Run: python omicsclaw.py knowledge build")
            else:
                print(f"\n{BOLD}Knowledge Base Statistics{RESET}")
                print(f"{'=' * 40}")
                print(f"  Total documents: {stats['total_documents']}")
                print(f"  Total chunks:    {stats['total_chunks']}")
                print(f"  Database:        {stats['db_path']}")
                print(f"\n{BOLD}By Domain:{RESET}")
                for domain, count in sorted(stats.get("by_domain", {}).items()):
                    print(f"  {domain:<15} {count}")
                print(f"\n{BOLD}By Type:{RESET}")
                for doc_type, count in sorted(stats.get("by_type", {}).items()):
                    print(f"  {doc_type:<20} {count}")

        elif kb_cmd == "list":
            topics = advisor.list_topics(getattr(args, "domain", None))
            if not topics:
                print(f"{YELLOW}No topics found. Run: python omicsclaw.py knowledge build{RESET}")
            else:
                print(f"\n{BOLD}Knowledge Base Topics{RESET} ({len(topics)} documents)")
                print(f"{'=' * 60}")
                current_domain = ""
                for t in topics:
                    d = t.get("domain", "")
                    if d != current_domain:
                        current_domain = d
                        print(f"\n{CYAN}[{d}]{RESET}")
                    dtype = t.get("doc_type", "")
                    title = t.get("title", t.get("source_path", ""))
                    print(f"  [{dtype:<16}] {title}")

        else:
            print("Usage: python omicsclaw.py knowledge [build|search|stats|list]")
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
            # sc-perturb-specific
            "control_label": "--control",
            "pert_key": "--pert-key",
            "split_by": "--split-by",
            "logfc_threshold": "--logfc-threshold",
            "pval_cutoff": "--pval-cutoff",
            "perturbation_type": "--perturbation-type",
            # bulkrna-specific
            "control_prefix": "--control-prefix",
            "treat_prefix": "--treat-prefix",
            "padj_cutoff": "--padj-cutoff",
            "lfc_cutoff": "--lfc-cutoff",
            "dpsi_cutoff": "--dpsi-cutoff",
            "gene_set_file": "--gene-set-file",
            "power": "--power",
            "min_module_size": "--min-module-size",
            # new bulkrna skills
            "batch_info": "--batch-info",
            "score_threshold": "--score-threshold",
            "top_n": "--top-n",
            "from_type": "--from",
            "to_type": "--to",
            "on_duplicate": "--on-duplicate",
            "mapping_file": "--mapping-file",
            "clinical": "--clinical",
            "cutoff_method": "--cutoff-method",
        }
        # flags whose values are file paths — resolve to absolute so subprocess cwd doesn't matter
        _FILE_PATH_FLAGS = {"reference", "reference_slice", "model", "batch_info", "clinical", "mapping_file"}

        for attr, flag in flag_map.items():
            val = getattr(args, attr, None)
            if val is not None:
                if attr in _FILE_PATH_FLAGS:
                    val = str(Path(val).resolve())
                extra.extend([flag, str(val)])

        # boolean flags
        if getattr(args, "refine", False):
            extra.append("--refine")
        if getattr(args, "no_gpu", False):
            extra.append("--no-gpu")
        # nargs="+" args
        if getattr(args, "reference_cat", None):
            extra.extend(["--reference-cat"] + args.reference_cat)

        # Pass through unknown run flags (e.g. newly added skill parameters)
        # and let per-skill allowlists in run_skill() enforce security.
        if unknown_args:
            extra.extend(unknown_args)

        # --sample-id flags (used by sc-multi-count)
        for sid in getattr(args, "sample_ids", []):
            extra.extend(["--sample-id", sid])

        # Resolve single vs multi input
        input_paths_list: list[str] = getattr(args, "input_paths", [])
        single_input = input_paths_list[0] if len(input_paths_list) == 1 else None
        multi_inputs = input_paths_list if len(input_paths_list) >= 2 else None

        result = run_skill(
            args.skill,
            input_path=single_input,
            input_paths=multi_inputs,
            output_dir=args.output_dir,
            demo=args.demo,
            session_path=args.session_path,
            extra_args=extra if extra else None,
        )

        if result["success"]:
            print(f"{GREEN}Success{RESET}: {result['skill']}")
            if result.get("method"):
                print(f"  Method: {result['method']}")
            if result.get("output_dir"):
                print(f"  Output: {result['output_dir']}")
            if result.get("readme_path"):
                print(f"  Guide:  {result['readme_path']}")
            if result.get("notebook_path"):
                print(f"  Notebook: {result['notebook_path']}")
            if result.get("stdout"):
                print(result["stdout"], end="")
        else:
            print(f"{RED}Failed{RESET}: {result['skill']}", file=sys.stderr)
            if result.get("stderr"):
                print(result["stderr"], file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
