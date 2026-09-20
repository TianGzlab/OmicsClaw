"""The three shapes this layer records into, and the free default.

:class:`Span`, :class:`Tracer` and :class:`Meter` — Protocols, plus a
no-op implementation of each. Everything else in this package programs
against these and never against a vendor, which is the same ruling
:mod:`omicsclaw.provider` makes about model backends and for the same
payoff: adding a backend is a new file, not an edit to the recorder.

**Why not simply depend on ``opentelemetry-api``.** That package ships
its own no-op and would make this module three lines. It was rejected on
two grounds, both checkable rather than aesthetic:

1. *It would be a hard dependency of an optional feature.* Every other
   layer in this rebuild is importable with nothing installed —
   ``provider/base.py`` says so in its own docstring — and a telemetry
   contract that cannot be imported without a third-party package would
   make ``import omicsclaw.entry`` fail on a machine that never wanted
   telemetry.
2. *It would decide the data model before the deployment does.* The
   OTEL API's ``Span`` carries events, links, status codes and a context
   API this package deliberately does not use (see
   :mod:`omicsclaw.observability.scope` on explicit parenting). Writing
   against the full interface and using a tenth of it is how the tenth
   becomes hard to find.

What is given up is real and is named so nobody rediscovers it: a
third-party OpenTelemetry instrumentation — an HTTP client, a database
driver — will **not** nest inside these spans, because it programs
against OTEL's context and this package does not put anything there.
:mod:`omicsclaw.observability.otel` does set the global tracer provider,
so such a library still exports to the same pipeline; its spans simply
arrive as roots of their own. Closing that gap means putting each span
into OTEL's context as well, which is a change to one adapter and not to
this contract.

**Three methods on a span, not ten.** The set is exactly what
``internal/observability`` uses across its three instrumented seams, and
adding a fourth should require a seam that needs it.

Stdlib only.
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

__all__ = [
    "NOOP_METER",
    "NOOP_SPAN",
    "NOOP_TRACER",
    "AttributeValue",
    "Meter",
    "NoopMeter",
    "NoopSpan",
    "NoopTracer",
    "Span",
    "Tracer",
]

AttributeValue = str | bool | int | float
"""What may be the value of a span attribute.

The four scalar types OTLP can serialize. Deliberately **not**
``Sequence`` — OTLP permits homogeneous arrays, nothing in this layer
records one, and allowing them would mean every backend adapter has to
decide what a mixed list means.

