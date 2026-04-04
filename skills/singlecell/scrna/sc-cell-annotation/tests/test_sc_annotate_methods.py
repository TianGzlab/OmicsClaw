"""Static method-contract tests for sc-cell-annotation."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_annotate.py").read_text(encoding="utf-8")


def test_method_registry_includes_popv():
    assert '"popv": MethodConfig(' in MODULE_TEXT
    assert 'description="Reference-mapped consensus annotation (PopV)"' in MODULE_TEXT


def test_dispatch_includes_popv():
    assert '"popv": lambda adata, args: annotate_popv' in MODULE_TEXT
