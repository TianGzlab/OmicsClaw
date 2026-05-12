"""Agent-specific tools for the OmicsClaw research pipeline.

Provides:
- ``think_tool`` — structured reflection (from EvoScientist)
- ``tavily_search`` — web search via Tavily (from EvoScientist)
- ``omicsclaw_execute`` — run OmicsClaw analysis skills

These tools are registered in the tool_registry and referenced by name
in config.yaml.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.tools import InjectedToolArg, tool
from typing_extensions import Annotated

logger = logging.getLogger(__name__)

# Module-level workspace directory for resolving relative notebook paths.
# Set by ResearchPipeline before agent execution starts.
_workspace_dir: str | None = None


def set_workspace_dir(path: str) -> None:
    """Register the pipeline workspace directory for notebook path resolution."""
    global _workspace_dir
    _workspace_dir = path


# =============================================================================
# Think tool — adapted from EvoScientist tools/think.py
# =============================================================================


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for structured reflection and strategic decision-making.

    Use this tool to pause and reason carefully at any decision point.
    This creates a deliberate checkpoint for quality thinking.

    When to use:
    - Before starting work: What do I know? What OmicsClaw skills are available?
    - After obtaining results: What did I learn? Does this change the approach?
    - When choosing between methods: What are the trade-offs?
    - When stuck or failing: What went wrong? Is there a fallback method?
    - Before concluding: Is the evidence sufficient?

    Your reflection should address relevant dimensions:
    1. Progress — What has been accomplished? What remains?
    2. Evidence quality — Sufficient for the goal? Gaps to fill?
    3. OmicsClaw skills — Is there a skill that fits the current task?
       Check available skills and use the appropriate one.
    4. Strategy — Continue current approach, adjust, or try something else?
    5. Handoff — Is this phase complete? What does the next agent need?

    Args:
        reflection: Your structured reflection addressing the relevant dimensions

    Returns:
        Confirmation that reflection was recorded
    """
    return f"Reflection recorded: {reflection}"


# =============================================================================
# Web search — adapted from EvoScientist tools/search.py
# =============================================================================

@tool(parse_docstring=True)
async def tavily_search(
    query: str,
    max_results: Annotated[int, InjectedToolArg] = 3,
    topic: Annotated[
        Literal["general", "news", "finance"], InjectedToolArg
    ] = "general",
) -> str:
    """Search the web for information on a given query.

    Uses Tavily to discover relevant URLs, then fetches full webpage
    content as markdown for comprehensive research.

    Args:
        query: Search query to execute

    Returns:
        Formatted search results with webpage content in markdown
    """
    try:
        from omicsclaw.research import search_web_markdown

        return await search_web_markdown(
            query,
            max_results=max_results,
            topic=topic,
        )
    except Exception as e:
        return f"Search failed: {e}"


# =============================================================================
# OmicsClaw skill execution tool
# =============================================================================


@tool(parse_docstring=True)
def omicsclaw_execute(
    skill: str,
    input_path: str = "",
    output_dir: str = "",
    method: str = "",
    demo: bool = False,
    extra_args: str = "",
) -> str:
    """Execute an OmicsClaw analysis skill.

    Runs a registered OmicsClaw skill (e.g., spatial-preprocessing,
    sc-cell-annotation) with the specified parameters.

    Args:
        skill: Name of the OmicsClaw skill to run
        input_path: Path to input data file (h5ad, csv, etc.)
        output_dir: Directory for output files
        method: Analysis method to use (e.g., leiden, tangram, cell2location)
        demo: If True, run with built-in demo data
        extra_args: Additional CLI arguments as a space-separated string

    Returns:
        Skill execution result with output paths and summary
    """
    # Build keyword arguments
    kwargs: dict = {}
    if input_path:
        kwargs["input_path"] = input_path
    if output_dir:
        kwargs["output_dir"] = output_dir
    if demo:
        kwargs["demo"] = True

    # Build extra flags list
    extra: list[str] = []
    if method:
        extra.extend(["--method", method])
    if extra_args:
        import shlex
        extra.extend(shlex.split(extra_args))
    if extra:
        kwargs["extra_args"] = extra

    try:
        from omicsclaw.core.skill_runner import run_skill

        result = run_skill(skill, **kwargs)
        success = result.success
        out_dir = result.output_dir or ""
        stdout = result.stdout
        stderr = result.stderr
        duration = result.duration_seconds

        if success:
            summary = (
                f"✓ Skill '{skill}' completed in {duration:.1f}s\n"
                f"Output: {out_dir}\n"
            )
            if stdout:
                summary += f"\n{stdout[:2000]}"
            return summary
        else:
            return (
                f"✗ Skill '{skill}' failed\n"
                f"Error: {stderr[:1000]}\n"
                f"Stdout: {stdout[:500]}"
            )
    except Exception as e:
        return f"Error executing skill '{skill}': {e}"


