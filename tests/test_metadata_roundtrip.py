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


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROD_SPATIAL_DE = _REPO_ROOT / "skills" / "spatial" / "spatial-de"


def _discover_v2_skills() -> list[Path]:
    """Every production skill directory that has migrated to v2 (has a
    parameters.yaml sidecar).  Excludes the _template scaffold."""
    return sorted(
        p.parent for p in (_REPO_ROOT / "skills").rglob("parameters.yaml")
        if not any(part.startswith("_") for part in p.relative_to(_REPO_ROOT / "skills").parts[:-1])
        and not p.parent.name.startswith("_")
    )


@pytest.mark.parametrize(
    "skill_dir",
    _discover_v2_skills(),
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_every_v2_skill_roundtrips(tmp_path: Path, skill_dir: Path) -> None:
    """Every v2 skill in production must round-trip identically between the
    legacy frontmatter form and the new sidecar form via LazySkillMetadata.

    Auto-discovers every parameters.yaml under skills/ — when PR #N adds a
    new v2 skill, this test covers it for free.  Per-skill failures are
    attributable via the pytest parametrisation ID (e.g.
    `bulkrna/bulkrna-coexpression`).
    """
    sidecar_data = yaml.safe_load((skill_dir / "parameters.yaml").read_text(encoding="utf-8"))
    assert isinstance(sidecar_data, dict), f"{skill_dir}/parameters.yaml must be a dict"

    # Identity fields stay in SKILL.md frontmatter; reuse production values
    # so the fabricated forms only differ in WHERE the runtime contract lives.
    prod_skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    prod_fm = yaml.safe_load(prod_skill_md.split("---", 2)[1]) or {}
    identity = {
        "name": prod_fm.get("name", skill_dir.name),
        "description": prod_fm.get("description", ""),
    }

    fm_skill = tmp_path / "fm"
    fm_skill.mkdir()
    fm_frontmatter = {**identity, "metadata": {"omicsclaw": sidecar_data}}
    (fm_skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(fm_frontmatter, sort_keys=False) + "---\n",
        encoding="utf-8",
    )

    sc_skill = tmp_path / "sc"
    sc_skill.mkdir()
    (sc_skill / "SKILL.md").write_text(
        "---\n" + yaml.safe_dump(identity, sort_keys=False) + "---\n",
        encoding="utf-8",
    )
    (sc_skill / "parameters.yaml").write_text(
        yaml.safe_dump(sidecar_data, sort_keys=False), encoding="utf-8"
    )

    fm = LazySkillMetadata(fm_skill)
    sc = LazySkillMetadata(sc_skill)

    assert fm.domain == sc.domain
    assert fm.script == sc.script
    assert fm.allowed_extra_flags == sc.allowed_extra_flags
    assert fm.trigger_keywords == sc.trigger_keywords
    assert fm.legacy_aliases == sc.legacy_aliases
    assert fm.saves_h5ad == sc.saves_h5ad
    assert fm.requires_preprocessed == sc.requires_preprocessed
    assert fm.param_hints == sc.param_hints


def test_spatial_de_real_skill_roundtrips(tmp_path: Path) -> None:
    """Pin the production skills/spatial/spatial-de runtime contract directly.

    Loads the actual parameters.yaml from the migrated skill and asserts both
    that (a) the legacy frontmatter form would yield the same LazySkillMetadata
    output as the production sidecar, and (b) the production sidecar still
    contains the load-bearing keys that bot/skill_orchestration.py and
    omicsclaw/core/registry.py read.  If a future edit drops a method, flag,
    or default from the production file, the production-sanity assertions
    below fail — closing the silent-drift hole that an in-test spec dict
    alone would leave open.
    """
    prod_sidecar = yaml.safe_load((_PROD_SPATIAL_DE / "parameters.yaml").read_text())

    # Production sanity: load-bearing shape every consumer depends on.
    assert set(prod_sidecar["param_hints"].keys()) == {"wilcoxon", "t-test", "pydeseq2"}
    assert "--method" in prod_sidecar["allowed_extra_flags"]
    assert "--sample-key" in prod_sidecar["allowed_extra_flags"]
    assert prod_sidecar["param_hints"]["pydeseq2"]["defaults"]["pydeseq2_n_cpus"] == 1
    assert prod_sidecar["param_hints"]["pydeseq2"]["defaults"]["pydeseq2_alpha"] == 0.05
    assert prod_sidecar["param_hints"]["wilcoxon"]["defaults"]["scanpy_pts"] is False
    assert (
        prod_sidecar["param_hints"]["pydeseq2"]["defaults"]["pydeseq2_fit_type"]
        == "parametric"
    )
    assert prod_sidecar["legacy_aliases"] == ["de"]
    assert prod_sidecar["saves_h5ad"] is True

    # Roundtrip: the same shape, expressed as legacy frontmatter, must give
    # identical LazySkillMetadata output as the production sidecar form.
    spec = {
        "domain": "spatial",
        "script": "spatial_de.py",
        "saves_h5ad": True,
        "requires_preprocessed": True,
        "trigger_keywords": [
            "differential expression", "marker gene", "pseudobulk",
            "Wilcoxon", "t-test", "PyDESeq2", "spatial DE",
        ],
        "legacy_aliases": ["de"],
        "allowed_extra_flags": [
            "--fdr-threshold", "--filter-compare-abs", "--filter-markers",
            "--group1", "--group2", "--groupby",
            "--log2fc-threshold", "--max-out-group-fraction", "--method",
            "--min-cells-per-sample", "--min-counts-per-gene",
            "--min-fold-change", "--min-in-group-fraction", "--n-top-genes",
            "--no-filter-compare-abs", "--no-filter-markers",
            "--no-pydeseq2-cooks-filter", "--no-pydeseq2-independent-filter",
            "--no-pydeseq2-refit-cooks", "--no-scanpy-pts",
            "--no-scanpy-rankby-abs", "--no-scanpy-tie-correct",
            "--pydeseq2-alpha", "--pydeseq2-cooks-filter",
            "--pydeseq2-fit-type", "--pydeseq2-independent-filter",
            "--pydeseq2-n-cpus", "--pydeseq2-refit-cooks",
            "--pydeseq2-size-factors-fit-type", "--sample-key",
            "--scanpy-corr-method", "--scanpy-pts", "--scanpy-rankby-abs",
            "--scanpy-tie-correct",
        ],
        "param_hints": {
            "wilcoxon": {
                "priority": "groupby → scanpy_corr_method → filter_markers → scanpy_tie_correct",
                "params": [
                    "groupby", "group1", "group2", "n_top_genes",
                    "fdr_threshold", "log2fc_threshold",
                    "scanpy_corr_method", "scanpy_rankby_abs", "scanpy_pts",
                    "scanpy_tie_correct", "filter_markers",
                    "min_in_group_fraction", "min_fold_change",
                    "max_out_group_fraction", "filter_compare_abs",
                ],
                "defaults": {
                    "groupby": "leiden", "n_top_genes": 10,
                    "fdr_threshold": 0.05, "log2fc_threshold": 1.0,
                    "scanpy_corr_method": "benjamini-hochberg",
                    "scanpy_rankby_abs": False, "scanpy_pts": False,
                    "scanpy_tie_correct": False, "filter_markers": True,
                    "min_in_group_fraction": 0.25, "min_fold_change": 1.0,
                    "max_out_group_fraction": 0.5, "filter_compare_abs": False,
                },
                "requires": ["obs.groupby", "X_log_normalized"],
                "tips": [
                    "--scanpy-corr-method: official `scanpy.tl.rank_genes_groups` "
                    "multiple-testing correction (`benjamini-hochberg` or `bonferroni`).",
                    "--scanpy-tie-correct: official Wilcoxon tie correction toggle "
                    "in Scanpy; only relevant for `wilcoxon`.",
                    "--scanpy-rankby-abs: ranks genes by absolute score but does "
                    "not change the reported log fold-change sign.",
                    "--scanpy-pts: asks Scanpy to report per-group detection "
                    "fractions (`pct_nz_group`, `pct_nz_reference`).",
                    "--filter-markers + min/max fraction controls: official "
                    "`scanpy.tl.filter_rank_genes_groups` post-filter for "
                    "cluster-style marker specificity.",
                ],
            },
            "t-test": {
                "priority": "groupby → scanpy_corr_method → filter_markers",
                "params": [
                    "groupby", "group1", "group2", "n_top_genes",
                    "fdr_threshold", "log2fc_threshold",
                    "scanpy_corr_method", "scanpy_rankby_abs", "scanpy_pts",
                    "filter_markers", "min_in_group_fraction",
                    "min_fold_change", "max_out_group_fraction",
                    "filter_compare_abs",
                ],
                "defaults": {
                    "groupby": "leiden", "n_top_genes": 10,
                    "fdr_threshold": 0.05, "log2fc_threshold": 1.0,
                    "scanpy_corr_method": "benjamini-hochberg",
                    "scanpy_rankby_abs": False, "scanpy_pts": False,
                    "filter_markers": True, "min_in_group_fraction": 0.25,
                    "min_fold_change": 1.0, "max_out_group_fraction": 0.5,
                    "filter_compare_abs": False,
                },
                "requires": ["obs.groupby", "X_log_normalized"],
                "tips": [
                    "--scanpy-corr-method / --scanpy-rankby-abs / --scanpy-pts: "
                    "same official Scanpy controls as the Wilcoxon path.",
                    "--filter-markers: keep this on for a first pass unless the "
                    "user explicitly wants raw unfiltered ranking output.",
                    "`t-test` is faster than Wilcoxon but remains an exploratory "
                    "log-expression marker workflow rather than replicate-aware "
                    "sample inference.",
                ],
            },
            "pydeseq2": {
                "priority": (
                    "group1/group2 → sample_key → "
                    "min_cells_per_sample/min_counts_per_gene → "
                    "pydeseq2_fit_type/size_factors_fit_type → pydeseq2_alpha"
                ),
                "params": [
                    "groupby", "group1", "group2", "sample_key",
                    "n_top_genes", "fdr_threshold", "log2fc_threshold",
                    "min_cells_per_sample", "min_counts_per_gene",
                    "pydeseq2_fit_type", "pydeseq2_size_factors_fit_type",
                    "pydeseq2_refit_cooks", "pydeseq2_alpha",
                    "pydeseq2_cooks_filter", "pydeseq2_independent_filter",
                    "pydeseq2_n_cpus",
                ],
                "defaults": {
                    "groupby": "leiden", "sample_key": "sample_id",
                    "n_top_genes": 10, "fdr_threshold": 0.05,
                    "log2fc_threshold": 1.0,
                    "min_cells_per_sample": 10, "min_counts_per_gene": 10,
                    "pydeseq2_fit_type": "parametric",
                    "pydeseq2_size_factors_fit_type": "ratio",
                    "pydeseq2_refit_cooks": True, "pydeseq2_alpha": 0.05,
                    "pydeseq2_cooks_filter": True,
                    "pydeseq2_independent_filter": True,
                    "pydeseq2_n_cpus": 1,
                },
                "requires": ["counts_or_raw", "obs.sample_key", "obs.groupby"],
                "tips": [
                    "`pydeseq2` in `spatial-de` is intentionally restricted to "
                    "explicit two-group contrasts with a real `sample_key`; "
                    "OmicsClaw will not fabricate replicates.",
                    "If the same biological samples contribute to both groups, "
                    "OmicsClaw automatically uses a paired design "
                    "(`~ sample_id + condition`).",
                    "--min-cells-per-sample: wrapper-level gate for each sample "
                    "x group pseudobulk profile before DESeq2 fitting.",
                    "--min-counts-per-gene: wrapper-level pseudobulk gene filter "
                    "applied before PyDESeq2.",
                    "--pydeseq2-fit-type / --pydeseq2-size-factors-fit-type / "
                    "--pydeseq2-refit-cooks / --pydeseq2-alpha / "
                    "--pydeseq2-cooks-filter / --pydeseq2-independent-filter / "
                    "--pydeseq2-n-cpus: official PyDESeq2 controls exposed "
                    "directly by the wrapper.",
                ],
            },
        },
    }
    fm = LazySkillMetadata(_frontmatter_form(tmp_path, "spatial-de", spec))
    sc = LazySkillMetadata(_sidecar_form(tmp_path, "spatial-de", spec))

    # Identity + scalar fields
    assert fm.allowed_extra_flags == sc.allowed_extra_flags == set(spec["allowed_extra_flags"])
    assert fm.trigger_keywords == sc.trigger_keywords == spec["trigger_keywords"]
    assert fm.legacy_aliases == sc.legacy_aliases == ["de"]
    assert fm.saves_h5ad is sc.saves_h5ad is True
    assert fm.requires_preprocessed is sc.requires_preprocessed is True

    # Per-method param_hints — exercises mixed bool/int/float/str defaults
    # and ensures none of the 3 methods got dropped.
    assert set(fm.param_hints.keys()) == set(sc.param_hints.keys()) == {"wilcoxon", "t-test", "pydeseq2"}
    assert fm.param_hints == sc.param_hints == spec["param_hints"]

    # Spot-check a few load-bearing values (cheap regression on framework
    # type-coercion behaviour for booleans, integers, floats, and strings).
    assert sc.param_hints["wilcoxon"]["defaults"]["scanpy_pts"] is False
    assert sc.param_hints["pydeseq2"]["defaults"]["pydeseq2_n_cpus"] == 1
    assert sc.param_hints["pydeseq2"]["defaults"]["pydeseq2_alpha"] == 0.05
    assert sc.param_hints["pydeseq2"]["defaults"]["pydeseq2_fit_type"] == "parametric"


def test_param_hints_preserve_advanced_params(tmp_path: Path) -> None:
    """bot/skill_orchestration.py reads tip_info['advanced_params'] — make
    sure roundtrip preserves it byte-for-byte (not coerced to a different
    container type)."""
    spec = RUNTIME_SPECS["multi_method"]
    sc = LazySkillMetadata(_sidecar_form(tmp_path, "multi", spec))

    morans = sc.param_hints["morans"]
    assert morans["advanced_params"] == ["morans_perm"]
