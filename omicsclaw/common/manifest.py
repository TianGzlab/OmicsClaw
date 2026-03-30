"""Pipeline manifest for tracking execution lineage across skills.

Each skill step produces a ``manifest.json`` in its output directory that
records what was run, with what parameters, and what upstream steps preceded
it.  When skills are chained in a pipeline, the manifest accumulates the
full execution history so downstream skills can verify upstream state.

Usage in a skill script::

    from omicsclaw.common.manifest import StepRecord, write_manifest, read_manifest

    record = StepRecord(
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        input_file=str(input_path),
        input_checksum=sha256_file(input_path),
        output_file=str(output_dir / "processed.h5ad"),
        params={"method": "leiden", "resolution": 0.8},
    )
    write_manifest(output_dir, record, upstream_manifest=read_manifest(input_dir))

Usage for validation::

    manifest = read_manifest(input_dir)
    if manifest:
        upstream = manifest.upstream_skills()
        if "spatial-preprocessing" not in upstream:
            logger.warning("Input was not preprocessed by spatial-preprocessing")
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "manifest.json"


@dataclass
class StepRecord:
    """Record of a single skill execution step."""

    skill: str
    version: str
    input_file: str = ""
    input_checksum: str = ""
    output_file: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    completed_at: str = ""

    def __post_init__(self):
        if not self.completed_at:
            self.completed_at = datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineManifest:
    """Ordered execution history for a pipeline run."""

    steps: list[StepRecord] = field(default_factory=list)

    def append(self, record: StepRecord) -> None:
        """Add a new step to the execution history."""
        self.steps.append(record)

    def upstream_skills(self) -> list[str]:
        """Return the ordered list of skill names that have been executed."""
        return [s.skill for s in self.steps]

    def has_skill(self, skill_name: str) -> bool:
        """Check whether a specific skill appears in the execution history."""
        return any(s.skill == skill_name for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [asdict(s) for s in self.steps]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineManifest:
        steps = [StepRecord(**s) for s in data.get("steps", [])]
        return cls(steps=steps)


def write_manifest(
    output_dir: str | Path,
    record: StepRecord,
    upstream: PipelineManifest | None = None,
) -> Path:
    """Write manifest.json to the output directory.

    If *upstream* is provided, the new record is appended to it.
    Otherwise a fresh manifest is created with just this step.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = PipelineManifest(steps=list(upstream.steps)) if upstream else PipelineManifest()
    manifest.append(record)

    path = output_dir / MANIFEST_FILENAME
    path.write_text(json.dumps(manifest.to_dict(), indent=2, default=str))
    return path


def read_manifest(directory: str | Path) -> PipelineManifest | None:
    """Read manifest.json from a directory, returning None if absent."""
    path = Path(directory) / MANIFEST_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PipelineManifest.from_dict(data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
