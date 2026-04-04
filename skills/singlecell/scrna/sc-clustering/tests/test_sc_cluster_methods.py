"""Static method-contract tests for sc-clustering."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_cluster.py").read_text(encoding="utf-8")


def test_cluster_methods_are_supported():
    assert '"--cluster-method"' in MODULE_TEXT
    assert '"leiden"' in MODULE_TEXT
    assert '"louvain"' in MODULE_TEXT
