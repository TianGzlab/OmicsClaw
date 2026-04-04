"""Notebook export helpers for standard OmicsClaw analysis outputs."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

try:
    import nbformat as nbf
    from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook
    _NBFORMAT_AVAILABLE = True
except ImportError:
    nbf = None  # type: ignore[assignment]
    _NBFORMAT_AVAILABLE = False

from omicsclaw.common.report import extract_method_name, load_result_json

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAX_EMBEDDED_TEXT = 20000


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _trim_text(text: str, limit: int = _MAX_EMBEDDED_TEXT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 17] + "\n\n...[truncated]..."


def _shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def _visible_files(paths: list[Path], base_dir: Path, limit: int = 12) -> list[str]:
    return [str(path.relative_to(base_dir)) for path in sorted(paths)[:limit]]


def _read_requirements_bundle(repro_dir: Path) -> str:
    """Read the best available environment description from reproducibility output."""
    for filename in ("requirements.txt", "environment.txt"):
        text = _read_text(repro_dir / filename)
        if text:
            return text
    return ""


def _find_primary_h5ad(output_dir: Path) -> Path | None:
    """Return the most likely AnnData output for notebook inspection."""
    preferred = [
        output_dir / "processed.h5ad",
        output_dir / "processed.h5ad",
    ]
    for path in preferred:
        if path.exists():
            return path

    h5ad_files = sorted(output_dir.glob("*.h5ad"))
    if h5ad_files:
        return h5ad_files[0]
    return None


def write_analysis_notebook(
    output_dir: str | Path,
    *,
    skill_alias: str,
    description: str = "",
    result_payload: dict[str, Any] | None = None,
    preferred_method: str | None = None,
    script_path: str | Path | None = None,
    actual_command: list[str] | None = None,
) -> Path:
    """Create a reproducibility notebook for a completed analysis run."""
    if not _NBFORMAT_AVAILABLE:
        import warnings
        warnings.warn("nbformat is not installed; skipping notebook export.", stacklevel=2)
        return Path(output_dir) / "reproducibility" / f"{skill_alias}_analysis.ipynb"
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    notebook_path = repro_dir / "analysis_notebook.ipynb"

    payload = result_payload or load_result_json(output_dir) or {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    params = {}
    if isinstance(payload, dict):
        data_block = payload.get("data", {})
        params = data_block.get("effective_params") or data_block.get("params", {})
    method = extract_method_name(payload, fallback=preferred_method) or "not recorded"
    report_text = _trim_text(_read_text(output_dir / "report.md"))
    commands_text = _trim_text(_read_text(repro_dir / "commands.sh"))
    requirements_text = _trim_text(_read_requirements_bundle(repro_dir))
    figure_paths = [p for p in (output_dir / "figures").glob("*") if p.is_file()] if (output_dir / "figures").exists() else []
    table_paths = [p for p in (output_dir / "tables").glob("*") if p.is_file()] if (output_dir / "tables").exists() else []
    primary_h5ad = _find_primary_h5ad(output_dir)
    params_json = json.dumps(params, indent=2, ensure_ascii=False, default=str)
    actual_cmd_str = _shell_join(actual_command) if actual_command else ""
    script_path_str = str(Path(script_path).resolve()) if script_path else ""

    overview_lines = [
        "# OmicsClaw Analysis Notebook",
        "",
        "This notebook was auto-generated from a standard OmicsClaw analysis run.",
        "",
        f"- **Skill**: `{skill_alias}`",
        f"- **Method**: `{method}`",
        f"- **Output directory**: `{output_dir}`",
    ]
    if description:
        overview_lines.append(f"- **Purpose**: {description}")
    if payload.get("completed_at"):
        overview_lines.append(f"- **Completed at**: `{payload['completed_at']}`")
    if script_path_str:
        overview_lines.append(f"- **Skill script**: `{script_path_str}`")

    key_file_lines = [
        "## Key Files",
        "",
        "- `report.md`: narrative report",
        "- `result.json`: machine-readable summary and parameters",
        "- `reproducibility/commands.sh`: shell rerun command",
        "- `reproducibility/analysis_notebook.ipynb`: this notebook",
    ]
    if primary_h5ad is not None:
        key_file_lines.append(f"- `{primary_h5ad.name}`: primary AnnData output for downstream analysis")
    if figure_paths:
        key_file_lines.append(f"- `figures/`: {len(figure_paths)} generated figure(s)")
    if table_paths:
        key_file_lines.append(f"- `tables/`: {len(table_paths)} generated table(s)")

    nb = new_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
            "omicsclaw": {
                "skill": skill_alias,
                "method": method,
                "output_dir": str(output_dir),
            },
        }
    )

    nb.cells.append(new_markdown_cell("\n".join(overview_lines)))
    nb.cells.append(new_markdown_cell("\n".join(key_file_lines)))

    if report_text:
        nb.cells.append(
            new_markdown_cell(
                "## Report Snapshot\n\n"
                "The current `report.md` content is embedded below for quick reading.\n\n"
                + report_text
            )
        )

    nb.cells.append(
        new_markdown_cell(
            "## Structured Summary\n\n"
            "The next cells let you inspect the structured outputs, understand the skill module, "
            "and rerun the analysis from inside Jupyter."
        )
    )

    nb.cells.append(
        new_code_cell(
            f"""from pathlib import Path
