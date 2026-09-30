"""Whether to observe, where to send it, and whether payloads may leave.

One frozen record read from the environment, mirroring
``observability/config.go``. Four of its five fields are the reference's;
the fifth — :attr:`ObservabilityConfig.capture_content` — is this
repository's, and it is the one to read before anything else in this
package.

**Why the environment, when :class:`~omicsclaw.engine.EngineConfig`
argues against it.** That argument is specific and does not reach here:
a turn ceiling read from the ambient shell makes two runs of the same
benchmark incomparable and the resulting stall looks like a model
regression. Telemetry changes no decision the agent makes — switching it
on cannot alter a trajectory — so the failure mode that ruling exists to
prevent does not exist for these fields. What does apply is the reason
:mod:`omicsclaw.provider` reads its own credentials: an OTLP bearer token
has nowhere else to live, and threading five more fields through
:class:`~omicsclaw.entry.config.AppConfig` would put a secret in the
record a surface prints when it reports its configuration.

Stdlib only. Reading this module must not require the OpenTelemetry SDK
to be installed, because deciding *not* to observe is the common case.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from .attributes import DEFAULT_SERVICE_NAME

__all__ = ["ExporterType", "ObservabilityConfig", "parse_otlp_headers"]

_TRUE = frozenset({"1", "true", "yes", "on"})
"""What counts as *yes* for the two boolean variables.

