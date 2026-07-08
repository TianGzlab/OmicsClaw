"""Tests for the sc-geo-download skill."""

from __future__ import annotations

import gzip
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pandas as pd
import pytest
import yaml


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_SCRIPT = SKILL_DIR / "sc_geo_download.py"


# ---------------------------------------------------------------------------
# Scaffold sanity
# ---------------------------------------------------------------------------


def test_scaffold_files_exist():
    """The skill bundle has the files OmicsClaw expects."""
    assert (SKILL_DIR / "SKILL.md").exists()
    assert (SKILL_DIR / "sc_geo_download.py").exists()
    assert (SKILL_DIR / "parameters.yaml").exists()
    for ref in ("methodology.md", "output_contract.md", "parameters.md", "r_visualization.md"):
        assert (SKILL_DIR / "references" / ref).exists(), f"missing references/{ref}"


def test_parameters_yaml_is_complete():
    """parameters.yaml carries the runtime contract fields the contract test requires."""
    params = yaml.safe_load((SKILL_DIR / "parameters.yaml").read_text())
    assert params["domain"] == "singlecell"
    assert params["script"] == "sc_geo_download.py"
    assert params["saves_h5ad"] is False
    assert params["requires_preprocessed"] is False
    assert params["input_required"] is False
    assert "--accession" in params["allowed_extra_flags"]
    assert "--pubmed-id" in params["allowed_extra_flags"]
    assert "--no-include-supp" in params["allowed_extra_flags"]
    assert isinstance(params["param_hints"], dict)


# ---------------------------------------------------------------------------
# Pure-Python unit tests (no subprocess, no network)
# ---------------------------------------------------------------------------


def _import_skill():
    """Import sc_geo_download as a module for white-box unit tests."""
    sys.path.insert(0, str(SKILL_DIR))
    try:
        import sc_geo_download
        return sc_geo_download
    finally:
        sys.path.pop(0)


@pytest.mark.parametrize("accession,expected_bucket", [
    ("GSE109564", "GSE109nnn"),
    ("GSE149689", "GSE149nnn"),
    ("GSE12345",  "GSE12nnn"),
    ("GSE1234",   "GSE1nnn"),
    ("GSE123",    "GSEnnn"),
])
def test_url_builder_matches_ncbi_convention(accession, expected_bucket):
    mod = _import_skill()
    url = mod._build_geo_dir_url(accession)
    assert url == f"https://ftp.ncbi.nlm.nih.gov/geo/series/{expected_bucket}/{accession}"


def test_list_directory_files_parses_ncbi_autoindex(monkeypatch):
    """`_list_directory_files` must extract file links from NCBI's Apache
    autoindex HTML, skipping the parent-dir link and external footer links."""
    mod = _import_skill()

    fake_html = """
    <html><body>
    <a href="/geo/series/GSE109nnn/GSE109564/">Parent Directory</a>
    <a href="GSE109564-GPL16791_series_matrix.txt.gz">…</a>
    <a href="GSE109564-GPL18573_series_matrix.txt.gz">…</a>
    <a href="https://www.hhs.gov/vulnerability-disclosure-policy/index.html">VDP</a>
    </body></html>
    """

    class _FakeResp:
        status_code = 200
        text = fake_html
        def raise_for_status(self): pass

    class _FakeSession:
        def get(self, url, timeout):
            return _FakeResp()

    files = mod._list_directory_files(_FakeSession(), "https://example/matrix/", timeout=10)
    assert files == [
        "GSE109564-GPL16791_series_matrix.txt.gz",
        "GSE109564-GPL18573_series_matrix.txt.gz",
    ]


def test_list_directory_files_returns_empty_on_404(monkeypatch):
    mod = _import_skill()

    class _Resp404:
        status_code = 404
        def raise_for_status(self):
            import requests
            raise requests.HTTPError(response=self)

    class _Sess:
        def get(self, url, timeout):
            return _Resp404()

    assert mod._list_directory_files(_Sess(), "https://example/missing/", timeout=10) == []


