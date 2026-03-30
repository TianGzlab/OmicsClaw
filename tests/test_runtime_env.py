from pathlib import Path
import tempfile

from omicsclaw.common.runtime_env import ensure_runtime_cache_dirs


def test_ensure_numba_cache_dir_sets_writable_default(monkeypatch):
    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)
    monkeypatch.delenv("OMICSCLAW_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)

    paths = ensure_runtime_cache_dirs("omicsclaw-test")
    path = paths["numba_cache_dir"]

    assert path.exists()
    assert path.is_dir()
    assert Path(tempfile.gettempdir()) in path.parents or path == Path(tempfile.gettempdir())
    assert paths["xdg_cache_home"].exists()
    assert paths["mplconfigdir"].exists()


def test_ensure_numba_cache_dir_respects_configured_root(monkeypatch, tmp_path):
    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)
    monkeypatch.setenv("OMICSCLAW_CACHE_DIR", str(tmp_path / "cache_root"))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)

    paths = ensure_runtime_cache_dirs("omicsclaw-test")
    path = paths["numba_cache_dir"]

    assert paths["xdg_cache_home"] == (tmp_path / "cache_root" / "xdg_cache")
    assert paths["mplconfigdir"] == (tmp_path / "cache_root" / "xdg_cache" / "matplotlib")
    assert path == (tmp_path / "cache_root" / "xdg_cache" / "numba")
    assert path.exists()
