"""Tests for the bulkrna-enrichment skill."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

SKILL_SCRIPT = Path(__file__).resolve().parent.parent / "bulkrna_enrichment.py"


@pytest.fixture
def tmp_output(tmp_path):
    return tmp_path / "enrichment_out"


def test_demo_mode(tmp_output):
    """bulkrna-enrichment --demo should run without error."""
    result = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert (tmp_output / "report.md").exists()
    assert (tmp_output / "result.json").exists()
    assert (tmp_output / "figures").exists()
    assert (tmp_output / "tables" / "enrichment_results.csv").exists()


def test_demo_report_content(tmp_output):
    """Report should contain expected sections."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    report = (tmp_output / "report.md").read_text()
    assert "Enrichment" in report
    assert "Disclaimer" in report


def test_demo_result_json(tmp_output):
    """result.json should contain expected keys."""
    subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--demo", "--output", str(tmp_output)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SKILL_SCRIPT.parent),
    )
    data = json.loads((tmp_output / "result.json").read_text())
    assert data["skill"] == "bulkrna-enrichment"
    assert "summary" in data
    assert data["summary"]["n_terms_tested"] > 0


def test_custom_gene_sets_do_not_silently_use_r_databases(monkeypatch):
    spec = importlib.util.spec_from_file_location("bulkrna_enrichment_test", SKILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    monkeypatch.setattr(
        module,
        "_run_enrichment_r",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("custom gene sets must not enter the R database backend")
        ),
    )
    fake_result = pd.DataFrame(
        {
            "Term": ["HALLMARK_TEST"],
            "Adjusted P-value": [0.01],
            "P-value": [0.001],
            "Genes": ["A;B"],
            "Overlap": ["2/10"],
        }
    )
    observed_kwargs = {}

    def fake_enrichr(**kwargs):
        observed_kwargs.update(kwargs)
        return SimpleNamespace(results=fake_result)

    monkeypatch.setitem(
        sys.modules,
        "gseapy",
        SimpleNamespace(enrichr=fake_enrichr),
    )
    de_df = pd.DataFrame(
        {
            "gene": ["A", "B", "C"],
            "log2FoldChange": [2.0, 2.0, 0.0],
            "pvalue": [0.001, 0.001, 1.0],
            "padj": [0.01, 0.01, 1.0],
        }
    )

    result = module.core_analysis(
        de_df,
        method="ora",
        gene_sets={"HALLMARK_TEST": ["A", "B", "D"]},
    )
    assert result["method_used"] == "ora_gseapy"
    assert result["n_terms_tested"] == 1
    assert set(observed_kwargs["background"]) == {"A", "B", "D"}
    assert result["background_genes"] == 3
    assert result["query_genes_in_background"] == 2


def test_ora_r_does_not_silently_claim_an_unimplemented_backend():
    from skills._sdk.notebook import load_skill
    data = pd.DataFrame({'gene': ['A'], 'log2FoldChange': [2.], 'pvalue': [.001], 'padj': [.01]})
    with pytest.raises(ValueError, match='not implemented'):
        load_skill('bulkrna-enrichment').enrich(data, method='ora_r', gene_sets={'pathway': ['A']})


def test_report_sorts_terms_by_fdr_and_does_not_duplicate_overlap(tmp_path):
    spec = importlib.util.spec_from_file_location("bulkrna_enrichment_report_test", SKILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    summary = {
        "n_input_genes": 10,
        "n_significant": 2,
        "method_used": "ora_gseapy",
        "n_terms_tested": 2,
        "n_enriched_terms": 2,
        "background_genes": 20,
        "query_genes_in_background": 2,
        "enrichment_df": pd.DataFrame(
            {
                "term": ["SECOND", "FIRST"],
                "overlap": ["1/4", "2/3"],
                "term_size": [4, 3],
                "pvalue": [0.02, 0.001],
                "padj": [0.02, 0.01],
            }
        ),
    }

    module.write_report(
        tmp_path,
        summary,
        input_file=None,
        params={"method": "ora", "padj_cutoff": 0.05, "lfc_cutoff": 1.0},
    )
    report = (tmp_path / "report.md").read_text(encoding="utf-8")

    assert report.index("| FIRST |") < report.index("| SECOND |")
    assert "| FIRST | 2/3 |" in report
    assert "2/3/3" not in report
