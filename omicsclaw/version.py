"""Project version helpers.

Update ``__version__`` here for each release/iteration. Packaging metadata,
CLI output, and service metadata all import from this single module.
"""


from functools import lru_cache
from pathlib import Path
import subprocess

__version__ = "0.1.2"


@lru_cache(maxsize=1)
def build_identity() -> dict[str, str | bool | None]:
    """Identify a source checkout once per process; installed wheels may be unknown."""
    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        return {"commit": None, "dirty": None}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
            stderr=subprocess.DEVNULL, timeout=2,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root, text=True, stderr=subprocess.DEVNULL, timeout=2,
        ).strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}
