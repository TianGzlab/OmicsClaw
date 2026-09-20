"""The one object a composition root holds, and the one function that builds it.

:class:`Telemetry` is this layer's ``Providers`` (``setup.go:33-43``) with
the three seams folded in, so that ``entry/assembly.py`` asks for
telemetry once and then never branches on whether it got any. That is the
design constraint this module exists to satisfy:

**a deployment that does not observe must not be a different deployment.**
``Telemetry()`` — the default instance — is a real, usable object whose
tracer is the no-op, whose :meth:`trace_provider` hands the provider
straight back, and whose :meth:`tool_hooks` returns ``()``. So the
composition root has no ``if telemetry is not None`` anywhere, and the
object graph of an unobserved run is byte-for-byte what it was before this
package existed — the property :func:`~omicsclaw.hooks.hook_tools`
established for hooks, restated here because it is what makes "could
telemetry be implicated in this bug?" answerable by looking.

**Blocking work is moved off the event loop.** ``force_flush`` and
``shutdown`` are synchronous in every OTEL SDK — the first waits on an
HTTP round trip, the second joins a background thread — and the reference
simply blocks its caller. Here they are awaited through
:func:`asyncio.to_thread`, because the caller is a turn that has just
finished and the next thing it wants to do is answer somebody.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Sequence

from omicsclaw.hooks import ToolHook
from omicsclaw.provider import LLMProvider

from .config import ExporterType, ObservabilityConfig
from .console import ConsoleMeter, ConsoleTracer
from .contract import NOOP_METER, NOOP_TRACER, Meter, Tracer
from .hook import TracingHook
from .otel import build_otel_backend
from .provider import TracedProvider
from .scope import RunScope

_log = logging.getLogger(__name__)

__all__ = ["Telemetry", "build_telemetry"]


@dataclass(frozen=True, slots=True)
class Telemetry:
    """A recorder, a meter, and the three ways to attach them.

    Frozen, like every other configuration-shaped record in this rebuild,
    and for the sharpest version of the reason: a live backend that could
    be swapped underneath a running exchange would give one interaction a
    tracer at its root span and a different one at its leaves, which is a
    broken trace with no error anywhere.
    """

    tracer: Tracer = NOOP_TRACER
    meter: Meter = NOOP_METER
    config: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    """What was asked for — **not** what was achieved. An OTLP export that
    could not be built leaves this saying ``otlp`` while :attr:`active` is
    ``False``, which is the pair of facts an operator needs: the
    configuration was read, and it did not take."""

    on_flush: Callable[[], None] | None = None
    on_shutdown: Callable[[], None] | None = None

    @property
    def active(self) -> bool:
        """Whether anything is actually being recorded.

        Identity against :data:`~omicsclaw.observability.contract.NOOP_TRACER`
        rather than a stored flag, so the answer cannot drift from the
        object graph it describes.
        """
        return self.tracer is not NOOP_TRACER

    def run(
        self,
        *,
        session_id: str = "",
        prompt: str = "",
        agent_type: str = "main",
        turn_events: bool = True,
    ) -> RunScope:
        """A scope for one exchange. Always returns one, even when inactive.

        An inactive scope opens no-op spans and costs one object per
        exchange, which is the price of letting
        ``entry/turn.py`` be written once::

            async with app.telemetry.run(session_id=sid, prompt=text) as scope:
                async for event in app.engine.run_stream(...):
                    scope.observe(event)
                    yield event

        Pass ``turn_events=False`` when driving
        :meth:`~omicsclaw.engine.AgentEngine.run`, which drops the events
        a turn boundary would be read from; see
        :attr:`~omicsclaw.observability.scope.RunScope.turn_events`.
        """
        return RunScope(
            self.tracer,
            self.meter,
            session_id=session_id,
            prompt=prompt,
            capture_content=self.config.capture_content,
            agent_type=agent_type,
            turn_events=turn_events,
            flush=self.force_flush if self.on_flush is not None else None,
        )

    def trace_provider(self, inner: LLMProvider, *, model: str = "") -> LLMProvider:
        """Wrap *inner*, or hand it back unchanged when inactive.

        Returning the argument is not an optimisation: it is what makes an
        unobserved deployment's provider chain identical to the one it had
        before, so ``tests/entry/test_assembly.py``'s existing assertions
        about what ``app.provider`` is keep holding.
        """
        if not self.active:
            return inner
        return TracedProvider(
            inner,
            self.tracer,
            self.meter,
            model=model,
            capture_content=self.config.capture_content,
        )

    def tool_hooks(self) -> Sequence[ToolHook]:
        """The hooks to append to a chain — one, or none.

        A sequence rather than an optional single hook so the caller
        writes ``(*build_hooks(config), *telemetry.tool_hooks())`` and
        never a conditional. **Append**, never prepend: see
        :class:`~omicsclaw.observability.hook.TracingHook` on why it is
        mounted last and :class:`~omicsclaw.hooks.AuditHook` on why that
        one is mounted first.
        """
        if not self.active:
            return ()
        return (
            TracingHook(
                self.tracer,
                self.meter,
                capture_content=self.config.capture_content,
            ),
        )

    async def force_flush(self) -> None:
        """Push what has ended so far. Contains its own failures.

        Called at the end of every clean exchange by
        :class:`~omicsclaw.observability.scope.RunScope`, which is the
        reference's reason too (``observer.go:88-97``): a short session
        would otherwise sit in the batcher until a timer fires, and the
        person waiting to see their trace has already reloaded the page.

        Only :exc:`Exception` is contained. A
        :exc:`~asyncio.CancelledError` raised out of the worker thread's
        await is a real cancellation and is re-raised, the distinction
        ``omicsclaw/hooks/chain.py`` was repaired to respect.
        """
        if self.on_flush is None:
            return
        try:
            await asyncio.to_thread(self.on_flush)
        except Exception:
            _log.warning("telemetry could not be flushed", exc_info=True)

    async def aclose(self) -> None:
        """Shut the backend down and release what it holds.

        Idempotent in practice because every backend's shutdown is, and
        called from :meth:`~omicsclaw.entry.AgentApp.aclose` alongside the
        MCP servers, the sandbox and the memory database. A failure here
        is logged and swallowed: a process that is already exiting is not
        helped by an exception from its telemetry.
        """
        if self.on_shutdown is None:
            return
        try:
            await asyncio.to_thread(self.on_shutdown)
        except Exception:
            _log.warning("telemetry could not be shut down cleanly", exc_info=True)


def build_telemetry(config: ObservabilityConfig | None = None) -> Telemetry:
    """Resolve the configuration and build the backend it names.

    *config* defaults to
    :meth:`~omicsclaw.observability.config.ObservabilityConfig.from_env`;
    pass one to build a deployment that does not read the environment,
    which is what every test in ``tests/observability/`` does.

    **Every failure degrades to the no-op and says so once.** The
    reference treats a failed ``Setup`` as fatal, which is right for a
    harness whose whole job is the run; here the run may be a six-hour
    alignment and the telemetry is a nice-to-have, so a missing SDK, an
    unset endpoint or an exporter that will not construct costs one
    warning and nothing else.
    """
    resolved = ObservabilityConfig.from_env() if config is None else config
    if not resolved.records:
        return Telemetry(config=resolved)

    if resolved.exporter is ExporterType.STDOUT:
        meter = ConsoleMeter()
        return Telemetry(
            tracer=ConsoleTracer(),
            meter=meter,
            config=resolved,
            # No flush: the console tracer writes each span as it ends, so
            # there is nothing pending between exchanges. The meter
            # aggregates and reports once, at shutdown.
            on_shutdown=meter.dump,
        )

    backend = build_otel_backend(resolved)
    if backend is None:
        # build_otel_backend has already logged which of its four refusals
        # this was, so repeating it here would double every line.
        return Telemetry(config=resolved)
    return Telemetry(
        tracer=backend.tracer,
        meter=backend.meter,
        config=resolved,
        on_flush=backend.force_flush,
        on_shutdown=backend.shutdown,
    )
