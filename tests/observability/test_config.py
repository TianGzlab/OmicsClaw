"""``ObservabilityConfig`` reads five variables and hides one of them."""

from __future__ import annotations

import pytest

from omicsclaw.observability import ExporterType, ObservabilityConfig
from omicsclaw.observability.config import parse_otlp_headers


def test_nothing_set_observes_nothing():
    config = ObservabilityConfig.from_env({})

    assert config.enabled is False
    assert config.exporter is ExporterType.NOOP
    assert config.capture_content is False
    assert config.records is False


def test_the_default_instance_matches_an_empty_environment():
    """``ObservabilityConfig()`` is what a test or a script should get."""
    assert ObservabilityConfig() == ObservabilityConfig.from_env({})


@pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", " on "])
def test_the_spellings_of_yes_that_are_accepted(raw: str):
    """The reference accepts only ``true``; ``.env.example`` writes ``1``."""
    assert ObservabilityConfig.from_env({"OTEL_ENABLED": raw}).enabled is True


@pytest.mark.parametrize("raw", ["false", "0", "", "no", "enabled", "y"])
def test_the_spellings_that_are_not(raw: str):
    assert ObservabilityConfig.from_env({"OTEL_ENABLED": raw}).enabled is False


def test_an_unknown_exporter_degrades_rather_than_raising():
    """A typo must not stop a six-hour alignment from starting."""
    config = ObservabilityConfig.from_env(
        {"OTEL_ENABLED": "true", "OTEL_EXPORTER_TYPE": "jaegr"}
    )

    assert config.exporter is ExporterType.NOOP
    assert config.records is False


@pytest.mark.parametrize("raw", ["OTLP", " otlp ", "otlp"])
def test_the_exporter_name_is_case_and_space_insensitive(raw: str):
    config = ObservabilityConfig.from_env({"OTEL_EXPORTER_TYPE": raw})

    assert config.exporter is ExporterType.OTLP


def test_records_needs_both_switches():
    """Two variables, one question — ``records`` is the single answer."""
    enabled_only = ObservabilityConfig.from_env({"OTEL_ENABLED": "true"})
    exporter_only = ObservabilityConfig.from_env({"OTEL_EXPORTER_TYPE": "stdout"})
    both = ObservabilityConfig.from_env(
        {"OTEL_ENABLED": "true", "OTEL_EXPORTER_TYPE": "stdout"}
    )

    assert enabled_only.records is False
    assert exporter_only.records is False
    assert both.records is True


def test_the_service_name_falls_back_and_can_be_overridden():
    assert ObservabilityConfig.from_env({}).service_name == "omicsclaw"
    assert ObservabilityConfig.from_env({"OTEL_SERVICE_NAME": " "}).service_name == (
        "omicsclaw"
    )
    assert (
        ObservabilityConfig.from_env({"OTEL_SERVICE_NAME": "bench"}).service_name
        == "bench"
    )


def test_a_header_value_may_contain_the_separator():
    """A bearer token routinely does; splitting on every ``=`` truncates it."""
    headers = parse_otlp_headers("Authorization=Basic a=b=c,X-Trace=1")

    assert headers == {"Authorization": "Basic a=b=c", "X-Trace": "1"}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", {}),
        ("novalue", {}),
        ("=orphan", {}),
        (" k = v ", {"k": "v"}),
        ("a=1,,b=2", {"a": "1", "b": "2"}),
    ],
)
def test_header_parsing_edges(raw: str, expected: dict[str, str]):
    assert dict(parse_otlp_headers(raw)) == expected


def test_parsed_headers_cannot_be_edited():
    """One deployment's credentials must not be writable into another's."""
    config = ObservabilityConfig.from_env({"OTEL_EXPORTER_OTLP_HEADERS": "a=1"})

    with pytest.raises(TypeError):
        config.otlp_headers["b"] = "2"  # type: ignore[index]


def test_the_repr_never_prints_a_credential():
    """This record is reachable from ``Telemetry``, which a surface prints."""
    config = ObservabilityConfig.from_env(
        {
            "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic SUPERSECRET",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://example.test/otel",
        }
    )

    rendered = repr(config)

    assert "SUPERSECRET" not in rendered
    assert "Authorization" not in rendered
    assert "headers=1" in rendered, "the count is what diagnoses a parse failure"
    assert "https://example.test/otel" in rendered


def test_content_capture_is_off_unless_asked_for_by_its_own_variable():
    """The safety default.

    :data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1: genetic data never
    leaves the machine.
    """
    everything_on = ObservabilityConfig.from_env(
        {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_TYPE": "otlp",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://example.test",
        }
    )

    assert everything_on.records is True
    assert everything_on.capture_content is False

    asked = ObservabilityConfig.from_env({"OMICSCLAW_OTEL_CAPTURE_CONTENT": "true"})
    assert asked.capture_content is True


def test_the_capture_variable_is_not_otel_namespaced():
    """No OpenTelemetry specification defines it; the name must not imply one."""
    assert (
        ObservabilityConfig.from_env({"OTEL_CAPTURE_CONTENT": "true"}).capture_content
        is False
    )


def test_from_env_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_TYPE", "stdout")

    assert ObservabilityConfig.from_env().records is True


def test_the_record_is_frozen():
    config = ObservabilityConfig()

    with pytest.raises(Exception):
        config.enabled = True  # type: ignore[misc]