def test_extract_raw_tar_groups_by_gsm(tmp_path):
    """`_extract_raw_tar` must drop each member into samples/<GSM>/ by prefix."""
    mod = _import_skill()
    tar_path = tmp_path / "fake_RAW.tar"
    with tarfile.open(tar_path, "w") as tar:
        for name, data in (
            ("GSM001_matrix.mtx.gz", b"matrix-001"),
            ("GSM001_barcodes.tsv.gz", b"barcodes-001"),
            ("GSM002_matrix.mtx.gz", b"matrix-002"),
            ("misc_README.txt", b"hello"),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    out = tmp_path / "out"
    extracted = mod._extract_raw_tar(tar_path, into=out)
    assert (out / "GSM001" / "GSM001_matrix.mtx.gz").exists()
    assert (out / "GSM001" / "GSM001_barcodes.tsv.gz").exists()
    assert (out / "GSM002" / "GSM002_matrix.mtx.gz").exists()
    assert (out / "_misc" / "misc_README.txt").exists()
    assert len(extracted) == 4


# ---------------------------------------------------------------------------
# Demo-mode end-to-end (no network)
# ---------------------------------------------------------------------------


def _run(args, tmp_path):
    out_dir = tmp_path / "out"
    cmd = [sys.executable, str(SKILL_SCRIPT), "--output", str(out_dir), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return proc, out_dir


def test_demo_run_produces_expected_layout(tmp_path):
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"

    assert (out / "report.md").exists()
    assert (out / "result.json").exists()
    assert (out / "manifest.csv").exists()
    assert (out / "metadata.json").exists()
    assert (out / "reproducibility" / "commands.sh").exists()

    # The synthetic accession dir: SOFT + series matrix + canonical 10x triplet
    acc_dir = out / "geo" / "GSE_DEMO_OC"
    assert (acc_dir / "GSE_DEMO_OC_family.soft.gz").exists()
    assert (acc_dir / "GSE_DEMO_OC_series_matrix.txt.gz").exists()
    assert (acc_dir / "barcodes.tsv.gz").exists()
    assert (acc_dir / "features.tsv.gz").exists()
    assert (acc_dir / "matrix.mtx.gz").exists()


def test_demo_synthetic_files_are_valid_gzip(tmp_path):
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    acc_dir = out / "geo" / "GSE_DEMO_OC"

    with gzip.open(acc_dir / "GSE_DEMO_OC_family.soft.gz", "rt") as fp:
        soft = fp.read()
    assert "^SERIES = GSE_DEMO_OC" in soft
    assert "GSM_DEMO_01" in soft and "GSM_DEMO_02" in soft

    with gzip.open(acc_dir / "GSE_DEMO_OC_series_matrix.txt.gz", "rt") as fp:
        matrix = fp.read()
    assert "!series_matrix_table_begin" in matrix
    assert "!series_matrix_table_end" in matrix
    assert "ENSG" in matrix  # ENSG-style IDs in the synthetic matrix

    # The 10x triplet files must be valid gzip-text and contain the expected
    # symbol / barcode / mtx header.
    with gzip.open(acc_dir / "features.tsv.gz", "rt") as fp:
        features = fp.read()
    assert "GENE_0" in features and "Gene Expression" in features

    with gzip.open(acc_dir / "matrix.mtx.gz", "rt") as fp:
        mtx_text = fp.read()
    assert mtx_text.startswith("%%MatrixMarket")


def test_demo_manifest_schema(tmp_path):
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    df = pd.read_csv(out / "manifest.csv")
    assert list(df.columns) == ["accession", "kind", "status", "bytes", "sha256", "path", "url"]
    kinds = set(df["kind"])
    assert {"soft", "series_matrix"} <= kinds
    assert (df["status"] == "synthesized").all()
    assert (df["bytes"] > 0).all()
    assert (df["sha256"].str.len() == 64).all()  # SHA-256 hex


def test_demo_result_json_envelope(tmp_path):
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    data = json.loads((out / "result.json").read_text())
    assert data["skill"] == "sc-geo-download"
    assert data["summary"]["demo"] is True
    assert data["summary"]["accessions"] == ["GSE_DEMO_OC"]
    assert data["summary"]["n_files"] >= 2
    assert "per_accession_paths" in data["data"]
    assert data["data"]["per_accession_paths"]["GSE_DEMO_OC"].endswith("GSE_DEMO_OC")


def test_demo_report_mentions_next_step(tmp_path):
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    report = (out / "report.md").read_text()
    assert "GSE_DEMO_OC" in report
    # The report should hand off to sc-geo-import
    assert "sc-geo-import" in report


def test_demo_is_idempotent(tmp_path):
    """Re-running --demo into the same dir must succeed (overwrites synthesizes)."""
    proc1, _ = _run(["--demo"], tmp_path)
    proc2, _ = _run(["--demo"], tmp_path)
    assert proc1.returncode == 0, f"first run stderr={proc1.stderr}"
    assert proc2.returncode == 0, f"second run stderr={proc2.stderr}"


def test_demo_reproducibility_script(tmp_path):
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    repro = (out / "reproducibility" / "commands.sh").read_text()
    assert "sc-geo-download" in repro
    assert "--demo" in repro


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_no_input_errors(tmp_path):
    """Without --demo, --accession, or --pubmed-id, the skill must error clearly."""
    proc, _ = _run([], tmp_path)
    assert proc.returncode != 0
    msg = (proc.stderr + proc.stdout).lower()
    assert "accession" in msg or "demo" in msg


def test_invalid_accession_format_errors_before_network(tmp_path):
    """Bad accessions must fail with a clear validation error, not a network call."""
    proc, _ = _run(["--accession", "PRJNA999"], tmp_path)
    assert proc.returncode != 0
    msg = (proc.stderr + proc.stdout)
    assert "PRJNA999" in msg or "GSE" in msg


# ---------------------------------------------------------------------------
# Agent / runner compatibility: --input is injected by the shared runner for
# any mode != 'demo', but this skill takes --accession instead of a file path.
# ---------------------------------------------------------------------------


def test_injected_input_flag_is_tolerated_alongside_demo(tmp_path):
    """The runner injects `--input <path>` when called with mode='path'; the
    skill must tolerate it (ignore + warn) so the agent's standard invocation
    works."""
    placeholder = tmp_path / "agent_placeholder"
    placeholder.mkdir()
    proc, out = _run(["--input", str(placeholder), "--demo"], tmp_path)
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    # The skill should warn that --input is ignored on this skill.
    assert "ignored" in (proc.stderr + proc.stdout).lower()
    # Demo bundle was still produced.
    assert (out / "geo" / "GSE_DEMO_OC" / "GSE_DEMO_OC_family.soft.gz").exists()


def test_agent_invocation_pattern_parses_cleanly():
    """The agent calls ``mode='path'`` which makes the runner emit:
        sc_geo_download.py --input <placeholder> --output <auto> --accession GSE...
    Verify argparse accepts that shape (--input ignored, --accession kept)."""
    mod = _import_skill()
    ns = mod.parse_args([
        "--input", "/agent/placeholder/data/GSE109564",
        "--output", "/tmp/oc_out",
        "--accession", "GSE109564",
    ])
    assert ns.ignored_input_path == "/agent/placeholder/data/GSE109564"
    assert ns.accession == ["GSE109564"]
    assert ns.output_dir == "/tmp/oc_out"
    assert ns.demo is False


def test_injected_input_alone_still_errors_with_clear_message(tmp_path):
    """`--input` alone (no accession, no demo, no pubmed) must fail with the
    standard 'provide --accession/--pubmed-id/--demo' message — *not* a generic
    argparse 'unrecognized arguments: --input' error."""
    placeholder = tmp_path / "agent_placeholder"
    placeholder.mkdir()
    proc, _ = _run(["--input", str(placeholder)], tmp_path)
    assert proc.returncode != 0
    combined = proc.stderr + proc.stdout
    assert "unrecognized arguments" not in combined.lower()
    assert "accession" in combined.lower() or "demo" in combined.lower()


# ---------------------------------------------------------------------------
# Composition with sc-geo-import (chain demo, still no network)
# ---------------------------------------------------------------------------


def test_demo_bundle_composes_with_sc_geo_import(tmp_path):
    """The download skill's --demo output must be a valid input for sc-geo-import.

    This proves the download → import chain works end-to-end without ever
    contacting NCBI; if either skill changes the on-disk contract, this test
    is the canary.
    """
    proc, out = _run(["--demo"], tmp_path)
    assert proc.returncode == 0, f"download stderr={proc.stderr}"

    import_script = SKILL_DIR.parent / "sc-geo-import" / "sc_geo_import.py"
    if not import_script.exists():
        pytest.skip("sc-geo-import not installed alongside sc-geo-download")

    import_out = tmp_path / "import_out"
    cmd = [
        sys.executable, str(import_script),
        "--input", str(out / "geo" / "GSE_DEMO_OC"),
        "--output", str(import_out),
    ]
    proc2 = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert proc2.returncode == 0, f"sc-geo-import stderr={proc2.stderr}"
    assert (import_out / "processed.h5ad").exists()

    import anndata as ad
    a = ad.read_h5ad(import_out / "processed.h5ad")
    assert a.n_obs > 0 and a.n_vars > 0
