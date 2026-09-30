"""Slice 8 — CLI smoke tests with stubbed LLM.

Covers full end-to-end pipeline + every exit code in ADR 0012's
failure semantics table (3 / 4 / 5 / 6 / 7 / 8).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR))


def _make_typed_run_with_real_de(tmp_path: Path, *, include_input_path: bool = True) -> tuple[Path, Path]:
    """Build a typed run pointing at a real synthetic adata so per_cluster_de runs.

    3 clusters × 30 cells × 50 genes; genes 0/1/2 are markers of cluster 0/1/2.
    """
    typed_run_dir = tmp_path / "typed_run"
    typed_run_dir.mkdir(parents=True, exist_ok=True)

    n_per = 30
    n = 3 * n_per
    n_genes = 50
    rng = np.random.default_rng(0)
    X = rng.poisson(0.5, size=(n, n_genes)).astype("float32")
    for cluster in range(3):
        start = cluster * n_per
        end = (cluster + 1) * n_per
        X[start:end, cluster] += rng.poisson(10, size=n_per)

    obs_idx = [f"obs_{i}" for i in range(n)]
    # Mark some real brain marker genes so MarkerDB lookup gets hits.
    var_names = [f"gene_{i}" for i in range(n_genes)]
    var_names[0] = "Aqp4"   # Astrocyte marker (bundled brain DB)
    var_names[1] = "Mbp"    # Oligodendrocyte marker
    var_names[2] = "Pvrl3"  # CA1 pyramidal marker
    adata = ad.AnnData(
        X=X,
        obs=pd.DataFrame(index=obs_idx),
        var=pd.DataFrame(index=var_names),
    )
    adata_path = (tmp_path / "adata.h5ad").resolve()
    adata.write_h5ad(adata_path)

    # consensus_labels: 3 clusters
    pd.DataFrame({
        "observation": obs_idx,
        "consensus_kmode": [i // n_per for i in range(n)],
    }).to_csv(typed_run_dir / "consensus_labels.tsv", sep="\t", index=False)

    pd.DataFrame([
        {"member": "m0", "composite": 0.6, "cross_nmi_mean": 0.65, "intrinsic": 0.55, "max_class_frac": 0.33, "filtered": False, "filter_reason": ""},
        {"member": "m1", "composite": 0.55, "cross_nmi_mean": 0.60, "intrinsic": 0.48, "max_class_frac": 0.33, "filtered": False, "filter_reason": ""},
    ]).to_csv(typed_run_dir / "member_scores.csv", index=False)

    pd.DataFrame(
        [[1.0, 0.45], [0.45, 1.0]],
        index=["m0", "m1"], columns=["m0", "m1"],
    ).to_csv(typed_run_dir / "cross_method_nmi.csv")

    plan: dict[str, object] = {
        "run_id": "smoke_run",
        "operator": "kmode",
        "members": [{"name": "m0"}, {"name": "m1"}],
        "alpha": 0.6, "beta": 0.4, "max_class_frac": 0.8,
    }
    if include_input_path:
        plan["input_path"] = str(adata_path)
    (typed_run_dir / "plan.json").write_text(json.dumps(plan, indent=2))

    return typed_run_dir, adata_path


def _stub_llm_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace annotate_cluster and synthesize_next_steps with deterministic
    stubs that always succeed (and respect invariants)."""
    import consensus_interpret as ci  # type: ignore[import-not-found]
    from _llm import ClusterAnnotation, EvidenceMarker, NextStep  # type: ignore[import-not-found]

    def stub_annotate(cluster_ctx, candidates, **kwargs):
        cell_type = candidates[0].cell_type if candidates else "Unknown"
        markers = []
        if cell_type != "Unknown" and candidates and candidates[0].supporting_markers:
            sm = candidates[0].supporting_markers[0]
            markers = [EvidenceMarker(
                gene=sm.gene, de_rank=sm.de_rank, db_source="stub",
                db_celltype=cell_type, weight=sm.weight,
            )]
        return ClusterAnnotation(
            cluster_id=int(cluster_ctx["cluster_id"]),
            n_cells=int(cluster_ctx["n_cells"]),
            cell_type=cell_type,
            confidence=0.8 if cell_type != "Unknown" else 0.1,
            evidence_markers=markers,
            narrative=f"Cluster {cluster_ctx['cluster_id']} annotated via stub.",
        )

    def stub_next_steps(annotations, nmi_matrix, **kwargs):
        return [NextStep(
            skill="spatial-de",
            args_hint="--groupby consensus_kmode",
            priority=1,
            evidence_refs=["cross_method_nmi.csv:m0,m1=0.45"],
            reason="stubbed",
        )]

    monkeypatch.setattr(ci, "annotate_cluster", stub_annotate)
    monkeypatch.setattr(ci, "synthesize_next_steps", stub_next_steps)


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #

def test_cli_happy_path_produces_5_artifacts_exit_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import consensus_interpret as ci  # type: ignore[import-not-found]

    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)
    _stub_llm_responses(monkeypatch)
    out = tmp_path / "interp_out"

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(out),
        "--tissue", "brain", "--llm",
    ])
    assert rc == 0

    for fname in ("interpreted_report.md", "interpreted_assignments.json",
                  "de_per_cluster.csv", "contradiction_regions.csv", "audit.json"):
        assert (out / fname).exists(), f"missing artifact: {fname}"

    banner = (out / "interpreted_report.md").read_text().splitlines()[0]
    assert banner == "[A+I: Interpreted on verified consensus]"