# =============================================================================
# Skill search — let coding-agent discover available skills before writing code
# =============================================================================

# Utility names imported from _lib that are NOT core analysis functions.
# skill_search filters these out so coding-agent sees only the important
# callable API (e.g. preprocess, run_de, dispatch_method).
_LIB_UTIL_NAMES: set[str] = {
    # Visualization helpers
    "save_figure", "VizParams", "plot_features", "plot_spatial_stats",
    "plot_integration", "plot_velocity", "plot_trajectory",
    "plot_enrichment", "plot_deconvolution", "plot_communication",
    "plot_cnv", "plot_expression",
    # AnnData helpers
    "store_analysis_metadata", "get_spatial_key",
    # Report helpers (from omicsclaw.common)
    "generate_report_header", "generate_report_footer",
    "write_result_json", "sha256_file",
    # Method config helpers
    "MethodConfig", "validate_method_choice",
    # Dependency check helpers
    "is_available",
    # Validation helpers
    "require", "require_spatial_coords",
    # Data loading (usually not the core analysis step)
    "load_spatial_data",
}


@tool(parse_docstring=True)
def skill_search(
    query: str = "",
    domain: str = "",
) -> str:
    """Search OmicsClaw's skill registry for available analysis functions.

    Use this BEFORE writing notebook code to find if an existing OmicsClaw
    skill can handle the analysis step. Returns matching skills with their
    function signatures and usage examples via load_skill().

    Args:
        query: Keyword to search in skill names and descriptions
            (e.g. 'differential expression', 'clustering', 'QC')
        domain: Optional domain filter (spatial, singlecell, genomics,
            proteomics, metabolomics, bulkrna). If empty, search all.

    Returns:
        Formatted list of matching skills with load_skill() usage
    """
    import ast
    from pathlib import Path

    try:
        from omicsclaw.core.registry import ensure_registry_loaded

        registry = ensure_registry_loaded()

        query_lower = query.lower()
        domain_lower = domain.lower() if domain else ""

        matches = []
        for skill_name, skill_info in registry.skills.items():
            # Domain filter
            if domain_lower and skill_info.get("domain", "") != domain_lower:
                continue

            # Keyword search in name + description
            searchable = f"{skill_name} {skill_info.get('description', '')}".lower()
            if query_lower and query_lower not in searchable:
                continue

            # Scan for public functions — separate core (_lib) from helpers
            script_path = skill_info.get("script")
            core_functions = []    # from _lib imports — the main analysis API
            helper_functions = []  # defined in the script — generate_figures, write_report, etc.
            if script_path and Path(script_path).exists():
                try:
                    source = Path(script_path).read_text(encoding="utf-8")
                    tree = ast.parse(source)
                    seen_names: set[str] = set()

                    # Pass 1: functions DEFINED in the script (helpers)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if (not node.name.startswith("_")
                                    and node.name != "main"
                                    and node.name not in ("get_demo_data", "generate_demo_data")):
                                args = [a.arg for a in node.args.args if a.arg != "self"]
                                sig = f"{node.name}({', '.join(args[:5])}{'...' if len(args) > 5 else ''})"
                                helper_functions.append(sig)
                                seen_names.add(node.name)

                    # Pass 2: core analysis functions IMPORTED from _lib
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            mod_path = node.module or ""
                            if "_lib" not in mod_path:
                                continue
                            for alias in node.names:
                                name = alias.asname or alias.name
                                if (not name.startswith("_")
                                        and name not in _LIB_UTIL_NAMES
                                        and name.upper() != name
                                        and name not in seen_names):
                                    core_functions.append(f"{name}(\u2026)")
                                    seen_names.add(name)
                except Exception:
                    pass

            entry = {
                "name": skill_name,
                "domain": skill_info.get("domain", ""),
                "description": skill_info.get("description", ""),
                "core": core_functions[:6],
                "helpers": helper_functions[:4],
            }
            matches.append(entry)

        if not matches:
            hint = f" in domain '{domain}'" if domain else ""
            return (
                f"No skills found matching '{query}'{hint}.\n"
                f"You should write custom analysis code for this step.\n"
                f"Available domains: spatial, singlecell, genomics, "
                f"proteomics, metabolomics, bulkrna"
            )

        # Format output with load_skill() usage — core functions first
        parts = [f"Found {len(matches)} skill(s) matching '{query or '*'}':"]
        parts.append("")
        parts.append("HOW TO USE: mod = load_skill(\"<skill-name>\"); mod.<function>(<args>)")
        parts.append("")

        for m in matches[:15]:
            parts.append(f"\u2550 **{m['name']}** [{m['domain']}]")
            parts.append(f"  {m['description']}")
            parts.append(f"  mod = load_skill(\"{m['name']}\")")
            if m["core"]:
                for fn in m["core"]:
                    parts.append(f"    \u25b6 mod.{fn}")
            # Show all script-defined functions if no core _lib functions
            funcs_to_show = m["helpers"] if not m["core"] else m["helpers"][:2]
            if funcs_to_show:
                helpers_str = ", ".join(f.split("(")[0] + "()" for f in funcs_to_show)
                parts.append(f"    helpers: {helpers_str}")
            parts.append("")

        if len(matches) > 15:
            parts.append(f"... and {len(matches) - 15} more. Narrow with domain filter.")

        return "\n".join(parts)
    except Exception as e:
        return f"Error searching skills: {e}"


