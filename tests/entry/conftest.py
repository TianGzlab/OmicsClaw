"""Shared fixtures for the entry layer tests."""

from __future__ import annotations

import pytest

from omicsclaw.entry import ensemble


@pytest.fixture(autouse=True)
def fixed_host_memory(monkeypatch):
    """Size the ensemble pool from a 256 GiB host rather than this machine.

    The pool is 80% of ``/proc/meminfo`` minus a 64 GB reserve, so on a
    16 GB CI runner it would have no memory and every test that mounts
    ``run_skill`` would fail. A test about a small host patches it again.
    """
    monkeypatch.setattr(ensemble, "mem_total_gib", lambda: 256.0)
