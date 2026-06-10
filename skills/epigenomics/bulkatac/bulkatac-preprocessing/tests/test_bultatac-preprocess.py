"""
tests/test_get_demo_data.py

Tests that do NOT require network access (all offline):
  - ENCODE_QC_THRESHOLDS dict structure and values
  - QC tier helper functions (frip, pbc1, nrf, tss, align_rate, fragment depth)
  - _downsample_fastq_gz correctness
  - _count_reads_fastq_gz
  - get_demo_data() with mocked download
  - manifest structure and ENCODE content
  - idempotency

Network test (opt-in):
  OC_NETWORK_TESTS=1 pytest tests/test_get_demo_data.py
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from get_demo_data import (
    ENCODE_QC_THRESHOLDS,
    NEXTERA_ADAPTER,
    ENCODE_BAM_EXCLUDE_FLAGS,
    ENCODE_BAM_REQUIRE_FLAGS,
    ENCODE_MAPQ_THRESHOLD,
    _ENCODE_FILES,
    _count_reads_fastq_gz,
    _downsample_fastq_gz,
    encode_frip_tier,
    encode_pbc1_tier,
    encode_nrf_tier,
    encode_tss_tier,
    encode_align_rate_tier,
    encode_fragment_depth_tier,
    get_demo_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fastq_gz(path: Path, n_reads: int, read_len: int = 76) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        for i in range(n_reads):
            seq  = "A" * read_len
            qual = "I" * read_len
            fh.write(f"@read_{i}\n{seq}\n+\n{qual}\n")
    return path


@pytest.fixture()
def raw_fastqs(tmp_path) -> dict[str, Path]:
    """Pre-place raw FASTQ stubs so download is never triggered."""
    raw_dir = tmp_path / "raw"
    paths = {}
    for sample, meta in _ENCODE_FILES.items():
        _make_fastq_gz(raw_dir / meta["R1_raw"], n_reads=200)
        _make_fastq_gz(raw_dir / meta["R2_raw"], n_reads=200)
    return paths


def _fake_download(url: str, dest: Path) -> Path:
    assert dest.exists(), f"_fake_download: {dest} not pre-placed by fixture"
    return dest


# ---------------------------------------------------------------------------
# ENCODE_QC_THRESHOLDS structure
# ---------------------------------------------------------------------------

class TestEncodeQCThresholds:
    """ENCODE_QC_THRESHOLDS must contain all metrics with correct tier values."""

    def test_frip_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["frip"]
        assert t["preferred"]  == pytest.approx(0.30)
        assert t["acceptable"] == pytest.approx(0.20)

    def test_tss_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["tss_enrichment"]
        assert t["preferred"]         == pytest.approx(7.0)
        assert t["acceptable"]        == pytest.approx(5.0)
        assert t["acceptable_tissue"] == pytest.approx(3.0)

    def test_nrf_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["nrf"]
        assert t["preferred"]  == pytest.approx(0.90)
        assert t["acceptable"] == pytest.approx(0.80)

    def test_pbc1_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["pbc1"]
        assert t["preferred"]    == pytest.approx(0.90)
        assert t["acceptable"]   == pytest.approx(0.50), \
            "PBC1 < 0.5 is ENCODE-defined severe bottlenecking"
        assert t["severe_cutoff"] == pytest.approx(0.50)

    def test_pbc2_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["pbc2"]
        assert t["preferred"]  == pytest.approx(3.0)
        assert t["acceptable"] == pytest.approx(1.0)

    def test_fragment_depth_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["n_fragments_pe"]
        assert t["preferred"]  == 25_000_000, "ENCODE: >= 25 M fragments (PE preferred)"
        assert t["acceptable"] == 10_000_000

    def test_align_rate_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["align_rate"]
        assert t["preferred"]  == pytest.approx(0.95)
        assert t["acceptable"] == pytest.approx(0.80)

    def test_peaks_replicated_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["n_peaks_replicated"]
        assert t["preferred"]  == 150_000
        assert t["acceptable"] == 100_000

    def test_peaks_idr_thresholds(self):
        t = ENCODE_QC_THRESHOLDS["n_peaks_idr"]
        assert t["preferred"]  == 70_000
        assert t["acceptable"] == 50_000

    def test_min_read_length(self):
        """ENCODE restriction: read length must be >= 45 bp before trimming."""
        t = ENCODE_QC_THRESHOLDS["min_read_length_bp"]
        assert t["acceptable"] == pytest.approx(45.0)

    def test_nextera_adapter_sequence(self):
        assert NEXTERA_ADAPTER == "CTGTCTCTTATACACATCT"

    def test_encode_bam_flags(self):
        """ENCODE BAM filter: -F 1804 -f 2 -q 30."""
        assert ENCODE_BAM_EXCLUDE_FLAGS == 1804
        assert ENCODE_BAM_REQUIRE_FLAGS == 2
        assert ENCODE_MAPQ_THRESHOLD    == 30


# ---------------------------------------------------------------------------
# QC tier helper functions
# ---------------------------------------------------------------------------

class TestEncodeQCTiers:
    """All tier helpers must implement the ENCODE pass/warn/fail ladder."""

    # --- FRiP ---
    def test_frip_preferred(self):
        assert encode_frip_tier(0.45) == "preferred"

    def test_frip_acceptable(self):
        assert encode_frip_tier(0.25) == "acceptable"

    def test_frip_fail(self):
        assert encode_frip_tier(0.10) == "fail"

    def test_frip_boundary_preferred(self):
        assert encode_frip_tier(0.30) == "preferred"

    def test_frip_boundary_acceptable(self):
        assert encode_frip_tier(0.20) == "acceptable"

    def test_frip_just_below_acceptable(self):
        assert encode_frip_tier(0.199) == "fail"

    # --- PBC1 ---
    def test_pbc1_preferred(self):
        assert encode_pbc1_tier(0.95) == "preferred"

    def test_pbc1_moderate_bottleneck(self):
        """0.5–0.8: moderate PCR bottlenecking → acceptable."""
        assert encode_pbc1_tier(0.65) == "acceptable"

    def test_pbc1_mild_bottleneck(self):
        """0.8–0.9: mild PCR bottlenecking → acceptable."""
        assert encode_pbc1_tier(0.85) == "acceptable"

    def test_pbc1_severe_bottleneck(self):
        """< 0.5: severe PCR bottlenecking → fail."""
        assert encode_pbc1_tier(0.35) == "fail"

    def test_pbc1_boundary_severe(self):
        assert encode_pbc1_tier(0.50) == "acceptable"

    def test_pbc1_just_below_severe(self):
        assert encode_pbc1_tier(0.499) == "fail"

    # --- NRF ---
    def test_nrf_preferred(self):
        assert encode_nrf_tier(0.95) == "preferred"

    def test_nrf_acceptable(self):
        assert encode_nrf_tier(0.85) == "acceptable"

    def test_nrf_fail(self):
        assert encode_nrf_tier(0.70) == "fail"

    # --- TSS enrichment ---
    def test_tss_preferred(self):
        assert encode_tss_tier(8.5, tissue_type="cell_line") == "preferred"

    def test_tss_acceptable_cell_line(self):
        assert encode_tss_tier(6.0, tissue_type="cell_line") == "acceptable"

    def test_tss_fail_cell_line(self):
        assert encode_tss_tier(4.0, tissue_type="cell_line") == "fail"

    def test_tss_acceptable_tissue(self):
        """Primary tissue: ENCODE acceptable cutoff is 3.0, not 5.0."""
        assert encode_tss_tier(4.0, tissue_type="tissue") == "acceptable"

    def test_tss_fail_tissue(self):
        assert encode_tss_tier(2.5, tissue_type="tissue") == "fail"

    # --- Alignment rate ---
    def test_align_rate_preferred(self):
        assert encode_align_rate_tier(0.97) == "preferred"

    def test_align_rate_acceptable(self):
        assert encode_align_rate_tier(0.88) == "acceptable"

    def test_align_rate_fail(self):
        assert encode_align_rate_tier(0.70) == "fail"

    # --- Fragment depth ---
    def test_fragment_depth_preferred(self):
        assert encode_fragment_depth_tier(30_000_000) == "preferred"

    def test_fragment_depth_acceptable(self):
        assert encode_fragment_depth_tier(15_000_000) == "acceptable"

    def test_fragment_depth_fail(self):
        """Demo data (50 000 reads) is far below both thresholds — expected."""
        assert encode_fragment_depth_tier(50_000) == "fail"


# ---------------------------------------------------------------------------
# _count_reads_fastq_gz
# ---------------------------------------------------------------------------

def test_count_reads(tmp_path):
    p = _make_fastq_gz(tmp_path / "r.fastq.gz", n_reads=42)
    assert _count_reads_fastq_gz(p) == 42


def test_count_reads_empty(tmp_path):
    p = tmp_path / "empty.fastq.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("")
    assert _count_reads_fastq_gz(p) == 0


# ---------------------------------------------------------------------------
# _downsample_fastq_gz
# ---------------------------------------------------------------------------

def test_downsample_exact(tmp_path):
    src  = _make_fastq_gz(tmp_path / "src.fastq.gz", n_reads=150)
    dest = tmp_path / "dest.fastq.gz"
    assert _downsample_fastq_gz(src, dest, 50) == 50
    assert _count_reads_fastq_gz(dest) == 50


def test_downsample_fewer_than_requested(tmp_path):
    src  = _make_fastq_gz(tmp_path / "src.fastq.gz", n_reads=30)
    dest = tmp_path / "dest.fastq.gz"
    n    = _downsample_fastq_gz(src, dest, 200)
    assert n == 30


def test_downsample_read_length_meets_encode_minimum(tmp_path):
    """ENCODE restriction: read length must be >= 45 bp before trimming.
    ENCSR356KRQ is 76 nt — verify the downsampled records preserve full length."""
    src  = _make_fastq_gz(tmp_path / "src.fastq.gz", n_reads=20, read_len=76)
    dest = tmp_path / "dest.fastq.gz"
    _downsample_fastq_gz(src, dest, 10)
    min_len = ENCODE_QC_THRESHOLDS["min_read_length_bp"]["acceptable"]
    with gzip.open(dest, "rt") as fh:
        lines = fh.readlines()
    seqs = [lines[i * 4 + 1].strip() for i in range(len(lines) // 4)]
    for seq in seqs:
        assert len(seq) >= min_len, \
            f"Read length {len(seq)} bp is below ENCODE minimum {min_len} bp"


def test_downsample_valid_fastq(tmp_path):
    src  = _make_fastq_gz(tmp_path / "src.fastq.gz", n_reads=20)
    dest = tmp_path / "dest.fastq.gz"
    _downsample_fastq_gz(src, dest, 10)
    with gzip.open(dest, "rt") as fh:
        lines = fh.readlines()
    assert len(lines) == 40
    assert lines[0].startswith("@")
    assert lines[2].strip() == "+"


def test_downsample_idempotent(tmp_path):
    src  = _make_fastq_gz(tmp_path / "src.fastq.gz", n_reads=100)
    dest = tmp_path / "dest.fastq.gz"
    _downsample_fastq_gz(src, dest, 40)
    mtime = dest.stat().st_mtime
    _downsample_fastq_gz(src, dest, 40)
    assert dest.stat().st_mtime == mtime


def test_downsample_rewrite_on_count_change(tmp_path):
    src  = _make_fastq_gz(tmp_path / "src.fastq.gz", n_reads=100)
    dest = tmp_path / "dest.fastq.gz"
    _downsample_fastq_gz(src, dest, 40)
    _downsample_fastq_gz(src, dest, 60)
    assert _count_reads_fastq_gz(dest) == 60


# ---------------------------------------------------------------------------
# get_demo_data() with pre-placed raw files
# ---------------------------------------------------------------------------

class TestGetDemoData:

    def test_returns_expected_samples(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            samples = get_demo_data(tmp_path, n_reads=50)
        assert set(samples.keys()) == {"CTRL_rep1", "CTRL_rep2"}

    def test_files_exist(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            samples = get_demo_data(tmp_path, n_reads=50)
        for name, meta in samples.items():
            assert Path(meta["R1"]).exists()
            assert Path(meta["R2"]).exists()

    def test_correct_read_count(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            samples = get_demo_data(tmp_path, n_reads=50)
        for name, meta in samples.items():
            assert meta["n_reads"] == 50
            assert _count_reads_fastq_gz(Path(meta["R1"])) == 50

    def test_condition_labels(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            samples = get_demo_data(tmp_path, n_reads=20)
        assert samples["CTRL_rep1"]["condition"] == "CTRL"
        assert samples["CTRL_rep2"]["condition"] == "CTRL"

    def test_encode_metadata_present(self, tmp_path, raw_fastqs):
        """Each sample must carry ENCODE pipeline metadata."""
        with patch("get_demo_data._download", side_effect=_fake_download):
            samples = get_demo_data(tmp_path, n_reads=20)
        for name, meta in samples.items():
            assert meta["organism"]          == "Homo sapiens"
            assert meta["genome"]            == "hg38"
            assert meta["assay"]             == "ATAC-seq"
            assert meta["source_accession"]  == "ENCSR356KRQ"
            assert meta["nextera_adapter"]   == NEXTERA_ADAPTER
            assert meta["mapq_threshold"]    == ENCODE_MAPQ_THRESHOLD
            assert meta["bam_exclude_flags"] == ENCODE_BAM_EXCLUDE_FLAGS

    def test_encode_qc_thresholds_in_sample(self, tmp_path, raw_fastqs):
        """QC thresholds must be embedded in each sample for downstream validation."""
        with patch("get_demo_data._download", side_effect=_fake_download):
            samples = get_demo_data(tmp_path, n_reads=20)
        for name, meta in samples.items():
            qc = meta["encode_qc_thresholds"]
            assert qc["frip"]["preferred"]  == pytest.approx(0.30)
            assert qc["pbc1"]["acceptable"] == pytest.approx(0.50)
            assert qc["n_fragments_pe"]["preferred"] == 25_000_000

    def test_raw_cached_in_raw_subdir(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20)
        assert (tmp_path / "raw").is_dir()

    def test_idempotent(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            s1 = get_demo_data(tmp_path, n_reads=50)
            mt = Path(s1["CTRL_rep1"]["R1"]).stat().st_mtime
            s2 = get_demo_data(tmp_path, n_reads=50)
        assert Path(s2["CTRL_rep1"]["R1"]).stat().st_mtime == mt


# ---------------------------------------------------------------------------
# Manifest content
# ---------------------------------------------------------------------------

class TestManifest:

    def test_manifest_written(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20, write_manifest=True)
        assert (tmp_path / "demo_manifest.json").exists()

    def test_manifest_has_encode_standards_url(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20)
        data = json.loads((tmp_path / "demo_manifest.json").read_text())
        assert "encode_standards_url" in data
        assert "encodeproject.org" in data["encode_standards_url"]

    def test_manifest_has_qc_thresholds(self, tmp_path, raw_fastqs):
        """Manifest must embed ENCODE QC thresholds for audit."""
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20)
        data = json.loads((tmp_path / "demo_manifest.json").read_text())
        assert "encode_qc_thresholds" in data
        assert "frip" in data["encode_qc_thresholds"]
        assert "pbc1" in data["encode_qc_thresholds"]
        assert "n_fragments_pe" in data["encode_qc_thresholds"]

    def test_manifest_has_pipeline_steps(self, tmp_path, raw_fastqs):
        """Manifest must document the ENCODE upstream processing steps."""
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20)
        data = json.loads((tmp_path / "demo_manifest.json").read_text())
        assert "encode_upstream_pipeline" in data
        pipeline = data["encode_upstream_pipeline"]
        assert "Bowtie2" in pipeline["aligner"]
        assert "MACS2"   in pipeline["peak_caller"]
        assert "Picard"  in pipeline["dedup"]

    def test_manifest_has_production_note(self, tmp_path, raw_fastqs):
        """Manifest must warn that subsampled data won't meet production thresholds."""
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20)
        data = json.loads((tmp_path / "demo_manifest.json").read_text())
        assert "production_threshold_note" in data
        note = data["production_threshold_note"].lower()
        assert "not" in note or "won't" in note or "below" in note, \
            "production_threshold_note must clearly state demo data won't meet ENCODE standards"

    def test_manifest_no_manifest_flag(self, tmp_path, raw_fastqs):
        with patch("get_demo_data._download", side_effect=_fake_download):
            get_demo_data(tmp_path, n_reads=20, write_manifest=False)
        assert not (tmp_path / "demo_manifest.json").exists()


# ---------------------------------------------------------------------------
# Network test (opt-in)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("OC_NETWORK_TESTS", "0") != "1",
    reason="Network tests disabled — set OC_NETWORK_TESTS=1 to enable",
)
def test_encode_download_end_to_end(tmp_path):
    """Downloads real ENCODE files. Only runs when OC_NETWORK_TESTS=1."""
    samples = get_demo_data(tmp_path, n_reads=1_000)
    for name, meta in samples.items():
        assert Path(meta["R1"]).exists()
        assert _count_reads_fastq_gz(Path(meta["R1"])) == 1_000
        # Verify ENCODE QC thresholds are embedded
        assert "frip" in meta["encode_qc_thresholds"]
        # Subsampled data should fail fragment depth (expected)
        assert encode_fragment_depth_tier(meta["n_reads"]) == "fail", \
            "Demo data should fail fragment depth threshold by design"