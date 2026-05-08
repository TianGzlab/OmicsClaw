"""Shared result model for skill runner adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SkillRunResult:
    """Normalized view over the public ``run_skill()`` result dictionary."""

    skill: str
    success: bool
    exit_code: int
    output_dir: str | None = None
    files: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    method: str | None = None
    readme_path: str = ""
    notebook_path: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def adapter_exit_code(self) -> int:
        """Exit code adapters should expose to job/bot callers."""
        if self.success:
            return self.exit_code
        return self.exit_code if self.exit_code != 0 else 1

    @property
    def combined_output(self) -> str:
        if self.stdout and self.stderr:
            return self.stdout + "\n" + self.stderr
        return self.stdout or self.stderr

    @property
    def output_path(self) -> Path | None:
        return Path(self.output_dir) if self.output_dir else None

    def error_text(self, *, default: str = "unknown error", tail_chars: int | None = None) -> str:
        text = self.stderr or self.stdout or default
        if tail_chars is not None and tail_chars > 0:
            return text[-tail_chars:]
        return text

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return the public dict shape expected by existing ``run_skill`` callers."""
        return {
            "skill": self.skill,
            "success": self.success,
            "exit_code": self.exit_code,
            "output_dir": self.output_dir,
            "files": list(self.files),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "method": self.method,
            "readme_path": self.readme_path,
            "notebook_path": self.notebook_path,
        }


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def coerce_skill_run_result(result: Mapping[str, Any]) -> SkillRunResult:
    """Coerce a runner result mapping into a normalized result model."""
    files = result.get("files") or ()
    if isinstance(files, (str, bytes)):
        file_items: tuple[str, ...] = (str(files),)
    else:
        file_items = tuple(str(item) for item in files)

    skill = str(result.get("skill") or "")
    success = bool(result.get("success", False))
    exit_code = _int_or_default(result.get("exit_code"), 0)
    output_dir_value = result.get("output_dir")
    method_value = result.get("method")
    return SkillRunResult(
        skill=skill,
        success=success,
        exit_code=exit_code,
        output_dir=str(output_dir_value) if output_dir_value else None,
        files=file_items,
        stdout=str(result.get("stdout") or ""),
        stderr=str(result.get("stderr") or ""),
        duration_seconds=_float_or_default(result.get("duration_seconds"), 0.0),
        method=str(method_value) if method_value else None,
        readme_path=str(result.get("readme_path") or ""),
        notebook_path=str(result.get("notebook_path") or ""),
        raw=dict(result),
    )


def result_json_fallback(result: SkillRunResult) -> str:
    """Serialize the original runner mapping for log fallback text."""
    return json.dumps(result.raw, ensure_ascii=False, default=str)


__all__ = ["SkillRunResult", "coerce_skill_run_result", "result_json_fallback"]
