"""Tests for namespace_policy — see docs/CONTEXT.md namespace ownership table."""

import pytest

from omicsclaw.memory.namespace_policy import resolve_namespace, should_version
from omicsclaw.memory.uri import MemoryURI


def test_resolve_namespace_returns_shared_for_core_agent():
    uri = MemoryURI.parse("core://agent")
    assert resolve_namespace(uri, current="tg/A") == "__shared__"


def test_resolve_namespace_returns_current_for_per_namespace_uri():
    assert resolve_namespace(MemoryURI.parse("dataset://pbmc.h5ad"), current="tg/A") == "tg/A"
    assert resolve_namespace(MemoryURI.parse("analysis://run_42"), current="tg/A") == "tg/A"
    assert resolve_namespace(MemoryURI.parse("project://current"), current="tg/A") == "tg/A"


def test_resolve_namespace_kh_prefix_is_shared():
    # core://kh and any sub-path under it are shared
    assert resolve_namespace(MemoryURI.parse("core://kh"), current="X") == "__shared__"
    assert resolve_namespace(MemoryURI.parse("core://kh/qc_threshold"), current="X") == "__shared__"
    assert resolve_namespace(MemoryURI.parse("core://kh/sc/marker"), current="X") == "__shared__"


def test_resolve_namespace_false_prefix_does_not_match():
    # 'kh' must not match 'khaki' (path-segment matching, not raw startswith)
    assert resolve_namespace(MemoryURI.parse("core://khaki"), current="X") == "X"
    assert resolve_namespace(MemoryURI.parse("core://agent_alt"), current="X") == "X"


def test_resolve_namespace_my_user_is_per_namespace():
    # core://my_user is per-user, not shared
    assert resolve_namespace(MemoryURI.parse("core://my_user"), current="tg/A") == "tg/A"


def test_resolve_namespace_my_user_default_is_shared():
    # core://my_user_default is the fallback template, shared
    assert resolve_namespace(MemoryURI.parse("core://my_user_default"), current="tg/A") == "__shared__"


def test_should_version_core_agent_true():
    assert should_version(MemoryURI.parse("core://agent")) is True


def test_should_version_false_for_non_versioned_domains():
    assert should_version(MemoryURI.parse("dataset://pbmc.h5ad")) is False
    assert should_version(MemoryURI.parse("analysis://sc-de/run_42")) is False
    assert should_version(MemoryURI.parse("session://abc123")) is False
    assert should_version(MemoryURI.parse("insight://cluster/3")) is False
    assert should_version(MemoryURI.parse("project://current")) is False


def test_should_version_core_my_user_true():
    # core://my_user is per-namespace (Q3) but versioned (Q5) — both rules independent
    assert should_version(MemoryURI.parse("core://my_user")) is True


def test_should_version_all_preferences_true():
    # whole `preference://` domain is versioned
    assert should_version(MemoryURI.parse("preference://qc/cutoff")) is True
    assert should_version(MemoryURI.parse("preference://global/theme")) is True
    assert should_version(MemoryURI.parse("preference://anything_at_all")) is True


def test_should_version_kh_and_my_user_default_false():
    # core://kh is shared but NOT versioned (static system content)
    assert should_version(MemoryURI.parse("core://kh")) is False
    assert should_version(MemoryURI.parse("core://kh/qc_threshold")) is False
    # core://my_user_default is the static fallback template, NOT versioned
    assert should_version(MemoryURI.parse("core://my_user_default")) is False


# ----------------------------------------------------------------------
# CONTEXT.md namespace ownership table — full matrix
# Lock the entire policy contract in one place. If a row needs to change,
# update CONTEXT.md and SHARED_PREFIXES / VERSIONED_PREFIXES in lockstep.
# ----------------------------------------------------------------------

_PER_NS = "ns/X"  # opaque current namespace for matrix tests


@pytest.mark.parametrize(
    "uri_str,expected_ns,expected_version",
    [
        ("core://agent",            "__shared__", True),
        ("core://kh",               "__shared__", False),
        ("core://kh/qc_threshold",  "__shared__", False),
        ("core://my_user_default",  "__shared__", False),
        ("core://my_user",          _PER_NS,      True),
        ("preference://qc/cutoff",  _PER_NS,      True),
        ("preference://global/x",   _PER_NS,      True),
        ("dataset://pbmc.h5ad",     _PER_NS,      False),
        ("analysis://run_42",       _PER_NS,      False),
        ("insight://cluster/3",     _PER_NS,      False),
        ("project://current",       _PER_NS,      False),
        ("session://abc123",        _PER_NS,      False),
    ],
)
def test_context_md_table_full_matrix(uri_str, expected_ns, expected_version):
    uri = MemoryURI.parse(uri_str)
    assert resolve_namespace(uri, current=_PER_NS) == expected_ns
    assert should_version(uri) is expected_version
