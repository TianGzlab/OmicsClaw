#!/usr/bin/env python3
"""Tests for sc-drug-response skill."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from anndata import AnnData
from skills._sdk.notebook import load_skill

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_script(name: str, path: Path):
    """Import the skill script at *path* under *name*; its directory name has hyphens."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dr = _load_script("sc_drug_response", Path(__file__).resolve().parent.parent / "sc_drug_response.py")
api = load_skill('sc-drug-response')


def expression():
    genes = sorted({gene for targets in api.builtin_drug_targets().values() for gene in targets})
    result = AnnData(np.random.default_rng(0).random((20, len(genes))))
    result.var_names = genes
    result.obs['cluster'] = ['A'] * 10 + ['B'] * 10
    return result


@pytest.mark.demo
class TestDemoDataGeneration:
    """Test synthetic demo data generation."""

    def test_demo_data_shape(self):
        adata = dr._generate_demo_data()
        assert adata.n_obs == 500
        assert adata.n_vars > 50
        assert "cluster" in adata.obs.columns
        assert adata.obs["cluster"].nunique() == 4

    def test_demo_data_has_umap(self):
        adata = dr._generate_demo_data()
        assert "X_umap" in adata.obsm

    def test_demo_data_has_counts_layer(self):
        adata = dr._generate_demo_data()
        assert "counts" in adata.layers

    def test_demo_data_has_contracts(self):
        adata = dr._generate_demo_data()
        assert "omicsclaw_input_contract" in adata.uns
        assert "omicsclaw_matrix_contract" in adata.uns


class TestSimpleCorrelation:
    """Test simple_correlation method."""

    def test_produces_scores(self):
        adata = expression()
        scores = api.score_drug_targets(adata, cluster_key="cluster")
        assert not scores.empty
        assert "Drug" in scores.columns
        assert "Cluster" in scores.columns
        assert "mean_target_expression" in scores.columns
        assert "Rank" in scores.columns

    def test_scores_have_all_clusters(self):
        adata = expression()
        scores = api.score_drug_targets(adata, cluster_key="cluster")
        expected_clusters = set(adata.obs["cluster"].unique().astype(str))
        actual_clusters = set(scores["Cluster"].unique())
        assert actual_clusters == expected_clusters

    def test_scores_are_numeric(self):
        adata = expression()
        scores = api.score_drug_targets(adata, cluster_key="cluster")
        assert scores["mean_target_expression"].dtype in (np.float64, np.float32, float)
        assert not scores["mean_target_expression"].isna().any()

    def test_ranks_are_correct(self):
        adata = expression()
        scores = api.score_drug_targets(adata, cluster_key="cluster")
        # Within each cluster, rank 1 should have the highest score
        for cluster in scores["Cluster"].unique():
            cluster_df = scores[scores["Cluster"] == cluster]
            max_score_idx = cluster_df["mean_target_expression"].idxmax()
            assert cluster_df.loc[max_score_idx, "Rank"] == 1

    def test_empty_when_no_gene_overlap(self):
        """When no target genes are in the data, result should be empty."""
        adata = expression()
        # Replace all gene names with non-matching names
        adata.var_names = [f"FAKE_GENE_{i}" for i in range(adata.n_vars)]
        scores = api.score_drug_targets(adata, cluster_key="cluster")
        assert scores.empty


@pytest.mark.parametrize('genes', [['BRCA1', 'TP53'], ['Brca1', 'Tp53'], ['brca1', 'tp53']])
def test_gene_case_matching_through_public_score(genes):
    adata = AnnData(np.ones((4, 2)))
    adata.var_names = genes
    table = api.score_drug_targets(adata, drug_targets={'example': ['BRCA1', 'TP53']})
    assert table.loc[0, 'TargetGenes'] == 2
    assert table.loc[0, 'mean_target_expression'] == 1.


