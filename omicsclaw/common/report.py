"""Common report generation helpers for OmicsClaw skills."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.checksums import sha256_file

DISCLAIMER = (
    "OmicsClaw is a research and educational tool for multi-omics "
    "analysis. It is not a medical device and does not provide clinical diagnoses. "
    "Consult a domain expert before making decisions based on these results."
)


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
