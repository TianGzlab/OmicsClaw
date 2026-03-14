import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.common.session import OmicsSession

def test_omics_session_agnostic(tmp_path):
    vcf = tmp_path / "test.vcf"
    vcf.write_text("vcf-dummy")
    
    session = OmicsSession.from_file(vcf, data_type="wgs", domain="genomics")
    assert session.primary_data_path == str(vcf)
    assert session.metadata["domain"] == "genomics"
    
    mzml = tmp_path / "test.mzml"
    mzml.write_text("mzml-dummy")
    
    ms_session = OmicsSession.from_file(mzml, data_type="lc-ms", domain="proteomics")
    assert ms_session.primary_data_path == str(mzml)
    assert ms_session.metadata["domain"] == "proteomics"