def test_cli_no_llm_degrade_mode(tmp_path: Path) -> None:
    """--no-llm: skip LLM, write structural report with [I-noLLM: ...] banner."""
    import consensus_interpret as ci  # type: ignore[import-not-found]

    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)
    out = tmp_path / "interp_struct"

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(out),
        "--no-llm",
        # --tissue not required when --no-llm
    ])
    assert rc == 0
    banner = (out / "interpreted_report.md").read_text().splitlines()[0]
    assert banner == "[I-noLLM: Structural patterns only — biology annotation disabled]"
    data = json.loads((out / "interpreted_assignments.json").read_text())
    assert data["banner"] == banner
    assert data["clusters"] == []
    assert data["next_steps"] == []


def test_cli_default_is_structural_only(tmp_path: Path) -> None:
    """Without --llm the run writes the structural report, as --no-llm does."""
    import consensus_interpret as ci  # type: ignore[import-not-found]

    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)
    out = tmp_path / "interp_default"

    rc = ci.main(["--input", str(typed_run_dir), "--output", str(out), "--tissue", "brain"])
    assert rc == 0
    banner = (out / "interpreted_report.md").read_text().splitlines()[0]
    assert banner == "[I-noLLM: Structural patterns only — biology annotation disabled]"


def test_cli_llm_without_a_model_client_exits_6_and_says_so(tmp_path: Path, capsys) -> None:
    """--llm reaches the default model call, which reports that LLM naming is unavailable."""
    import consensus_interpret as ci  # type: ignore[import-not-found]
    from _llm import LLM_UNAVAILABLE  # type: ignore[import-not-found]

    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "llm_off"),
        "--tissue", "brain", "--llm",
    ])
    assert rc == 6
    assert LLM_UNAVAILABLE in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Exit codes — T1 paths                                                       #
# --------------------------------------------------------------------------- #

def test_cli_missing_plan_json_exits_3(tmp_path: Path) -> None:
    import consensus_interpret as ci  # type: ignore[import-not-found]
    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)
    (typed_run_dir / "plan.json").unlink()

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail3"),
        "--tissue", "brain", "--no-llm",
    ])
    assert rc == 3


def test_cli_missing_adata_exits_4(tmp_path: Path) -> None:
    import consensus_interpret as ci  # type: ignore[import-not-found]
    typed_run_dir, adata_path = _make_typed_run_with_real_de(tmp_path)
    adata_path.unlink()

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail4"),
        "--tissue", "brain", "--no-llm",
    ])
    assert rc == 4


def test_cli_unknown_tissue_no_markers_exits_5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import consensus_interpret as ci  # type: ignore[import-not-found]
    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)
    _stub_llm_responses(monkeypatch)

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail5"),
        "--tissue", "totally_made_up", "--llm",
    ])
    assert rc == 5


def test_cli_no_tissue_and_no_markers_with_llm_exits_5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM path requires tissue OR --markers; neither -> exit 5."""
    import consensus_interpret as ci  # type: ignore[import-not-found]
    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)
    _stub_llm_responses(monkeypatch)

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail5b"), "--llm",
    ])
    assert rc == 5


def test_cli_llm_returns_none_exits_6(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default LLM unavailable + --no-llm not set -> exit 6."""
    import consensus_interpret as ci  # type: ignore[import-not-found]
    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)

    # Force annotate_cluster to raise LLMUnavailableError (simulating provider failure).
    from _errors import LLMUnavailableError  # type: ignore[import-not-found]
    def raise_unavailable(*a, **kw):
        raise LLMUnavailableError("simulated provider down")
    monkeypatch.setattr(ci, "annotate_cluster", raise_unavailable)

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail6"),
        "--tissue", "brain", "--llm",
    ])
    assert rc == 6


def test_cli_invariant_violation_exits_7(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM violated marker_grounding -> exit 7."""
    import consensus_interpret as ci  # type: ignore[import-not-found]
    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)

    from _errors import InvariantViolationError  # type: ignore[import-not-found]
    def raise_invariant(*a, **kw):
        raise InvariantViolationError("simulated marker_grounding fail")
    monkeypatch.setattr(ci, "annotate_cluster", raise_invariant)

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail7"),
        "--tissue", "brain", "--llm",
    ])
    assert rc == 7


def test_cli_coverage_below_threshold_exits_8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If < 50% of clusters are interpreted -> exit 8."""
    import consensus_interpret as ci  # type: ignore[import-not-found]
    from _llm import ClusterAnnotation  # type: ignore[import-not-found]
    typed_run_dir, _ = _make_typed_run_with_real_de(tmp_path)

    def all_unknown(cluster_ctx, candidates, **kwargs):
        return ClusterAnnotation(
            cluster_id=int(cluster_ctx["cluster_id"]),
            n_cells=int(cluster_ctx["n_cells"]),
            cell_type="Unknown",
            confidence=0.1,
            evidence_markers=[],
            narrative="Stub returns Unknown for all clusters.",
        )
    monkeypatch.setattr(ci, "annotate_cluster", all_unknown)
    # Don't need synthesize_next_steps; coverage check fires first

    rc = ci.main([
        "--input", str(typed_run_dir),
        "--output", str(tmp_path / "fail8"),
        "--tissue", "brain",
        "--coverage-floor", "0.5", "--llm",
    ])
    assert rc == 8
