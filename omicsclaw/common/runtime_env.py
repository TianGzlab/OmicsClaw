"""Runtime environment helpers for scientific Python dependencies."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _activate_cache_env(env_name: str, path: Path) -> Path | None:
    """Create and activate a writable cache directory for an environment variable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create cache directory for %s at %s: %s", env_name, path, exc)
        return None

    os.environ[env_name] = str(path)
    return path


def _resolve_cache_root(app_name: str) -> list[Path]:
    """Return candidate roots for runtime cache directories."""
    configured_root = os.getenv("OMICSCLAW_CACHE_DIR")
    if configured_root:
        return [Path(configured_root).expanduser()]
    return [Path(tempfile.gettempdir()) / app_name]


def ensure_runtime_cache_dirs(app_name: str = "omicsclaw") -> dict[str, Path]:
    """Ensure common scientific-library cache directories are writable.

    This currently bootstraps:
    - ``NUMBA_CACHE_DIR`` for Scanpy/Numba import-time caching
    - ``XDG_CACHE_HOME`` for libraries such as fontconfig
    - ``MPLCONFIGDIR`` for Matplotlib config/cache writes
    """
    cache_root = None
    for root_candidate in _resolve_cache_root(app_name):
        activated = _activate_cache_env("XDG_CACHE_HOME", root_candidate / "xdg_cache")
        if activated is not None:
            cache_root = activated
            break
    if cache_root is None:
        raise RuntimeError("Failed to configure a writable XDG_CACHE_HOME")

    current_mpl = os.getenv("MPLCONFIGDIR")
    if current_mpl:
        mpl_dir = _activate_cache_env("MPLCONFIGDIR", Path(current_mpl).expanduser())
    else:
        mpl_dir = _activate_cache_env("MPLCONFIGDIR", cache_root / "matplotlib")
    if mpl_dir is None:
        raise RuntimeError("Failed to configure a writable MPLCONFIGDIR")

    current_numba = os.getenv("NUMBA_CACHE_DIR")
    if current_numba:
        numba_dir = _activate_cache_env("NUMBA_CACHE_DIR", Path(current_numba).expanduser())
    else:
        numba_dir = _activate_cache_env("NUMBA_CACHE_DIR", cache_root / "numba")
    if numba_dir is None:
        raise RuntimeError("Failed to configure a writable NUMBA_CACHE_DIR")

    return {
        "xdg_cache_home": cache_root,
        "mplconfigdir": mpl_dir,
        "numba_cache_dir": numba_dir,
    }


def ensure_numba_cache_dir(app_name: str = "omicsclaw") -> Path:
    """Backward-compatible wrapper returning the configured Numba cache path."""
    return ensure_runtime_cache_dirs(app_name)["numba_cache_dir"]