# =============================================================================
# Notebook tools — CellVoyager-inspired notebook execution for coding-agent
# =============================================================================

# Module-level session holder; one session per pipeline run.
_nb_session = None


def _get_or_fail_session():
    """Return the active notebook session or raise."""
    if _nb_session is None:
        raise RuntimeError(
            "No notebook session active. Call notebook_create first."
        )
    return _nb_session


@tool(parse_docstring=True)
def notebook_create(
    notebook_path: str,
    setup_code: str = "",
) -> str:
    """Create a new Jupyter notebook and start a persistent kernel.

    This must be called once before any other notebook_* tools.
    The kernel has OmicsClaw's project root on PYTHONPATH, so skill
    functions can be imported directly (e.g.
    ``from skills.spatial... import preprocess``).

    Args:
        notebook_path: Path for the .ipynb file. If relative, it will be
            placed inside the pipeline's workspace/output directory.
        setup_code: Optional Python code to execute in the first cell
            (e.g. data loading, common imports)

    Returns:
        Confirmation message with notebook path
    """
    from pathlib import Path as _Path

    global _nb_session

    # ── Resolve relative paths to workspace directory ─────────────
    nb_path = _Path(notebook_path)
    if not nb_path.is_absolute():
        if _workspace_dir:
            nb_path = _Path(_workspace_dir) / nb_path
        else:
            # Fallback: use CWD (shouldn't happen if pipeline set workspace)
            nb_path = _Path.cwd() / nb_path
    nb_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path = str(nb_path.resolve())

    # Shutdown previous session if any
    if _nb_session is not None:
        try:
            _nb_session.shutdown()
        except Exception:
            pass

    try:
        from .notebook_session import NotebookSession

        _nb_session = NotebookSession(notebook_path)

        if setup_code.strip():
            result = _nb_session.insert_execute_code_cell(None, setup_code)
            if not result["ok"]:
                return (
                    f"Notebook created at {notebook_path} but setup cell "
                    f"failed:\n{result.get('error', 'unknown error')}"
                )

        return (
            f"✓ Notebook created: {notebook_path}\n"
            f"  Kernel running (python3), PYTHONPATH includes OmicsClaw root.\n"
            f"  Cells: {_nb_session.nb.cells.__len__()}"
        )
    except Exception as e:
        return f"Error creating notebook: {e}"


