"""Mechanical helpers shared by every OmicsClaw skill.

A directory starting with ``_`` is not a skill. Importing this package loads
nothing but :mod:`pathlib`; each helper lives in its own submodule.
"""

from pathlib import Path

__all__ = ["REPO_ROOT"]

REPO_ROOT = Path(__file__).resolve().parents[2]
"""The repository (or install tree) that provides this ``skills/_sdk``."""
