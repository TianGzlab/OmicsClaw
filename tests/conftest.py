"""Shared pytest configuration for OmicsClaw."""

from __future__ import annotations

import os

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