``bool`` is listed before ``int`` for readers, not for the type checker:
in Python ``bool`` *is* an ``int``, and a backend that dispatches on type
must therefore test ``bool`` first or record ``True`` as ``1``.
:class:`~omicsclaw.observability.console.ConsoleTracer` does; a backend
that forgets is caught by
``tests/observability/test_console.py::test_a_bool_attribute_stays_a_bool``.
"""


@runtime_checkable
class Span(Protocol):
    """One timed unit of work, already started.

    Started by :meth:`Tracer.start_span` and finished by :meth:`end`.
    There is no context-manager protocol here on purpose: a
    :data:`~omicsclaw.observability.attributes.SPAN_TURN` outlives the
    function that opens it and an ``async with`` cannot express that, so
    offering one would make the shortest path the wrong one for the case
    this package actually has.

    **Every method must be safe to call more than once and safe to call
    after :meth:`end`.** That is not politeness: the cancellation paths in
    :class:`~omicsclaw.observability.scope.RunScope` close whatever is
    open from two places, and a contract where the second close raises
    would turn a cancelled run into a crash inside telemetry.
    """

    def set_attributes(self, attributes: Mapping[str, AttributeValue]) -> None:
        """Record several attributes at once.

        A mapping rather than ``**kwargs`` because the keys are dotted
        (``gen_ai.request.model``) and are not Python identifiers. Plural
        rather than singular because every caller in this package has
        several to set and a backend can batch them.
        """
        ...

    def record_error(self, error: BaseException) -> None:
        """Mark this span as having failed, with *error* as the cause.

        A backend should record the exception's **type** and may record
        its message; callers in this package that must not leak an
        argument set a redacted attribute themselves and pass nothing
        here. See :class:`~omicsclaw.observability.hook.TracingHook`.
        """
        ...

    def end(self) -> None:
        """Stop the clock and hand the span to the exporter."""
        ...


@runtime_checkable
class Tracer(Protocol):
    """Starts spans. One method.

    **Parenting is an argument, not ambient state**, which is the single
    most consequential difference between this contract and the OTEL API
    it is usually backed by. The reference harness threads a
    ``context.Context`` through every call and writes each span into
    **two** slots — the OTEL one and a private key — then re-asserts the
    parent before starting a child (``observer.go:67-68`` writes both for
    the interaction; ``observer.go:101-102`` restores it before the turn
    span is started), because middle layers replace the ctx and the
    private copy is what survives. Python's equivalent would be a
    :class:`~contextvars.ContextVar`, and this package does use one — but
    only to answer *which span is current* (see
    :mod:`omicsclaw.observability.scope`), never to pass it. By the time
    a tracer is called the parent is an object in hand, so a span tree
    that comes out wrong is a bug in one readable expression rather than
    in the interaction between three layers' context handling.
    """

    def start_span(
        self,
        name: str,
        *,
        parent: Span | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> Span:
        """Begin a span now. ``parent=None`` starts a new trace."""
        ...


@runtime_checkable
class Meter(Protocol):
    """Records measurements. Two methods, one per instrument kind.

    Instruments are addressed **by name** rather than created and held,
    which is where this departs from both OTEL's API and the reference's
    use of it. The reference constructs six instruments across three
    constructors, each of which can fail and each of which therefore
    makes its owner's constructor return an ``error``
    (``hook.go:44-66``). Here the names live in
    :data:`~omicsclaw.observability.attributes.INSTRUMENTS`, a backend
    resolves them once, and no seam in this package has a fallible
    constructor because of telemetry.
    """

    def count(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        """Add to a monotonic counter."""
        ...

    def record(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        """Record one observation into a histogram."""
        ...


class NoopSpan:
    """A span that does nothing, allocates nothing, and is a singleton.

    ``__slots__ = ()`` and no state, so :data:`NOOP_SPAN` can be shared by
    every caller in every task — there is nothing to race on.
    """

    __slots__ = ()

    def set_attributes(self, attributes: Mapping[str, AttributeValue]) -> None:
        return None

    def record_error(self, error: BaseException) -> None:
        return None

    def end(self) -> None:
        return None


NOOP_SPAN = NoopSpan()
"""The one instance. Identity is testable, which is how
``tests/observability/test_contract.py`` pins that the disabled path
allocates nothing per call."""


class NoopTracer:
    """Hands out :data:`NOOP_SPAN` and ignores everything else."""

    __slots__ = ()

    def start_span(
        self,
        name: str,
        *,
        parent: Span | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> Span:
        return NOOP_SPAN


class NoopMeter:
    """Drops every measurement."""

    __slots__ = ()

    def count(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        return None

    def record(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        return None


NOOP_TRACER = NoopTracer()
NOOP_METER = NoopMeter()
"""The disabled deployment's whole telemetry stack.

:func:`~omicsclaw.observability.telemetry.build_telemetry` returns a
:class:`~omicsclaw.observability.telemetry.Telemetry` over these two when
nothing switched observability on, and the seams then wrap nothing at all
— see :meth:`~omicsclaw.observability.telemetry.Telemetry.trace_provider`,
which hands the provider straight back. The object graph of a deployment
that does not observe is byte-for-byte the one it had before this package
existed, which is the property :func:`~omicsclaw.hooks.hook_tools`
established for hooks and the one that makes "is telemetry implicated?"
answerable by looking rather than by bisecting.
"""
