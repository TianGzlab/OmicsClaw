"""Common report generation helpers for OmicsClaw skills."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.output_claim import (
    atomic_write_owned_output_text,
    collect_output_claim_identities,
    is_contained_output_path,
    is_scientific_output_file,
)

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "OmicsClaw is a research and educational tool for multi-omics "
    "analysis. It is not a medical device and does not provide clinical diagnoses. "
    "Consult a domain expert before making decisions based on these results."
)


def load_result_json(output_dir: str | Path) -> dict[str, Any] | None:
    """Load ``result.json`` from an output directory if present."""
    output_root = Path(output_dir)
    result_path = output_root / "result.json"
    if not is_scientific_output_file(
        result_path,
        output_root=output_root,
    ):
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
    claim_identities = collect_output_claim_identities(output_dir)
    for path in sorted(output_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if path.name == "README.md" or path.is_symlink() or not is_contained_output_path(
            path,
            output_root=output_dir,
        ):
            continue
        if path.is_file() and not is_scientific_output_file(
            path,
            output_root=output_dir,
            claim_identities=claim_identities,
        ):
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
    replay_path: str | Path | None = None,
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
    report_exists = is_scientific_output_file(
        output_dir / "report.md",
        output_root=output_dir,
    )
    readme_path = output_dir / "README.md"
    replay_rel = ""
    if replay_path:
        try:
            replay_rel = str(Path(replay_path).resolve().relative_to(output_dir.resolve()))
        except ValueError:
            replay_rel = str(replay_path)

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
            f"- Open `{replay_rel}` for the machine-readable replay contract." if replay_rel else "- Replay evidence is not available for this run.",
            "- Browse `figures/` for plots and `tables/` for tabular outputs when present.",
            "- Run `sh reproducibility/replay.sh` to start a fresh, verified replay.",
            "- Inspect `reproducibility/environment.json` for bounded producer-environment evidence.",
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
    atomic_write_owned_output_text(
        readme_path,
        output_root=output_dir,
        text="\n".join(lines) + "\n",
        label="output guide",
    )
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
    """Emit the standard README for callers that already own replay evidence."""
    output_dir = Path(output_dir)
    try:
        write_output_readme(
            output_dir,
            skill_alias=skill_alias,
            description=description,
            result_payload=result_payload,
            preferred_method=preferred_method,
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

    return atomic_write_owned_output_text(
        output_dir / "result.json",
        output_root=output_dir,
        text=json.dumps(envelope, indent=2, default=str),
        label="output ownership metadata",
    )


_RESULT_STATUS_VALUES = frozenset({"ok", "partial", "failed"})

# Sentinel status written by placeholder scaffold scripts (scaffolder.render_skill_script):
# the envelope is shape-valid but the scientific body is unimplemented. The
# promotion / demo smoke gate keys off this to keep a fresh scaffold as ``draft``
# instead of crediting it. It is NOT a run outcome, so ``mark_result_status``
# (which gates real success / failure) deliberately rejects it.
SCAFFOLD_STATUS = "scaffold"


def validate_result_envelope(payload: Any) -> list[str]:
    """Validate a ``result.json`` payload against the standard envelope contract.

    Returns a list of human-readable problems (empty == valid). ``skill``,
    ``version``, and ``completed_at`` must be present as non-empty strings;
    ``input_checksum`` must be present as a string but may be empty (an
    unhashed input is legitimate) — this mirrors exactly what
    :func:`write_result_json` always writes, so any envelope it produces
    passes. ``summary`` and ``data`` are always written as dicts by
    :func:`write_result_json`. A top-level ``status``, when present, must be
    one of the documented run outcomes (``ok`` / ``partial`` / ``failed``) or
    the :data:`SCAFFOLD_STATUS` sentinel that marks an unimplemented
    placeholder. This is the shared contract the ``--demo`` smoke gate reuses to
    decide whether a freshly-created skill earned ``demo-validated`` (it treats a
    ``scaffold`` status as "not a real run" rather than a failure).
    """
    if not isinstance(payload, dict):
        return ["result.json must be a JSON object"]
    problems: list[str] = []
    for key in ("skill", "version", "completed_at"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            problems.append(f"{key} must be a non-empty string")
    checksum = payload.get("input_checksum")
    if not isinstance(checksum, str):
        problems.append("input_checksum must be a string (may be empty)")
    if not isinstance(payload.get("summary"), dict):
        problems.append("summary must be an object")
    if not isinstance(payload.get("data"), dict):
        problems.append("data must be an object")
    status = payload.get("status")
    if status is not None and status not in _RESULT_STATUS_VALUES and status != SCAFFOLD_STATUS:
        allowed = sorted(_RESULT_STATUS_VALUES | {SCAFFOLD_STATUS})
        problems.append(f"status {status!r} is not one of {allowed}")
    return problems


def mark_result_status(
    output_dir: str | Path,
    status: str,
) -> bool:
    """Patch ``result.json`` with a top-level ``status`` field.

    Skills opt in to explicit success/failure signalling by calling this
    helper **as their last step**, after every disk write that would
    affect correctness. The runner reads the field via
    :func:`read_result_status` and uses it to decide success / failure
    instead of relying on the exit code; when no status is present the
    runner falls back to the legacy ``-9 → 0`` heuristic for backward
    compatibility (OMI-12 audit P1 #2).

    Why "last step"? If a skill writes the status early and then crashes,
    ``result.json`` would carry ``status: ok`` from a crashed run and the
    runner would incorrectly report success. Calling this after every
    other write means a crash before the patch leaves the file
    status-less, and the legacy heuristic stays in charge.

    Args:
        output_dir: Skill output directory; the ``result.json`` envelope
            ``write_result_json`` already produced must live here.
        status: One of ``"ok"``, ``"partial"``, or ``"failed"``.

    Returns:
        ``True`` when the field was written; ``False`` when the envelope
        was missing, unreadable, or the status value was rejected. The
        function never raises so callers can tail-call it without an
        exception handler.
    """
    if status not in _RESULT_STATUS_VALUES:
        logger.warning(
            "mark_result_status: ignoring unknown status %r (allowed: %s)",
            status,
            sorted(_RESULT_STATUS_VALUES),
        )
        return False

    output_root = Path(output_dir)
    result_path = output_root / "result.json"
    if not is_scientific_output_file(
        result_path,
        output_root=output_root,
    ):
        return False
    try:
        envelope = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(envelope, dict):
        return False

    envelope["status"] = status
    try:
        atomic_write_owned_output_text(
            result_path,
            output_root=output_root,
            text=json.dumps(envelope, indent=2, default=str),
            label="result status",
        )
    except (OSError, RuntimeError):
        return False
    return True


def read_result_status(output_dir: str | Path) -> str | None:
    """Return the top-level ``status`` field from ``result.json``, or None.

    Only returns one of the documented values (``"ok"``, ``"partial"``,
    ``"failed"``); any other shape is treated as "no status" so the
    runner falls back to its exit-code heuristic.
    """
    envelope = load_result_json(output_dir)
    if not isinstance(envelope, dict):
        return None
    value = envelope.get("status")
    if isinstance(value, str) and value in _RESULT_STATUS_VALUES:
        return value
    return None
