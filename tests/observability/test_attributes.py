"""The names are a wire contract, so they are checked rather than trusted."""

from __future__ import annotations

import omicsclaw.observability.attributes as attrs
from omicsclaw.observability.attributes import INSTRUMENTS, InstrumentKind


def _constants(prefix: str) -> dict[str, str]:
    return {
        name: value
        for name, value in vars(attrs).items()
        if name.startswith(prefix) and isinstance(value, str)
    }


def test_every_declared_instrument_has_a_kind_a_unit_and_a_description():
    """An instrument with a blank axis reaches a dashboard silently."""
    metrics = set(_constants("METRIC_").values())

    assert metrics, "no instruments declared"
    assert metrics == set(INSTRUMENTS), (
        "every METRIC_ constant must appear in INSTRUMENTS and vice versa"
    )
    for name, (kind, unit, description) in INSTRUMENTS.items():
        assert kind in {InstrumentKind.COUNTER, InstrumentKind.HISTOGRAM}, name
        assert unit, name
        assert description, name


def test_the_six_instruments_of_the_reference_are_all_present():
    """Parity, named one by one so a deletion is a failing test."""
    assert set(INSTRUMENTS) == {
        "omicsclaw.llm.request.duration",
        "omicsclaw.llm.tokens.input",
        "omicsclaw.llm.tokens.output",
        "omicsclaw.tool.calls.total",
        "omicsclaw.tool.execution.duration",
        "omicsclaw.agent.turns.total",
    }


def test_durations_are_seconds_and_counts_are_annotations():
    """UCUM for real units, ``{curly}`` for dimensionless — OTEL's rule."""
    for name, (kind, unit, _) in INSTRUMENTS.items():
        if kind == InstrumentKind.HISTOGRAM:
            assert unit == "s", name
        else:
            assert unit.startswith("{") and unit.endswith("}"), name


def test_the_four_span_names_are_distinct_and_namespaced():
    names = _constants("SPAN_")

    assert len(set(names.values())) == 4
    assert all(value.startswith("omicsclaw.") for value in names.values())


def test_no_attribute_key_collides_with_another():
    """Two constants with one value is a rename half-done."""
    keys = _constants("ATTR_")
    duplicated = {
        value for value in keys.values() if list(keys.values()).count(value) > 1
    }

    assert not duplicated, f"two names share {duplicated}"


def test_the_genai_keys_are_the_specification_s_and_not_ours():
    assert attrs.ATTR_GENAI_SYSTEM == "gen_ai.system"
    assert attrs.ATTR_GENAI_REQUEST_MODEL == "gen_ai.request.model"
    assert attrs.ATTR_GENAI_INPUT_TOKENS == "gen_ai.usage.input_tokens"
    assert attrs.ATTR_GENAI_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"


def test_the_langfuse_keys_are_the_v4_ones():
    """``langfuse.input`` lands in metadata instead of the Input pane."""
    langfuse = _constants("ATTR_LANGFUSE_")

    assert set(langfuse.values()) == {
        "langfuse.trace.input",
        "langfuse.trace.output",
        "langfuse.observation.input",
        "langfuse.observation.output",
    }


def test_instruments_cannot_be_edited_at_runtime():
    import pytest

    with pytest.raises(TypeError):
        INSTRUMENTS["x"] = (InstrumentKind.COUNTER, "{x}", "x")  # type: ignore[index]
