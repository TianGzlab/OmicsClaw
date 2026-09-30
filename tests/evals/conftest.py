"""Fixtures for the eval tests: a hermetic environment and the report collector.

Every dataset test hands its :class:`~omicsclaw.evals.Result` to
``eval_results``. When ``OMICSCLAW_EVAL_REPORT_DIR`` is set, the session
writes ``report.json`` and ``report.md`` there at the end.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omicsclaw.evals import Result, build_report, write_json, write_markdown
from omicsclaw.evals.hermetic import block_network, hermetic_changes

REPORT_DIR_VARIABLE = "OMICSCLAW_EVAL_REPORT_DIR"
_RESULTS = pytest.StashKey[list]()


@pytest.fixture
def hermetic(monkeypatch, tmp_path):
    """The Runner's hermetic environment, applied with ``monkeypatch``.

    Yields the ``HOME`` directory it set.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    removed, updates = hermetic_changes(home)
    for name in removed:
        monkeypatch.delenv(name, raising=False)
    for name, value in updates.items():
        monkeypatch.setenv(name, value)
    with block_network():
        yield home


@pytest.fixture
def eval_results(request) -> list[Result]:
    """The session's list of eval results, which the report is built from."""
    return request.config.stash.setdefault(_RESULTS, [])


def pytest_sessionfinish(session, exitstatus):
    results = session.config.stash.get(_RESULTS, [])
    directory = os.environ.get(REPORT_DIR_VARIABLE)
    if not directory or not results:
        return
    report = build_report(results)
    write_json(report, Path(directory) / "report.json")
    write_markdown(report, Path(directory) / "report.md")