@tool(parse_docstring=True)
def notebook_add_execute(
    source: str,
    cell_type: str = "code",
    index: int = -1,
    timeout: int | None = None,
) -> str:
    """Insert a cell into the notebook and execute it (if code cell).

    Use this to add analysis steps. Code cells should import and call
    OmicsClaw skill functions directly, e.g.::

        from skills.spatial.spatial_preprocess.spatial_preprocess import preprocess
        adata, summary = preprocess(adata, min_genes=200)
        print(summary)

    For interpretation/documentation, set cell_type='markdown'.

    Args:
        source: The cell source code or markdown text
        cell_type: 'code' (default) or 'markdown'
        index: Position to insert (-1 = append at end)
        timeout: Max wall-clock seconds for code execution. Defaults to OC_NOTEBOOK_TIMEOUT env var or 600s. Use higher values for deep learning methods like Cell2Location (1800-3600s).

    Returns:
        Execution result with output preview or error
    """
    session = _get_or_fail_session()
    idx = None if index < 0 else index

    try:
        if cell_type == "markdown":
            result = session.insert_cell(idx, "markdown", source)
            return (
                f"✓ Markdown cell inserted at index {result['cell_index']}\n"
                f"  Total cells: {result['num_cells']}"
            )
        else:
            result = session.insert_execute_code_cell(idx, source, timeout=timeout)
            status = "✓" if result["ok"] else "✗"
            msg = (
                f"{status} Code cell at index {result['cell_index']} "
                f"[exec #{result.get('execution_count', '?')}]\n"
            )
            if result.get("output_preview"):
                msg += f"Output:\n{result['output_preview']}\n"
            if result.get("error"):
                msg += f"Error:\n{result['error']}\n"
            return msg
    except Exception as e:
        return f"Error: {e}"


@tool(parse_docstring=True)
def notebook_read() -> str:
    """Read the full notebook structure — all cells with source and output previews.

    Use this to understand the current state of the analysis notebook.

    Returns:
        Overview of all cells in the notebook
    """
    session = _get_or_fail_session()

    try:
        info = session.read_notebook()
        parts = [
            f"Notebook: {info['notebook_path']}",
            f"Total cells: {info['num_cells']}",
            "",
        ]
        for cell in info["cells"]:
            marker = "📝" if cell["cell_type"] == "markdown" else "🔢"
            parts.append(
                f"[{cell['index']}] {marker} {cell['cell_type']}"
            )
            parts.append(f"  Source: {cell['source_preview']}")
            if cell["output_preview"]:
                parts.append(f"  Output: {cell['output_preview']}")
            parts.append("")
        return "\n".join(parts)
    except Exception as e:
        return f"Error reading notebook: {e}"


@tool(parse_docstring=True)
def notebook_read_cell(index: int) -> str:
    """Read a single cell's full source and output.

    Use this to inspect detailed execution output, error tracebacks,
    or image indicators from a specific cell.

    Args:
        index: Cell index (0-based)

    Returns:
        Full cell source and output
    """
    session = _get_or_fail_session()

    try:
        info = session.read_cell(index)
        parts = [
            f"Cell [{info['cell_index']}] ({info['cell_type']})",
            f"Execution count: {info.get('execution_count', 'N/A')}",
            "",
            "--- Source ---",
            info["source"],
            "",
            "--- Output ---",
            info.get("output_preview", "(no output)"),
        ]
        return "\n".join(parts)
    except Exception as e:
        return f"Error reading cell {index}: {e}"


# =============================================================================
# Tool registry builder
# =============================================================================


def build_tool_registry() -> dict:
    """Build the tool name → tool object mapping for subagent loading."""
    return {
        "think_tool": think_tool,
        "tavily_search": tavily_search,
        "omicsclaw_execute": omicsclaw_execute,
        "skill_search": skill_search,
        "notebook_create": notebook_create,
        "notebook_add_execute": notebook_add_execute,
        "notebook_read": notebook_read,
        "notebook_read_cell": notebook_read_cell,
    }
