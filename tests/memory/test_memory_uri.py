"""Tests for MemoryURI value object.

See docs/CONTEXT.md → "Memory URI" for the contract this exercises.
"""

import pytest

from omicsclaw.memory.uri import MemoryURI


def test_parse_basic_uri():
    uri = MemoryURI.parse("core://agent")
    assert uri.domain == "core"
    assert uri.path == "agent"


def test_str_canonical_form():
    uri = MemoryURI(domain="dataset", path="pbmc.h5ad")
    assert str(uri) == "dataset://pbmc.h5ad"


def test_is_root_property():
    assert MemoryURI(domain="core", path="").is_root is True
    assert MemoryURI(domain="core", path="agent").is_root is False


def test_child_appends_name_with_slash():
    parent = MemoryURI(domain="analysis", path="sc-de")
    assert parent.child("run_42") == MemoryURI(domain="analysis", path="sc-de/run_42")


def test_child_of_root_has_no_leading_slash():
    root = MemoryURI(domain="core", path="")
    assert root.child("agent") == MemoryURI(domain="core", path="agent")


def test_parent_strips_last_segment():
    uri = MemoryURI(domain="analysis", path="sc-de/run_42")
    assert uri.parent() == MemoryURI(domain="analysis", path="sc-de")


def test_parent_of_single_segment_returns_root():
    uri = MemoryURI(domain="dataset", path="pbmc.h5ad")
    parent = uri.parent()
    assert parent == MemoryURI(domain="dataset", path="")
    assert parent.is_root


def test_parent_of_root_returns_none():
    root = MemoryURI(domain="core", path="")
    assert root.parent() is None


def test_parse_without_scheme_defaults_to_core():
    uri = MemoryURI.parse("agent")
    assert uri == MemoryURI(domain="core", path="agent")


def test_parse_root_uri_with_empty_path():
    uri = MemoryURI.parse("core://")
    assert uri == MemoryURI(domain="core", path="")
    assert uri.is_root


def test_root_classmethod_creates_root_uri():
    assert MemoryURI.root("dataset") == MemoryURI(domain="dataset", path="")
    assert MemoryURI.root() == MemoryURI(domain="core", path="")
    assert MemoryURI.root("dataset").is_root


def test_parse_str_roundtrip():
    for raw in (
        "core://agent",
        "dataset://pbmc.h5ad",
        "analysis://sc-de/run_42",
        "core://",
    ):
        assert str(MemoryURI.parse(raw)) == raw, f"roundtrip failed for {raw!r}"


def test_uri_is_hashable_and_equal_by_value():
    a = MemoryURI(domain="core", path="agent")
    b = MemoryURI(domain="core", path="agent")
    c = MemoryURI(domain="core", path="other")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)
    assert len({a, b, c}) == 2  # set deduplicates a/b


def test_empty_domain_rejected():
    with pytest.raises(ValueError, match="domain"):
        MemoryURI(domain="", path="agent")
    with pytest.raises(ValueError, match="domain"):
        MemoryURI.parse("://agent")


def test_domain_with_scheme_separator_rejected():
    with pytest.raises(ValueError, match="domain"):
        MemoryURI(domain="core://nope", path="agent")


def test_path_with_scheme_separator_rejected():
    with pytest.raises(ValueError, match="path"):
        MemoryURI(domain="core", path="x://y")
    with pytest.raises(ValueError, match="path"):
        MemoryURI.parse("core://x://y")


@pytest.mark.parametrize("bad_char", ["\n", "\t", "\x00", "\r"])
def test_domain_with_control_chars_rejected(bad_char):
    with pytest.raises(ValueError, match="domain"):
        MemoryURI(domain=f"core{bad_char}", path="agent")
