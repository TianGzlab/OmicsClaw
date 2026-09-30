"""Mark every test under ``tests/evals/dataset/`` as ``scripted_eval``."""

from __future__ import annotations

from pathlib import Path

import pytest

DATASET_DIR = Path(__file__).resolve().parent


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Add the ``scripted_eval`` marker before ``-m`` filters the items.

    The hook sees every item of the session, so it filters by path.
    """
    for item in items:
        if DATASET_DIR in Path(item.path).resolve().parents:
            item.add_marker(pytest.mark.scripted_eval)
