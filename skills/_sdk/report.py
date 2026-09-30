"""The standard markdown report header and footer, and the reproducibility pin file."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from skills._sdk.checksums import sha256_file

__all__ = ["generate_report_header", "generate_report_footer", "write_repro_requirements"]

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
