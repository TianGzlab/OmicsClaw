"""Velocity input contracts through load_skill."""

import pytest
from skills._sdk.notebook import load_demo, load_skill


def test_missing_unspliced_counts_are_not_synthesized():
    data = load_demo("spatial_synthetic")
    data.layers["spliced"] = data.X.copy()
    with pytest.raises(ValueError, match="unspliced"):
        load_skill("spatial-velocity").velocity(data)
    assert "unspliced" not in data.layers


def test_invalid_preprocessing_does_not_silently_clip_the_request():
    data = load_demo("spatial_synthetic")
    data.layers["spliced"] = data.X.copy()
    data.layers["unspliced"] = data.X.copy()
    with pytest.raises(ValueError, match="velocity_n_pcs"):
        load_skill("spatial-velocity").velocity(data, method_params={"velocity_n_pcs": 0})


def test_missing_backend_names_the_install_action():
    import sys
    import subprocess

    code = """
import sys
from skills._sdk.notebook import load_demo, load_skill
data = load_demo('spatial_synthetic')
data.layers['spliced'] = data.X.copy()
data.layers['unspliced'] = data.X.copy()
sys.modules['scvelo'] = None
try:
    load_skill('spatial-velocity').velocity(data)
except ImportError as exc:
    assert 'scvelo' in str(exc) and 'install_skill_deps' in str(exc)
else:
    raise AssertionError('Missing backend was not reported')
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
