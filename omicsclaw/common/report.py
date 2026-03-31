"""Common report generation helpers for OmicsClaw skills."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.checksums import sha256_file

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "OmicsClaw is a research and educational tool for multi-omics "
    "analysis. It is not a medical device and does not provide clinical diagnoses. "
    "Consult a domain expert before making decisions based on these results."
)


def load_result_json(output_dir: str | Path) -> dict[str, Any] | None:
    """Load ``result.json`` from an output directory if present."""
    result_path = Path(output_dir) / "result.json"
    if not result_path.exists():
        return None
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def extract_method_name(
    result_payload: dict[str, Any] | None,
    fallback: str | None = None,
) -> str | None:
    """Extract the user-relevant method name from a standard result payload."""
    if not isinstance(result_payload, dict):
        return fallback

    candidates = [
        result_payload.get("summary", {}).get("method"),
        result_payload.get("data", {}).get("params", {}).get("method"),
        result_payload.get("data", {}).get("method"),
        result_payload.get("method"),
        fallback,
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return None


def slugify_output_token(value: str) -> str:
    """Convert free-form method names into stable path-safe tokens."""
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "default"


def build_output_dir_name(
    skill_name: str,
    timestamp: str,
    method: str | None = None,
    unique_suffix: str | None = None,
) -> str:
    """Build a human-readable output directory name.

    Example:
        ``spatial-domain-identification__cellcharter__20260329_063000``
    """
    parts = [slugify_output_token(skill_name)]
    if method:
        parts.append(slugify_output_token(method))
    parts.append(timestamp)
    if unique_suffix:
        parts.append(slugify_output_token(unique_suffix))
    return "__".join(parts)


def _format_scalar(value: Any) -> str:
    """Render a value compactly for markdown summaries."""
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, ensure_ascii=False, default=str)
        return rendered if len(rendered) <= 100 else rendered[:97] + "..."
    return str(value)


def _top_level_entries(output_dir: Path) -> list[str]:
    entries: list[str] = []
    for path in sorted(output_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if path.name == "README.md":
            continue
        suffix = "/" if path.is_dir() else ""
        entries.append(f"`{path.name}{suffix}`")
    return entries


def write_output_readme(
    output_dir: str | Path,
    *,
    skill_alias: str,
    description: str = "",
    result_payload: dict[str, Any] | None = None,
    preferred_method: str | None = None,
    notebook_path: str | Path | None = None,
) -> Path:
    """Write a human-friendly ``README.md`` into an analysis output directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = result_payload or load_result_json(output_dir) or {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    params = {}
    if isinstance(payload, dict):
        data_block = payload.get("data", {})
        params = data_block.get("effective_params") or data_block.get("params", {})
    method = extract_method_name(payload, fallback=preferred_method) or "not recorded"
    completed_at = payload.get("completed_at", "")
    report_exists = (output_dir / "report.md").exists()
    readme_path = output_dir / "README.md"
    notebook_rel = ""
    if notebook_path:
        try:
            notebook_rel = str(Path(notebook_path).resolve().relative_to(output_dir.resolve()))
        except ValueError:
            notebook_rel = str(notebook_path)

    lines = [
        "# OmicsClaw Output Guide",
        "",
        "## Overview",
        "",
        f"- **Skill**: `{skill_alias}`",
        f"- **Method**: `{method}`",
    ]
    internal_skill = payload.get("skill")
    if internal_skill and internal_skill != skill_alias:
        lines.append(f"- **Internal skill id**: `{internal_skill}`")
    if description:
        lines.append(f"- **Purpose**: {description}")
    if completed_at:
        lines.append(f"- **Completed at**: `{completed_at}`")
    lines.extend(
        [
            "",
            "## Start Here",
            "",
            f"- {'Open `report.md` for the narrative report.' if report_exists else 'This run did not generate `report.md`; start from `result.json`.'}",
            "- Open `result.json` to inspect structured summary and parameters.",
            f"- Open `{notebook_rel}` for a code-first walkthrough and rerunnable notebook." if notebook_rel else "- Notebook export is not available for this run.",
            "- Browse `figures/` for plots and `tables/` for tabular outputs when present.",
            "- Use `reproducibility/commands.sh` to rerun with the same settings when available.",
        ]
    )

    if params:
        lines.extend(["", "## Analysis Method And Parameters", ""])
        for key, value in params.items():
            if value is None or value == "":
                continue
            lines.append(f"- `{key}`: {_format_scalar(value)}")

    if summary:
        lines.extend(["", "## Key Results", ""])
        for key, value in summary.items():
            if key == "method":
                continue
            if value is None or value == "":
                continue
            lines.append(f"- `{key}`: {_format_scalar(value)}")

    entries = _top_level_entries(output_dir)
    if entries:
        lines.extend(["", "## Folder Contents", ""])
        for entry in entries:
            lines.append(f"- {entry}")

    lines.extend(["", "## Notes", "", f"- {DISCLAIMER}"])
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return readme_path


def write_repro_requirements(
    output_dir: str | Path,
    packages: list[str],
) -> Path:
    """Write a best-effort pinned requirements file under reproducibility/."""
    output_dir = Path(output_dir)
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    env_lines: list[str] = []
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    for pkg in packages:
        try:
            env_lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue

    req_path = repro_dir / "requirements.txt"
    req_path.write_text("\n".join(env_lines) + ("\n" if env_lines else ""), encoding="utf-8")
    return req_path


def write_standard_run_artifacts(
    output_dir: str | Path,
    *,
    skill_alias: str,
    description: str,
    result_payload: dict[str, Any],
    preferred_method: str | None,
    script_path: str | Path,
    actual_command: list[str],
) -> None:
    """Emit notebook and README artifacts when dependencies allow."""
    output_dir = Path(output_dir)
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=skill_alias,
            description=description,
            result_payload=result_payload,
            preferred_method=preferred_method,
            script_path=Path(script_path).resolve(),
            actual_command=actual_command,
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook for %s: %s", skill_alias, exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=skill_alias,
            description=description,
            result_payload=result_payload,
            preferred_method=preferred_method,
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md for %s: %s", skill_alias, exc)


def generate_report_header(
    title: str,
    skill_name: str,
    input_files: list[Path] | None = None,
    extra_metadata: dict[str, str] | None = None,
) -> str:
    """Generate the standard markdown report header."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    checksums = []
    if input_files:
        for f in input_files:
            f = Path(f)
            if f.exists():
                checksums.append(f"- `{f.name}`: `{sha256_file(f)}`")
            else:
                checksums.append(f"- `{f.name}`: (file not found)")

    lines = [
        f"# {title}",
        "",
        f"**Date**: {now}",
        f"**Skill**: {skill_name}",
    ]
    if extra_metadata:
        for key, val in extra_metadata.items():
            lines.append(f"**{key}**: {val}")
    if checksums:
        lines.append("**Input files**:")
        lines.extend(checksums)
    lines.extend(["", "---", ""])

    return "\n".join(lines)


def generate_report_footer() -> str:
    """Generate the standard markdown report footer with disclaimer."""
    return f"""
---

## Disclaimer

*{DISCLAIMER}*
"""


def write_result_json(
    output_dir: str | Path,
    skill: str,
    version: str,
    summary: dict[str, Any],
    data: dict[str, Any],
    input_checksum: str = "",
    lineage: list[dict[str, Any]] | None = None,
) -> Path:
    """Write the standardized result.json envelope alongside report.md.

    Args:
        lineage: Optional list of upstream step records from a
                 :class:`~omicsclaw.common.manifest.PipelineManifest`.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    envelope: dict[str, Any] = {
        "skill": skill,
        "version": version,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "input_checksum": f"sha256:{input_checksum}" if input_checksum else "",
        "summary": summary,
        "data": data,
    }
    if lineage is not None:
        envelope["lineage"] = lineage

    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(envelope, indent=2, default=str))
    return result_path
