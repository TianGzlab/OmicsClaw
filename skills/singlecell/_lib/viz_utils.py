"""Backward-compatible visualization helpers for single-cell skills.

This module now delegates to :mod:`skills.singlecell._lib.viz` so newer skills
can import from the shared visualization package while older code keeps working.
"""

from .viz import save_figure

__all__ = ["save_figure"]
