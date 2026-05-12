"""Tests for ``omicsclaw.core.runtime.pipeline_config`` (OMI-12 P2.7).

These pin the YAML schema and the validation errors the loader raises.
The end-to-end runner integration is exercised by
``test_runtime_pipeline_dispatch.py``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from omicsclaw.core.runtime.pipeline_config import (
    PIPELINES_DIR,
    PipelineConfigError,
    list_available_pipelines,
    load_pipeline_config,
    pipeline_config_path,
)


# ---------------------------------------------------------------------------
# Default config — shipped at repo root in ``pipelines/spatial-pipeline.yaml``.
# ---------------------------------------------------------------------------


def test_default_pipelines_dir_resolves_to_repo_root():
    assert PIPELINES_DIR.name == "pipelines"
    assert PIPELINES_DIR.exists(), (
        "pipelines/ must ship with the package — the runner depends on it"
    )


def test_shipped_spatial_pipeline_yaml_loads():
    config = load_pipeline_config("spatial-pipeline")
    assert config is not None
    assert config.name == "spatial-pipeline"
    assert config.chain_output_basename == "processed.h5ad"
    assert config.skill_names == (
        "spatial-preprocess",
        "spatial-domains",
        "spatial-de",
        "spatial-genes",
        "spatial-statistics",
    )


def test_list_available_pipelines_includes_spatial():
    available = list_available_pipelines()
    assert "spatial-pipeline" in available


def test_missing_yaml_returns_none(tmp_path: Path):
    assert load_pipeline_config("nonexistent-pipeline", pipelines_dir=tmp_path) is None


def test_pipeline_config_path_targets_yaml_extension(tmp_path: Path):
    path = pipeline_config_path("foo-pipeline", pipelines_dir=tmp_path)
    assert path == tmp_path / "foo-pipeline.yaml"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, name: str, contents: str) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(textwrap.dedent(contents), encoding="utf-8")
    return path


def test_invalid_yaml_raises(tmp_path: Path):
    _write_yaml(tmp_path, "bad-pipeline", "name: bad-pipeline\nsteps: [oops")
    with pytest.raises(PipelineConfigError, match="invalid YAML"):
        load_pipeline_config("bad-pipeline", pipelines_dir=tmp_path)


def test_top_level_must_be_mapping(tmp_path: Path):
    _write_yaml(tmp_path, "listy-pipeline", "- not\n- a\n- mapping\n")
    with pytest.raises(PipelineConfigError, match="top-level must be a mapping"):
        load_pipeline_config("listy-pipeline", pipelines_dir=tmp_path)


def test_name_must_match_filename(tmp_path: Path):
    """A renamed file with a stale ``name:`` value must fail loudly so the
    dispatcher and the config can't disagree silently."""
    _write_yaml(
        tmp_path,
        "renamed-pipeline",
        """
        name: original-pipeline
        steps:
          - skill: foo
        """,
    )
    with pytest.raises(PipelineConfigError, match="does not match"):
        load_pipeline_config("renamed-pipeline", pipelines_dir=tmp_path)


def test_name_must_end_with_pipeline_suffix(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "missing-suffix",
        """
        name: missing-suffix
        steps:
          - skill: foo
        """,
    )
    with pytest.raises(PipelineConfigError, match="-pipeline"):
        load_pipeline_config("missing-suffix", pipelines_dir=tmp_path)


def test_steps_must_be_non_empty_list(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "empty-pipeline",
        """
        name: empty-pipeline
        steps: []
        """,
    )
    with pytest.raises(PipelineConfigError, match="non-empty list"):
        load_pipeline_config("empty-pipeline", pipelines_dir=tmp_path)


def test_step_requires_skill_key(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "broken-pipeline",
        """
        name: broken-pipeline
        steps:
          - notes: this step has no skill
        """,
    )
    with pytest.raises(PipelineConfigError, match=r"step #0 ``skill``"):
        load_pipeline_config("broken-pipeline", pipelines_dir=tmp_path)


def test_chain_output_basename_default_when_omitted(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "tiny-pipeline",
        """
        name: tiny-pipeline
        steps:
          - skill: foo
        """,
    )
    config = load_pipeline_config("tiny-pipeline", pipelines_dir=tmp_path)
    assert config is not None
    assert config.chain_output_basename == "processed.h5ad"


def test_chain_output_basename_can_be_overridden(tmp_path: Path):
    _write_yaml(
        tmp_path,
        "bulk-pipeline",
        """
        name: bulk-pipeline
        chain_output_basename: counts.csv
        steps:
          - skill: bulkrna-qc
          - skill: bulkrna-de
        """,
    )
    config = load_pipeline_config("bulk-pipeline", pipelines_dir=tmp_path)
    assert config is not None
    assert config.chain_output_basename == "counts.csv"
    assert config.skill_names == ("bulkrna-qc", "bulkrna-de")