import importlib.util
import inspect
import json
import shlex
import subprocess
import sys

PROJECT_ROOT = Path({json.dumps(str(_PROJECT_ROOT))})
OUTPUT_DIR = Path({json.dumps(str(output_dir))})
REPRO_DIR = OUTPUT_DIR / "reproducibility"
RESULT_PATH = OUTPUT_DIR / "result.json"
REPORT_PATH = OUTPUT_DIR / "report.md"
COMMANDS_PATH = REPRO_DIR / "commands.sh"
REQUIREMENTS_PATH = REPRO_DIR / "requirements.txt"
SKILL_NAME = {json.dumps(skill_alias)}
METHOD = {json.dumps(method)}
SKILL_SCRIPT = Path({json.dumps(script_path_str)}) if {json.dumps(bool(script_path_str))} else None
PRIMARY_H5AD_PATH = Path({json.dumps(str(primary_h5ad))}) if {json.dumps(primary_h5ad is not None)} else None

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def load_skill(name: str):
    from omicsclaw.core.registry import registry

    registry.load_all()
    info = registry.skills.get(name)
    if not info:
        raise ValueError(f"Unknown skill: {{name}}")
    script = Path(info["script"])
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

print("Notebook ready for:", SKILL_NAME, "| method:", METHOD)
print("Output directory:", OUTPUT_DIR)
"""
        )
    )

    nb.cells.append(
        new_code_cell(
            """result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
print("Summary keys:", sorted(result.get("summary", {}).keys()))
result["summary"]
"""
        )
    )

    nb.cells.append(
        new_code_cell(
            f"""params = json.loads({json.dumps(params_json)})
params
"""
        )
    )

    nb.cells.append(
        new_code_cell(
            """skill_module = load_skill(SKILL_NAME)
print("Skill module file:", skill_module.__file__)
public_callables = sorted(
    name
    for name in dir(skill_module)
    if not name.startswith("_") and callable(getattr(skill_module, name))
)
public_callables[:40]
"""
        )
    )

    nb.cells.append(
        new_code_cell(
            """def preview_function(name: str, max_chars: int = 4000):
    src = inspect.getsource(getattr(skill_module, name))
    print(src[:max_chars] + ("\\n... [truncated]" if len(src) > max_chars else ""))

# Example:
# preview_function("main")
"""
        )
    )

    nb.cells.append(
        new_code_cell(
            f"""ACTUAL_RUN_COMMAND = {json.dumps(actual_cmd_str)}
COMMAND_TEMPLATE = {json.dumps(commands_text)}

print("Actual command captured for this run:\\n")
print(ACTUAL_RUN_COMMAND or "<not recorded>")

if COMMAND_TEMPLATE:
    print("\\nTemplate command from reproducibility/commands.sh:\\n")
    print(COMMAND_TEMPLATE)

# Uncomment to rerun after reviewing the command:
# subprocess.run(ACTUAL_RUN_COMMAND, shell=True, check=True)
"""
        )
    )

    if requirements_text:
        nb.cells.append(
            new_code_cell(
                f"""print({json.dumps(requirements_text)})
"""
            )
        )

    if primary_h5ad is not None:
        nb.cells.append(
            new_code_cell(
                """import scanpy as sc

adata = sc.read_h5ad(PRIMARY_H5AD_PATH)
print("Loaded AnnData from:", PRIMARY_H5AD_PATH)
print(adata)
adata
"""
            )
        )

    if figure_paths:
        nb.cells.append(
            new_code_cell(
                """from IPython.display import Image, display

fig_dir = OUTPUT_DIR / "figures"
for figure_path in sorted(fig_dir.glob("*")):
    if figure_path.is_file():
        print(figure_path.name)
        display(Image(filename=str(figure_path)))
"""
            )
        )

    if table_paths:
        nb.cells.append(
            new_code_cell(
                """import pandas as pd

tables_dir = OUTPUT_DIR / "tables"
table_paths = sorted(p for p in tables_dir.glob("*") if p.is_file())
[p.name for p in table_paths]
"""
            )
        )

    nb.cells.append(
        new_markdown_cell(
            "## Notebook Notes\n\n"
            f"- Embedded figures: {', '.join(_visible_files(figure_paths, output_dir)) or 'none'}\n"
            f"- Embedded tables: {', '.join(_visible_files(table_paths, output_dir)) or 'none'}\n"
            "- This notebook is intentionally generic so every OmicsClaw skill can emit it without custom code.\n"
            "- If you need a deeper function-level workflow, use `skill_module.__file__` and `preview_function(...)` above."
        )
    )

    with notebook_path.open("w", encoding="utf-8") as handle:
        nbf.write(nb, handle)
    return notebook_path