The reference accepts the single string ``"true"`` and treats everything
else as off. Widened here for one reason found in this repository's own
``.env.example``, which already spells booleans as ``1``: a deployment
that writes ``OTEL_ENABLED=1``, gets silence, and has no error to search
for will conclude the feature is broken. Compared lower-cased and
stripped.
"""


class ExporterType(StrEnum):
    """Where spans and measurements go. Three, as in the reference.

    A :class:`~enum.StrEnum` so a value survives a round trip through an
    environment variable or a log line without a converter, the same
    reason :class:`~omicsclaw.hooks.HookAction` is one.
    """

    NOOP = "noop"
    """Record nothing, at no cost. The default, and what an unrecognised
    value degrades to.

    Degrading rather than raising is deliberate and is the direction this
    whole package fails in: a typo in ``OTEL_EXPORTER_TYPE`` must not
    stop an analysis run from starting. It is logged once by
    :func:`~omicsclaw.observability.telemetry.build_telemetry`, which is
    the difference between failing open and failing silently.
    """

    STDOUT = "stdout"
    """Write JSON lines to a stream — development and debugging.

    Satisfied by :mod:`omicsclaw.observability.console`, which is
    **standard library only**. That is a deliberate departure from the
    reference, whose ``stdout`` exporter is an OTEL SDK component: here
    it means a contributor can see the trace tree of a run, and the whole
    test suite can exercise a real backend, with nothing installed.
    """

    OTLP = "otlp"
    """Export over OTLP/HTTP — Langfuse, Grafana, Jaeger, anything else
    speaking the protocol. The only value that needs the OpenTelemetry
    SDK; without it this degrades to :attr:`NOOP` with one warning."""


def parse_otlp_headers(raw: str) -> Mapping[str, str]:
    """Parse ``key1=val1,key2=val2`` into a mapping.

    The OTLP convention, and the reference's implementation
    (``config.go:60-80``) split at the **first** ``=`` so a value may
    contain more of them — which a bearer token routinely does. A pair
    with no ``=`` at all is dropped rather than kept with an empty value,
    because a header whose value nobody wrote is not a header anybody
    meant to send.

    Returns a read-only mapping, so a caller cannot edit one deployment's
    credentials into another's config record.
    """
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        key, sep, value = pair.partition("=")
        if not sep:
            continue
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return MappingProxyType(headers)


_EMPTY_HEADERS: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """What this deployment asked for. Frozen, like every other config here.

    The default instance observes nothing, which is what makes
    ``ObservabilityConfig()`` a usable answer for a test, a script, or a
    skill runner that never wanted telemetry.
    """

    enabled: bool = False
    """``OTEL_ENABLED``. Off unless a deployment says otherwise.

    Off by default for the same reason
    :attr:`~omicsclaw.entry.config.AppConfig.audit_log` has no default
    location: telemetry that appears without being asked for is a record
    about a person written because nobody said no.
    """

    service_name: str = DEFAULT_SERVICE_NAME
    """``OTEL_SERVICE_NAME``. What a backend groups this process under."""

    exporter: ExporterType = ExporterType.NOOP
    """``OTEL_EXPORTER_TYPE``."""

    otlp_endpoint: str = ""
    """``OTEL_EXPORTER_OTLP_ENDPOINT`` — the **base** URL, without
    ``/v1/traces``.

    The suffix is appended explicitly by
    :mod:`omicsclaw.observability.otel` rather than left to the SDK, which
    is the reference's hard-won note (``setup.go:85-86``): SDK versions
    have disagreed about whether they append it, and the symptom of
    guessing wrong is a 404 nobody sees.
    """

    otlp_headers: Mapping[str, str] = field(default_factory=lambda: _EMPTY_HEADERS)
    """``OTEL_EXPORTER_OTLP_HEADERS``, parsed. Typically one
    ``Authorization`` header.

    **Never render this.** It holds a credential, and this record is
    reachable from :class:`~omicsclaw.observability.Telemetry`, which a
    surface may well print when reporting its configuration.
    :meth:`__repr__` is overridden for exactly that reason.
    """

    capture_content: bool = False
    """``OMICSCLAW_OTEL_CAPTURE_CONTENT``. Off, and the default is a
    safety property rather than a preference.

    **This field has no counterpart in the reference harness, which
    always captures.** ``observability/provider.go`` serializes the whole
    message list into a span attribute and ``observability/hook.go`` puts
    every tool's arguments and output into two more, so enabling OTLP
    export there ships the conversation to a third party. In a coding
    harness that is a reasonable default. Here it is not:
    :data:`~omicsclaw.entry.assembly.SAFETY_RULES` rule 1 states *"Genetic
    data never leaves this machine — all processing is local"*, and a
    prompt in this deployment routinely
    quotes a patient cohort, a file path under a sequencing run, or the
    output of a differential-expression call.

    So with this off — the default — a span carries names, counts,
    durations, token usage, model, outcome and turn structure, and **no
    payload**: no message, no tool argument, no tool output. Everything a
    dashboard needs to answer "is it working, what does it cost, what is
    slow" survives; nothing that names a person or a gene leaves the
    process.

    Switching it on is a deployment's decision to make and is why the
    field exists rather than the capture being deleted outright — a
    Langfuse project on a machine that also holds the data is a
    legitimate setup, and prompt debugging needs the payload. It is
    ``OMICSCLAW_``-prefixed, not ``OTEL_``-prefixed, because no
    OpenTelemetry specification defines it and pretending otherwise would
    invite somebody to look for it in the wrong documentation.
    """

    def __post_init__(self) -> None:
        """Coerce what a hand-written config is likely to hold.

        **A raw ``"stdout"`` used to build an inactive deployment in
        silence**, which is the worst shape a configuration bug can have.
        :class:`ExporterType` is a :class:`~enum.StrEnum`, so
        ``config.exporter == "stdout"`` was true while
        ``config.exporter is ExporterType.STDOUT`` — the comparison this
        package uses everywhere, and the one an enum deserves — was not.
        Coercing here means the identity comparisons downstream are
        sound for every way one of these is built, rather than only for
        :meth:`from_env`.

        An unrecognised string degrades to :attr:`ExporterType.NOOP`, the
        same answer :meth:`from_env` gives it and for the same reason.

        The headers are made read-only for the reason
        :meth:`from_env` already returns them that way: this record holds
        a credential and a caller must not be able to edit one
        deployment's into another's.
        """
        if not isinstance(self.exporter, ExporterType):
            try:
                coerced = ExporterType(str(self.exporter).strip().lower())
            except ValueError:
                coerced = ExporterType.NOOP
            object.__setattr__(self, "exporter", coerced)
        if not isinstance(self.otlp_headers, MappingProxyType):
            object.__setattr__(
                self, "otlp_headers", MappingProxyType(dict(self.otlp_headers))
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ObservabilityConfig:
        """Read the five variables. *env* defaults to :data:`os.environ`.

        Taking the mapping as an argument is what lets
        ``tests/observability/test_config.py`` cover every branch without
        mutating the process environment — a test that does mutate it
        leaks into whatever runs next under ``pytest -p xdist``, and this
        module's variables are global by nature.

        An unrecognised ``OTEL_EXPORTER_TYPE`` becomes :attr:`
        ExporterType.NOOP`; see there for why it does not raise.
        """
        source = os.environ if env is None else env
        raw_exporter = source.get("OTEL_EXPORTER_TYPE", "").strip().lower()
        try:
            exporter = ExporterType(raw_exporter)
        except ValueError:
            exporter = ExporterType.NOOP
        return cls(
            enabled=_flag(source.get("OTEL_ENABLED")),
            service_name=(
                source.get("OTEL_SERVICE_NAME", "").strip() or DEFAULT_SERVICE_NAME
            ),
            exporter=exporter,
            otlp_endpoint=source.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip(),
            otlp_headers=parse_otlp_headers(
                source.get("OTEL_EXPORTER_OTLP_HEADERS", "")
            ),
            capture_content=_flag(source.get("OMICSCLAW_OTEL_CAPTURE_CONTENT")),
        )

    @property
    def records(self) -> bool:
        """Whether anything at all will be recorded.

        ``enabled`` and ``exporter`` are two switches for one question and
        a caller should not have to remember that both must agree — which
        is the reference's ``if !cfg.Enabled || cfg.Exporter ==
        ExporterNoop`` repeated at every call site.
        """
        return self.enabled and self.exporter is not ExporterType.NOOP

    def __repr__(self) -> str:
        """Everything except the headers, which hold a credential.

        A redacted count rather than an omission: ``headers=2`` is what
        tells an operator whose export is silently unauthenticated that
        their ``OTEL_EXPORTER_OTLP_HEADERS`` never parsed, which is the
        one question about this field that a log can answer.
        """
        return (
            f"{type(self).__name__}(enabled={self.enabled!r}, "
            f"service_name={self.service_name!r}, "
            f"exporter={self.exporter.value!r}, "
            f"otlp_endpoint={self.otlp_endpoint!r}, "
            f"headers={len(self.otlp_headers)}, "
            f"capture_content={self.capture_content!r})"
        )


def _flag(raw: str | None) -> bool:
    """One environment variable read as a boolean."""
    return raw is not None and raw.strip().lower() in _TRUE
