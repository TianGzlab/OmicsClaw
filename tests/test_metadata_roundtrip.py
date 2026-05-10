"""Migration roundtrip: frontmatter form vs sidecar form must agree.

For every production skill we convert, the runtime contract LazySkillMetadata
returns BEFORE migration (frontmatter-only) MUST equal what it returns AFTER
migration (sidecar-only).  This test fabricates both shapes from a single
fixture spec and checks every public field individually so a regression points
at the offending field.

Coverage targets:
  * `param_hints == {}`  (bulkrna-de baseline)
  * single-method `param_hints` (spatial-preprocess "scanpy_standard")
  * multi-method `param_hints` with method-specific flags (spatial-genes)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from omicsclaw.core.lazy_metadata import LazySkillMetadata

# Each spec is the *runtime contract* — the fields that move between
# frontmatter.metadata.omicsclaw and parameters.yaml.  Identity fields (name,
# description) come from frontmatter in both forms.
RUNTIME_SPECS: dict[str, dict] = {
    "empty_param_hints": {
        "domain": "bulkrna",
        "script": "demo.py",
        "saves_h5ad": False,
        "requires_preprocessed": False,
        "trigger_keywords": ["differential expression", "DEGs"],
        "legacy_aliases": ["bulk-de"],
        "allowed_extra_flags": ["--method", "--padj-cutoff"],
        "param_hints": {},
    },
    "single_method": {
        "domain": "spatial",
        "script": "demo.py",
        "saves_h5ad": True,
        "requires_preprocessed": False,
        "trigger_keywords": ["preprocess"],
        "legacy_aliases": [],
        "allowed_extra_flags": ["--tissue", "--n-neighbors"],
        "param_hints": {
            "scanpy_standard": {
                "priority": "tissue -> n_neighbors",
                "params": ["tissue", "n_neighbors"],
                "defaults": {"tissue": "brain", "n_neighbors": 15},
                "requires": ["X_log_normalized"],
                "tips": ["Pick tissue first."],
            }
        },
    },
    "multi_method": {
        "domain": "spatial",
        "script": "demo.py",
        "saves_h5ad": False,
        "requires_preprocessed": True,
        "trigger_keywords": ["svg"],
        "legacy_aliases": ["spatial-svg"],
        "allowed_extra_flags": [
            "--morans-n-neighs",
            "--sparkx-option",
            "--spatialde-no-aeh",
        ],
        "param_hints": {
            "morans": {
                "priority": "morans_n_neighs",
                "params": ["morans_n_neighs"],
                "advanced_params": ["morans_perm"],
                "defaults": {"morans_n_neighs": 6},
                "requires": ["obsm.spatial"],
                "tips": ["Use 6 neighbours for Visium."],
            },
            "sparkx": {
                "priority": "sparkx_option",
                "params": ["sparkx_option"],
                "defaults": {"sparkx_option": "mixture"},
                "requires": ["obsm.spatial"],
                "tips": [],
            },
        },
    },
}


def _frontmatter_form(tmp_path: Path, name: str, spec: dict) -> Path:
    """Write a skill that pins the runtime contract in frontmatter only."""
    skill = tmp_path / f"{name}-fm"
    skill.mkdir()
    frontmatter = {
        "name": name,
        "description": "Load when test.",
        "version": "0.0.1",
        "metadata": {"omicsclaw": dict(spec)},
    }
    (skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n",
        encoding="utf-8",
    )
    return skill


def _sidecar_form(tmp_path: Path, name: str, spec: dict) -> Path:
    """Write a skill that pins the runtime contract in parameters.yaml only."""
    skill = tmp_path / f"{name}-sc"
    skill.mkdir()
    frontmatter = {
        "name": name,
        "description": "Load when test.",
        "version": "0.0.1",
    }
    (skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\n",
        encoding="utf-8",
    )
    (skill / "parameters.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False), encoding="utf-8"
    )
    return skill


@pytest.mark.parametrize("name,spec", list(RUNTIME_SPECS.items()))
def test_runtime_contract_roundtrips(tmp_path: Path, name: str, spec: dict) -> None:
    fm = LazySkillMetadata(_frontmatter_form(tmp_path, name, spec))
    sc = LazySkillMetadata(_sidecar_form(tmp_path, name, spec))

    # Identity fields stay in frontmatter — they should be identical.
    assert fm.name == sc.name == name
    assert fm.description == sc.description

    # Every runtime field must match between the two forms.
    assert fm.domain == sc.domain, "domain"
    assert fm.script == sc.script, "script"
    assert fm.saves_h5ad == sc.saves_h5ad, "saves_h5ad"
    assert fm.requires_preprocessed == sc.requires_preprocessed, "requires_preprocessed"
    assert fm.trigger_keywords == sc.trigger_keywords, "trigger_keywords"
    assert fm.legacy_aliases == sc.legacy_aliases, "legacy_aliases"
    assert fm.allowed_extra_flags == sc.allowed_extra_flags, "allowed_extra_flags"
    assert fm.param_hints == sc.param_hints, "param_hints"


def test_bulkrna_de_real_skill_roundtrips(tmp_path: Path) -> None:
    """Fixture mirroring the production skills/bulkrna/bulkrna-de runtime
    contract.  If a future maintainer changes the bulkrna-de sidecar in a way
    that diverges from the legacy frontmatter, this test fails — guarding
    PR #1's pilot migration permanently."""
    spec = {
        "domain": "bulkrna",
        "script": "bulkrna_de.py",
        "saves_h5ad": False,
        "requires_preprocessed": False,
        "trigger_keywords": [
            "differential expression", "DE analysis", "DESeq2",
            "volcano plot", "fold change", "DEGs", "bulk DE",
        ],
        "legacy_aliases": ["bulk-de"],
        "allowed_extra_flags": [
            "--control-prefix", "--lfc-cutoff", "--method",
            "--padj-cutoff", "--treat-prefix",
        ],
        "param_hints": {},
    }
    fm = LazySkillMetadata(_frontmatter_form(tmp_path, "bulkrna-de", spec))
    sc = LazySkillMetadata(_sidecar_form(tmp_path, "bulkrna-de", spec))
    assert fm.allowed_extra_flags == sc.allowed_extra_flags == set(spec["allowed_extra_flags"])
    assert fm.trigger_keywords == sc.trigger_keywords == spec["trigger_keywords"]
    assert fm.legacy_aliases == sc.legacy_aliases == spec["legacy_aliases"]
    assert fm.param_hints == sc.param_hints == {}


