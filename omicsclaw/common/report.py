"""Common report generation helpers for OmicsClaw skills."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.checksums import sha256_file

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
) -> Path:
    """Write a human-friendly ``README.md`` into an analysis output directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = result_payload or load_result_json(output_dir) or {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    params = payload.get("data", {}).get("params", {}) if isinstance(payload, dict) else {}
    method = extract_method_name(payload, fallback=preferred_method) or "not recorded"
    completed_at = payload.get("completed_at", "")
    report_exists = (output_dir / "report.md").exists()
    readme_path = output_dir / "README.md"

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
            "- Browse `figures/` for plots and `tables/` for tabular outputs when present.",
            "- Use `reproducibility/commands.sh` to rerun with the same settings when available.",
        ]
    )

    if params:
        lines.extend(["", "## Analysis Method And Parameters", ""])
        for key, value in params.items():
            lines.append(f"- `{key}`: {_format_scalar(value)}")

    if summary:
        lines.extend(["", "## Key Results", ""])
        for key, value in summary.items():
            if key == "method":
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
