import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import registry

def test_registry_loaded():
    registry.load_all()
    assert "preprocess" in registry.skills
    assert "spatial" in registry.domains
    assert len(registry.skills) > 0
    assert len(registry.domains) > 0