def test_sc_de_real_skill_roundtrips(tmp_path: Path) -> None:
    """Fixture mirroring the production skills/singlecell/scrna/sc-de runtime
    contract — the first migrated skill with non-trivial param_hints.  All 5
    methods (wilcoxon, t-test, logreg, mast, deseq2_r) are pinned so a
    future edit that drops or renames any method is caught.  Exercises the
    per-field-merge path on a realistically complex shape."""
    spec = {
        "domain": "singlecell",
        "script": "sc_de.py",
        "saves_h5ad": True,
        "requires_preprocessed": True,
        "trigger_keywords": [
            "differential expression", "marker genes", "de analysis",
            "wilcoxon", "pseudo-bulk",
        ],
        "legacy_aliases": [],
        "allowed_extra_flags": [
            "--celltype-key", "--group1", "--group2", "--groupby",
            "--log2fc-threshold", "--logreg-solver", "--method",
            "--n-top-genes", "--padj-threshold",
            "--pseudobulk-min-cells", "--pseudobulk-min-counts",
            "--r-enhanced", "--sample-key",
        ],
        "param_hints": {
            "wilcoxon": {
                "priority": "groupby -> n_top_genes -> group1/group2",
                "params": ["groupby", "n_top_genes", "group1", "group2"],
                "advanced_params": ["padj_threshold", "log2fc_threshold"],
                "defaults": {
                    "groupby": "leiden", "n_top_genes": 10,
                    "padj_threshold": 0.05, "log2fc_threshold": 1.0,
                },
                "requires": ["preprocessed_anndata", "scanpy"],
                "tips": ["--method wilcoxon: Default exploratory marker-ranking path."],
            },
            "t-test": {
                "priority": "groupby -> n_top_genes -> group1/group2",
                "params": ["groupby", "n_top_genes", "group1", "group2"],
                "advanced_params": ["padj_threshold", "log2fc_threshold"],
                "defaults": {
                    "groupby": "leiden", "n_top_genes": 10,
                    "padj_threshold": 0.05, "log2fc_threshold": 1.0,
                },
                "requires": ["preprocessed_anndata", "scanpy"],
                "tips": ["--method t-test: Parametric alternative to Wilcoxon."],
            },
            "logreg": {
                "priority": "groupby -> logreg_solver -> n_top_genes",
                "params": ["groupby", "logreg_solver", "n_top_genes"],
                "advanced_params": ["padj_threshold", "log2fc_threshold"],
                "defaults": {
                    "groupby": "leiden", "logreg_solver": "lbfgs",
                    "n_top_genes": 10, "padj_threshold": 0.05,
                    "log2fc_threshold": 1.0,
                },
                "requires": ["preprocessed_anndata", "scanpy"],
                "tips": [
                    "--method logreg: Logistic-regression ranking, useful when "
                    "you want genes that best separate one group from the others."
                ],
            },
            "mast": {
                "priority": "groupby -> group1/group2 -> n_top_genes",
                "params": ["groupby", "group1", "group2", "n_top_genes"],
                "advanced_params": ["padj_threshold", "log2fc_threshold"],
                "defaults": {
                    "groupby": "leiden", "n_top_genes": 10,
                    "padj_threshold": 0.05, "log2fc_threshold": 1.0,
                },
                "requires": ["R_MAST_stack", "log_normalized_expression_matrix"],
                "tips": [
                    "--method mast: R-backed MAST hurdle-model path on "
                    "log-normalized expression."
                ],
            },
            "deseq2_r": {
                "priority": "groupby -> group1/group2 -> sample_key -> celltype_key",
                "params": ["groupby", "group1", "group2", "sample_key", "celltype_key"],
                "advanced_params": [
                    "pseudobulk_min_cells", "pseudobulk_min_counts",
                    "padj_threshold", "log2fc_threshold",
                ],
                "defaults": {
                    "sample_key": "sample_id", "celltype_key": "cell_type",
                    "pseudobulk_min_cells": 10, "pseudobulk_min_counts": 1000,
                    "padj_threshold": 0.05, "log2fc_threshold": 1.0,
                },
                "requires": [
                    "raw_counts_or_raw_layer",
                    "biological_replicates",
                    "R_DESeq2_stack",
                ],
                "tips": [
                    "--method deseq2_r: Sample-aware pseudobulk path.",
                    "--group1 and --group2 are required for the DESeq2 path.",
                ],
            },
        },
    }
    fm = LazySkillMetadata(_frontmatter_form(tmp_path, "sc-de", spec))
    sc = LazySkillMetadata(_sidecar_form(tmp_path, "sc-de", spec))
    assert fm.allowed_extra_flags == sc.allowed_extra_flags == set(spec["allowed_extra_flags"])
    assert fm.trigger_keywords == sc.trigger_keywords == spec["trigger_keywords"]
    assert fm.saves_h5ad is sc.saves_h5ad is True
    assert fm.requires_preprocessed is sc.requires_preprocessed is True
    # Per-method param_hints — exercise advanced_params on multiple methods.
    assert fm.param_hints == sc.param_hints == spec["param_hints"]
    assert sc.param_hints["wilcoxon"]["advanced_params"] == ["padj_threshold", "log2fc_threshold"]
    assert sc.param_hints["deseq2_r"]["defaults"]["pseudobulk_min_cells"] == 10


def test_param_hints_preserve_advanced_params(tmp_path: Path) -> None:
    """bot/skill_orchestration.py reads tip_info['advanced_params'] — make
    sure roundtrip preserves it byte-for-byte (not coerced to a different
    container type)."""
    spec = RUNTIME_SPECS["multi_method"]
    sc = LazySkillMetadata(_sidecar_form(tmp_path, "multi", spec))

    morans = sc.param_hints["morans"]
    assert morans["advanced_params"] == ["morans_perm"]
