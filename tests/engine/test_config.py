"""Contract tests for ``omicsclaw.engine.config`` (plan 0027 §3, §4 Q6).

The defaults are pinned by value. Each was chosen against a recorded
failure — a turn ceiling that stalls a benchmark, a retry budget too
narrow for a TLS error, a tool result some backends answer with a 400 —
and a silently edited number would take a long time to be noticed, since
nothing about it fails fast.
"""

from __future__ import annotations

import inspect

import pytest

from omicsclaw.engine import config as config_module
from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.types import EngineError


# --- the defaults ---------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_turns", 50),
        ("tool_timeout", 60.0),
        ("max_concurrent_tools", 0),
        ("generate_retries", 3),
        ("generate_retry_base", 1.0),
        ("network_retries", 6),
        ("network_retry_base", 5.0),
        ("empty_output_placeholder", "[tool completed with no output]"),
    ],
)
def test_every_default_is_the_documented_one(field, value):
    assert getattr(EngineConfig(), field) == value


def test_the_turn_ceiling_clears_the_legacy_twenty():
    """Plan 0027 §4 Q6.

    ``docs/evaluation/cross-agent-benchmark-guide.md`` records that the
    legacy ``OMICSCLAW_MAX_TOOL_ITERATIONS=20`` stalls the 30-turn
    benchmark tasks outright, and the reference harness's 500 is tuned
    for unattended long-horizon coding.
    """
    assert EngineConfig().max_turns > 30
    assert EngineConfig().max_turns < 500


def test_the_tool_timeout_is_seconds_as_a_float():
    """Matching ``ProviderConfig.timeout_seconds`` rather than the
    reference harness's duration type, so arithmetic on it needs no
    conversion."""
    assert isinstance(EngineConfig().tool_timeout, float)
    assert isinstance(EngineConfig().generate_retry_base, float)
    assert isinstance(EngineConfig().network_retry_base, float)


def test_the_transport_retry_budget_is_the_wider_of_the_two():
    """They are independent budgets, not one budget reused.

    TLS, DNS and connection-establishment failures are more intermittent
    than a 4xx or a 5xx: the reference harness saw three benchmark tasks
    give up a turn on the same x509 error once the narrow budget's ~3s of
    backoff was spent.
    """
    config = EngineConfig()
    assert config.network_retries > config.generate_retries
    assert config.network_retry_base > config.generate_retry_base


def test_the_placeholder_for_an_empty_tool_result_is_not_itself_empty():
    """Its whole purpose: some backends reject an empty ``tool_result``
    with a 400, and an Observation carrying nothing wastes a turn."""
    assert EngineConfig().empty_output_placeholder.strip() != ""


# --- copy-on-write --------------------------------------------------------


def test_with_overrides_returns_a_changed_copy_and_leaves_the_receiver_alone():
    original = EngineConfig()
    tightened = original.with_overrides(max_turns=5, tool_timeout=1.5)

    assert tightened.max_turns == 5
    assert tightened.tool_timeout == 1.5
    assert original.max_turns == 50
    assert original.tool_timeout == 60.0


def test_with_overrides_copies_even_when_nothing_is_overridden():
    """Copy-on-write always copies; a caller holding the result must
    never be holding the receiver."""
    original = EngineConfig()
    copy = original.with_overrides()

    assert copy == original
    assert copy is not original


def test_with_overrides_carries_the_untouched_fields_forward():
    config = EngineConfig(empty_output_placeholder="[nothing]")
    assert config.with_overrides(max_turns=2).empty_output_placeholder == "[nothing]"


def test_with_overrides_rejects_an_unknown_field():
    """A typo'd ``max_turn=`` that quietly did nothing would surface much
    later as an unexplained stall."""
    with pytest.raises(TypeError):
        EngineConfig().with_overrides(max_turn=5)


def test_the_rejection_names_the_unknown_field_and_lists_the_known_ones():
    with pytest.raises(TypeError) as caught:
        EngineConfig().with_overrides(max_turn=5)

    message = str(caught.value)
    assert "max_turn" in message
    assert "max_turns" in message
    assert "empty_output_placeholder" in message


def test_the_rejection_is_a_type_error_not_an_engine_error():
    """A misspelled keyword argument is a mistake at the call site — the
    same one the constructor already raises — and must not be catchable
    alongside a genuine run failure."""
    with pytest.raises(TypeError):
        EngineConfig(max_turn=5)  # type: ignore[call-arg]
    with pytest.raises(TypeError) as caught:
        EngineConfig().with_overrides(max_turn=5)
    assert not isinstance(caught.value, EngineError)


def test_engine_config_is_frozen():
    """Two runs driven by one engine must not observe each other's limits
    changing mid-flight."""
    config = EngineConfig()
    with pytest.raises(Exception):
        config.max_turns = 5  # type: ignore[misc]


# --- what this layer refuses to read --------------------------------------


def test_the_engine_is_configured_by_its_caller_and_by_nothing_else():
    """Plan 0027 §4 Q6: "this layer reads no environment variables".

    ``ProviderConfig`` resolves from the ambient shell because an API key
    has nowhere else to live. A turn ceiling that did the same would make
    two runs of one benchmark task incomparable, and the resulting stall
    would read as a model regression rather than as configuration.
    """
    source = inspect.getsource(config_module)
    assert "os.environ" not in source
    assert "getenv" not in source
    assert not hasattr(config_module, "os")


def test_the_module_exports_only_the_config():
    assert config_module.__all__ == ["EngineConfig"]
