"""Load and validate ``pipelines/<name>.yaml`` chain definitions.

OMI-12 P2.7: pipelines were hard-coded as ``SPATIAL_PIPELINE = [...]`` inside
``pipeline_runner``. Adding a ``singlecell-pipeline`` / ``bulkrna-pipeline``
meant editing Python and recompiling reasoning about which constant to use.
This module loads YAML configs that the runner consumes, so new pipelines
are a one-file drop-in.

Schema (see ``pipelines/spatial-pipeline.yaml``):

    name                   str  required  pipeline alias (must end with ``-pipeline``)
    description            str  optional  one-line summary
    chain_output_basename  str  optional  file the runner looks for in step N's
                                          output dir to feed step N+1 as ``--input``
                                          (default ``processed.h5ad``).
    steps                  list required  ordered list of ``{skill: <alias>}`` dicts

Steps run sequentially; the chain stops at the first failure. Each step's
result is recorded in the final ``pipeline_summary.json`` regardless of how
the chain terminates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from omicsclaw.core.registry import OMICSCLAW_DIR


_DEFAULT_CHAIN_OUTPUT = "processed.h5ad"

# Repository-root ``pipelines/`` directory. Shares the registry's
# ``OMICSCLAW_DIR`` resolution so the ``OMICSCLAW_DIR`` env override that the
# rest of the runtime honours (wheel installs, custom layouts) also routes
# pipeline lookup to the operator's actual data tree.
PIPELINES_DIR = OMICSCLAW_DIR / "pipelines"


@dataclass(frozen=True)
class PipelineStep:
    """One entry in a pipeline chain — currently just a skill alias."""

    skill: str


@dataclass(frozen=True)
class PipelineConfig:
    """In-memory view of a loaded ``pipelines/<name>.yaml`` file."""

    name: str
    description: str
    chain_output_basename: str
    steps: tuple[PipelineStep, ...]

    @property
    def skill_names(self) -> tuple[str, ...]:
        """Convenience: list of skill aliases in run order."""
        return tuple(step.skill for step in self.steps)


class PipelineConfigError(ValueError):
    """Raised when a YAML config is malformed or missing required fields."""


def pipeline_config_path(name: str, *, pipelines_dir: Path | None = None) -> Path:
    """Return the canonical YAML path for a pipeline alias."""
    return (pipelines_dir or PIPELINES_DIR) / f"{name}.yaml"


def load_pipeline_config(
    name: str,
    *,
    pipelines_dir: Path | None = None,
) -> PipelineConfig | None:
    """Load ``pipelines/<name>.yaml``; return ``None`` when the file is absent.

    Validation errors raise ``PipelineConfigError`` — the runner converts those
    into stable error results so an operator typo in the YAML never crashes
    the process.
    """
    path = pipeline_config_path(name, pipelines_dir=pipelines_dir)
    if not path.exists():
        return None

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PipelineConfigError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise PipelineConfigError(f"{path}: top-level must be a mapping")

    config_name = raw.get("name")
    if not isinstance(config_name, str) or not config_name:
        raise PipelineConfigError(f"{path}: ``name`` must be a non-empty string")
    # Catch the silent-rename trap: if the operator renames the file but not
    # the ``name:`` field (or vice versa), the runner's dispatch table will
    # disagree with the config's self-identification.
    if config_name != name:
        raise PipelineConfigError(
            f"{path}: file alias {name!r} does not match ``name: {config_name!r}``"
        )
    if not config_name.endswith("-pipeline"):
        raise PipelineConfigError(
            f"{path}: ``name`` must end with ``-pipeline`` (got {config_name!r})"
        )

    description = raw.get("description", "")
    if not isinstance(description, str):
        raise PipelineConfigError(f"{path}: ``description`` must be a string")

    chain_basename = raw.get("chain_output_basename", _DEFAULT_CHAIN_OUTPUT)
    if not isinstance(chain_basename, str) or not chain_basename:
        raise PipelineConfigError(
            f"{path}: ``chain_output_basename`` must be a non-empty string"
        )

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PipelineConfigError(f"{path}: ``steps`` must be a non-empty list")

    steps: list[PipelineStep] = []
    for idx, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise PipelineConfigError(
                f"{path}: step #{idx} must be a mapping with a ``skill`` key"
            )
        skill = raw_step.get("skill")
        if not isinstance(skill, str) or not skill:
            raise PipelineConfigError(
                f"{path}: step #{idx} ``skill`` must be a non-empty string"
            )
        steps.append(PipelineStep(skill=skill))

    return PipelineConfig(
        name=config_name,
        description=description,
        chain_output_basename=chain_basename,
        steps=tuple(steps),
    )


def list_available_pipelines(*, pipelines_dir: Path | None = None) -> list[str]:
    """Return the alias of every ``*.yaml`` in the pipelines directory."""
    target = pipelines_dir or PIPELINES_DIR
    if not target.exists():
        return []
    return sorted(p.stem for p in target.glob("*.yaml") if p.is_file())
