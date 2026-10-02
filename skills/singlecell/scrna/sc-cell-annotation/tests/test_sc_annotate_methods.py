"""Static method-contract tests for sc-cell-annotation."""

from __future__ import annotations

from pathlib import Path

MODULE_TEXT = (Path(__file__).resolve().parent.parent / "sc_annotate.py").read_text(encoding="utf-8")
API_TEXT = (Path(__file__).resolve().parent.parent / "_api.py").read_text(encoding="utf-8")


def test_method_registry_includes_popv():
    assert '"popv": MethodConfig(' in MODULE_TEXT
    assert 'PopV-style reference mapping' in MODULE_TEXT or 'PopV' in MODULE_TEXT


def test_method_registry_includes_manual():
    assert '"manual": MethodConfig(' in MODULE_TEXT
    assert 'Manual relabeling' in MODULE_TEXT


def test_method_registry_includes_knnpredict():
    assert '"knnpredict": MethodConfig(' in MODULE_TEXT
    assert 'Lightweight AnnData-first reference mapping inspired by SCOP KNNPredict' in MODULE_TEXT


def test_dispatch_includes_popv():
    assert 'if method == "popv":\n        return annotate_popv(' in API_TEXT


def test_dispatch_includes_manual():
    assert 'if method == "manual":\n        return annotate_manual(' in API_TEXT


def test_dispatch_includes_knnpredict():
    assert 'if method == "knnpredict":\n        return annotate_knnpredict(' in API_TEXT
