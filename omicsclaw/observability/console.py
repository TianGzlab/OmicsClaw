"""A working backend with nothing installed: JSON lines and a metric summary.

Satisfies :data:`~omicsclaw.observability.config.ExporterType.STDOUT`.
The reference's equivalent is an OpenTelemetry SDK component
(``stdouttrace`` / ``stdoutmetric``); this one is **standard library
only**, and the difference buys two things worth having:

- a contributor can see the trace tree of a real run without installing
  anything, which is the state a bug report usually arrives in;
- the test suite can exercise a genuine backend end to end, so the
  contract in :mod:`omicsclaw.observability.contract` is pinned by
  something other than the no-op that trivially satisfies it.

**Where it writes, and why that is not stdout.** The name of the exporter
type is the reference's, kept for parity; the stream is
:data:`sys.stderr`, kept for survival. Two of this repository's three
surfaces draw on stdout — ``oc tui`` owns the whole screen and ``oc
interactive`` owns the line — so a span printed there corrupts the thing
the user is looking at. stderr is also where the reference sends its OTEL
*error* handler output, and for the same stated reason.

Imports this package and the standard library. No vendor SDK, which is
what makes it the fallback when :mod:`omicsclaw.observability.otel`
cannot load.
"""

from __future__ import annotations

import json
import secrets
import sys
import threading
import time
from typing import IO, Any, Mapping

from .attributes import INSTRUMENTS, InstrumentKind
from .contract import AttributeValue, Span

__all__ = ["ConsoleMeter", "ConsoleSpan", "ConsoleTracer", "MetricSnapshot"]


