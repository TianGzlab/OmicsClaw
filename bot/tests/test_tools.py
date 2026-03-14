import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from bot.core import TOOLS, OMICS_EXTENSIONS

def test_tools_generated():
    assert len(TOOLS) > 0
    omicsclaw_tool = next((t for t in TOOLS if t["function"]["name"] == "omicsclaw"), None)
    assert omicsclaw_tool is not None
    assert "vcf-ops" in omicsclaw_tool["function"]["description"]  # Added to registry based on orchestration
    
    # Just checking an extension loaded dynamically
    assert ".vcf" in OMICS_EXTENSIONS
