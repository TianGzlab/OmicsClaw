from omicsclaw.loaders import (
    EXTENSION_TO_DOMAIN,
    detect_domain_from_extension,
    detect_domain_from_path,
)
from skills.orchestrator.omics_orchestrator import detect_domain


def test_detect_domain_from_extension_preserves_existing_mappings():
    assert EXTENSION_TO_DOMAIN[".h5ad"] == "spatial"
    assert detect_domain_from_extension(".mzML") == "proteomics"
    assert detect_domain_from_extension(".unknown", fallback="") == ""


def test_detect_domain_from_path_handles_multi_suffix_inputs():
    assert detect_domain_from_path("/tmp/sample.vcf.gz") == "genomics"
    assert detect_domain_from_path("/tmp/sample.fastq.gz") == "genomics"
    assert detect_domain_from_path("/tmp/sample.unknown", fallback="") == ""


def test_orchestrator_detect_domain_uses_shared_path_helper():
    assert detect_domain(input_path="/tmp/sample.vcf.gz") == "genomics"
    assert detect_domain(input_path="/tmp/sample.mzML") == "proteomics"