class ConsoleSpan:
    """One span, written as a single JSON object when it ends.

    **Written on :meth:`end`, not on start**, so a line carries a
    duration. The consequence is an ordering a reader has to know about:
    children end before their parents, so the file reads inner-out. That
    is the same order a batching OTLP exporter delivers in, and pairing
    them up is what :attr:`span_id` and ``parent_span_id`` are for.
    """

    __slots__ = (
        "_attributes",
        "_ended",
        "_error",
        "_name",
        "_parent_id",
        "_span_id",
        "_start",
        "_stream",
        "_lock",
        "_trace_id",
    )

    def __init__(
        self,
        stream: IO[str],
        lock: threading.Lock,
        name: str,
        *,
        trace_id: str,
        span_id: str,
        parent_id: str = "",
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> None:
        self._stream = stream
        self._lock = lock
        self._name = name
        self._trace_id = trace_id
        self._span_id = span_id
        self._parent_id = parent_id
        self._attributes: dict[str, AttributeValue] = dict(attributes or {})
        self._start = time.perf_counter()
        self._ended = False
        self._error = ""

    @property
    def trace_id(self) -> str:
        """Shared by every span of one interaction. Inherited from the
        parent, minted when there is none."""
        return self._trace_id

    @property
    def span_id(self) -> str:
        """This span's own identifier, referenced by its children."""
        return self._span_id

    @property
    def attributes(self) -> Mapping[str, AttributeValue]:
        """What has been set so far. Exposed for tests, which is the only
        way to assert on a span that has not been written yet."""
        return dict(self._attributes)

    def set_attributes(self, attributes: Mapping[str, AttributeValue]) -> None:
        """Merge. A later write to the same key wins, and that is how
        :class:`~omicsclaw.observability.provider.TracedProvider` records
        a model name up front and a token count afterwards."""
        self._attributes.update(attributes)

    def record_error(self, error: BaseException) -> None:
        """Keep the exception's class name. **Not its message.**

        The strict half of the rule ``hooks/audit.py`` argues for, applied
        here to every caller rather than only to tools: a message quotes
        the argument that failed, a span is a record that leaves the
        process, and a backend shipping ``FileNotFoundError:
        /data/GSE12345/patient_07.h5ad`` has exported a filename. A
        caller that has a *safe* string to add sets an attribute itself —
        :class:`~omicsclaw.observability.provider.TracedProvider` does,
        because a provider's error text is written by the vendor's SDK
        about an HTTP exchange.
        """
        self._error = type(error).__name__

    def end(self) -> None:
        """Write the line. Calling twice writes once.

        Idempotence is required by :class:`~omicsclaw.observability.contract.Span`
        and is load-bearing here: a cancelled run closes an open turn span
        from both :meth:`~omicsclaw.observability.scope.RunScope.observe`
        and the scope's exit, and a second line would double-count the
        turn in whatever reads the file.
        """
        if self._ended:
            return
        self._ended = True
        record: dict[str, Any] = {
            "name": self._name,
            "trace_id": self._trace_id,
            "span_id": self._span_id,
            "parent_span_id": self._parent_id,
            "duration_s": round(time.perf_counter() - self._start, 6),
            "attributes": dict(self._attributes),
        }
        if self._error:
            record["error"] = self._error
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


class ConsoleTracer:
    """Starts :class:`ConsoleSpan` objects against one stream.

    The lock is shared with every span it makes, because a turn's tool
    spans end concurrently and two interleaved ``write`` calls produce one
    unparseable line. It is a :class:`threading.Lock` rather than an
    :class:`asyncio.Lock` on purpose: :meth:`ConsoleSpan.end` is
    synchronous — a span must be closeable from a ``finally`` that cannot
    await — and an asyncio lock would force every closer to be a
    coroutine.
    """

    __slots__ = ("_lock", "_stream")

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream = sys.stderr if stream is None else stream
        self._lock = threading.Lock()

    def start_span(
        self,
        name: str,
        *,
        parent: Span | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> Span:
        """Begin a span, inheriting *parent*'s trace when there is one.

        A *parent* that is not a :class:`ConsoleSpan` — a
        :data:`~omicsclaw.observability.contract.NOOP_SPAN` left over from
        a reconfiguration, another backend's span — is treated as no
        parent at all rather than raising. A mixed stack is a composition
        mistake that deserves a broken trace tree, not a crashed run.
        """
        if isinstance(parent, ConsoleSpan):
            trace_id, parent_id = parent.trace_id, parent.span_id
        else:
            trace_id, parent_id = secrets.token_hex(16), ""
        return ConsoleSpan(
            self._stream,
            self._lock,
            name,
            trace_id=trace_id,
            span_id=secrets.token_hex(8),
            parent_id=parent_id,
            attributes=attributes,
        )


class MetricSnapshot:
    """What one instrument has accumulated, for one attribute combination."""

    __slots__ = ("count", "maximum", "minimum", "total")

    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.minimum = float("inf")
        self.maximum = float("-inf")

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    def as_dict(self, kind: str) -> dict[str, Any]:
        """A counter reports its total; a histogram reports its shape.

        Splitting on kind rather than always printing both is what keeps
        the summary readable: ``min``/``max`` on a token counter are the
        size of individual requests, which is a different question from
        the one the counter was created to answer.
        """
        if kind == InstrumentKind.COUNTER:
            return {"total": round(self.total, 6), "count": self.count}
        return {
            "count": self.count,
            "total": round(self.total, 6),
            "min": round(self.minimum, 6),
            "max": round(self.maximum, 6),
            "mean": round(self.total / self.count, 6) if self.count else 0.0,
        }


class ConsoleMeter:
    """Accumulates in memory; writes one summary when the process is done.

    **Aggregating rather than printing each measurement** is the whole
    design. A single turn records two token counters and a duration per
    model call and three more per tool, so a line-per-measurement meter
    would bury the span lines it shares a stream with — and the numbers
    only mean something summed anyway.

    An instrument name that is not in
    :data:`~omicsclaw.observability.attributes.INSTRUMENTS` is still
    recorded, filed as a histogram. Dropping it would make a typo in a
    caller invisible; this way it shows up in the summary under the wrong
    shape, which is the form of wrong that gets noticed.
    """

    __slots__ = ("_lock", "_series", "_stream")

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream = sys.stderr if stream is None else stream
        self._lock = threading.Lock()
        self._series: dict[tuple[str, tuple[tuple[str, str], ...]], MetricSnapshot] = {}

    def count(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._observe(name, float(value), attributes)

    def record(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._observe(name, float(value), attributes)

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """Everything accumulated so far, grouped by instrument.

        The read path for tests, and the one
        :meth:`dump` renders. Sorted by attribute key so two runs of the
        same shape produce the same ordering — the property that lets a
        diff over two summaries mean something, which is the same
        argument ``hooks/audit.py`` makes for sorting its JSON keys.
        """
        with self._lock:
            items = sorted(self._series.items())
        grouped: dict[str, list[dict[str, Any]]] = {}
        for (name, attrs), snapshot in items:
            kind = INSTRUMENTS.get(name, (InstrumentKind.HISTOGRAM, "", ""))[0]
            entry: dict[str, Any] = {"attributes": dict(attrs)}
            entry.update(snapshot.as_dict(kind))
            grouped.setdefault(name, []).append(entry)
        return grouped

    def dump(self) -> None:
        """Write the summary, once, if there is anything to say.

        Silence when nothing was recorded, so a run that made no model
        call leaves no trace of the meter at all — the same property
        :class:`~omicsclaw.hooks.JsonlAuditSink` gets by creating its
        directory on first write.
        """
        summary = self.snapshot()
        if not summary:
            return
        line = json.dumps({"metrics": summary}, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def _observe(
        self, name: str, value: float, attributes: Mapping[str, str] | None
    ) -> None:
        key = (name, tuple(sorted((attributes or {}).items())))
        with self._lock:
            series = self._series.get(key)
            if series is None:
                series = self._series[key] = MetricSnapshot()
            series.observe(value)
