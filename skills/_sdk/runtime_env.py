"""Writable cache directories for the scientific Python stack."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

__all__ = ["ensure_runtime_cache_dirs"]

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

    Sets ``XDG_CACHE_HOME``, ``MPLCONFIGDIR`` and ``NUMBA_CACHE_DIR`` in this
    process's environment (keeping existing ``MPLCONFIGDIR`` and
    ``NUMBA_CACHE_DIR`` values) and creates the directories. The root is
    ``$OMICSCLAW_CACHE_DIR`` when set, else ``<tempdir>/<app_name>``.

    :returns: The three directories, keyed ``xdg_cache_home``, ``mplconfigdir``
        and ``numba_cache_dir``.
    :raises RuntimeError: If a directory cannot be created.
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