@pytest.mark.demo
class TestDemoCadrresScores:
    """Test synthetic CaDRReS score generation."""

    def test_gdsc_scores(self):
        adata = dr._generate_demo_data()
        scores = dr._generate_demo_cadrres_scores(adata, "cluster", "gdsc", 10)
        assert not scores.empty
        assert "Drug" in scores.columns
        assert "Score" in scores.columns
        assert scores["Drug"].nunique() >= 10

    def test_prism_scores(self):
        adata = dr._generate_demo_data()
        scores = dr._generate_demo_cadrres_scores(adata, "cluster", "prism", 10)
        assert not scores.empty
        assert all(d.startswith("BRD-") for d in scores["Drug"].unique())


class TestPreflightCadrres:
    """Test CaDRReS preflight checks."""

    def test_missing_model_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Missing CaDRReS model"):
            dr.preflight_cadrres(tmp_path, "gdsc")

    def test_missing_model_shows_instructions(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not bundled"):
            dr.preflight_cadrres(tmp_path, "gdsc")


class TestPreflightData:
    """Test data preflight checks."""

    def test_missing_cluster_key_raises(self):
        adata = expression()
        with pytest.raises(ValueError, match="not found"):
            dr.preflight_data(adata, "nonexistent_key")


class TestVisualization:
    """Test visualization functions."""

    def test_bar_chart(self, tmp_path):
        scores = pd.DataFrame({
            "Drug": ["DrugA", "DrugA", "DrugB", "DrugB"],
            "Cluster": ["0", "1", "0", "1"],
            "Score": [0.5, 0.3, 0.8, 0.2],
            "Rank": [2, 2, 1, 1],
        })
        path = dr.plot_top_drugs_bar(scores, tmp_path, n_drugs=5)
        assert path is not None
        assert path.exists()

    def test_heatmap(self, tmp_path):
        scores = pd.DataFrame({
            "Drug": ["DrugA", "DrugA", "DrugB", "DrugB"],
            "Cluster": ["0", "1", "0", "1"],
            "Score": [0.5, 0.3, 0.8, 0.2],
            "Rank": [2, 2, 1, 1],
        })
        path = dr.plot_drug_cluster_heatmap(scores, tmp_path)
        assert path is not None
        assert path.exists()

    def test_empty_scores_no_crash(self, tmp_path):
        empty = pd.DataFrame(columns=["Drug", "Cluster", "Score", "Rank"])
        assert dr.plot_top_drugs_bar(empty, tmp_path) is None
        assert dr.plot_drug_cluster_heatmap(empty, tmp_path) is None


@pytest.mark.demo
@pytest.mark.cli_subprocess
class TestEndToEnd:
    """End-to-end test via CLI entry point."""

    def test_demo_mode(self, tmp_path):
        """Full demo run should succeed and produce all expected outputs."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(Path(dr.__file__)),
                "--demo",
                "--output", str(tmp_path / "demo_out"),
                "--method", "simple_correlation",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"STDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
        out_dir = tmp_path / "demo_out"
        assert (out_dir / "processed.h5ad").exists()
        assert (out_dir / "tables" / "drug_rankings.csv").exists()
        assert (out_dir / "report.md").exists()
        assert (out_dir / "result.json").exists()
        assert (out_dir / "figures" / "top_drugs_bar.png").exists()
        assert (out_dir / "figures" / "drug_cluster_heatmap.png").exists()

        # Check result.json structure
        with open(out_dir / "result.json") as f:
            rj = json.load(f)
        assert rj["skill"] == "sc-drug-response"
        assert rj["summary"]["n_drugs_scored"] > 0
        from skills._sdk import report
        report_text = (out_dir / 'report.md').read_text()
        assert report.DISCLAIMER in report_text
        assert 'not correlation or predicted sensitivity' in report_text
        table = pd.read_csv(out_dir / 'tables/drug_rankings.csv')
        assert 'mean_target_expression' in table and 'Score' not in table
