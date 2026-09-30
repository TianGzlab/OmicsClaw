"""The composition root's obligations to the observability layer.

Four of them, in the order they would go wrong.

**A deployment that does not observe is unchanged.** Not "behaves the
same": *is the same objects*. ``app.provider`` is the provider
``provider_from_env`` returned, and no tool has grown a wrapper. This is
what makes the layer cheap to add — a regression in an unobserved
deployment cannot be blamed on it.

**``app.telemetry`` is never ``None``.** The default
:class:`~omicsclaw.observability.Telemetry` records nothing and is a real
object, so ``entry/turn.py`` opens a scope unconditionally and no surface
has to know whether telemetry was configured.

**The tracing hook is mounted last and the audit hook first.** They want
opposite ends and for reasons that do not conflict: audit wants to *hear
about* a refusal, tracing wants to *not measure* one. Reverse either and
nothing raises — one loses its refusals, the other's span starts
measuring its neighbours.

**The blocking path declares that it reports no turns.** Miss it and a
five-turn run becomes one span labelled ``agent.turn=1``, which is a
wrong number rather than a missing level. Checked **twice**: once by
driving the real :func:`~omicsclaw.entry.turn.run_turn` against a real
recorder and reading the tree, and once by reading ``entry/turn.py`` as
text — the way ``tests/hooks/test_audit.py`` checks the session-id
spelling it may not import. The text check came first and was the only
one until a read-only evaluation pointed out what it cannot see: that
``scope.py`` and ``turn.py`` are each covered while the *join* between
them was not, and that a string count can in principle be satisfied by a
comment. Both are kept, because they fail for different reasons.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.assembly import build_app, build_hooks
from omicsclaw.entry.config import AppConfig
from omicsclaw.hooks import AuditHook, HookedTool
from omicsclaw.observability import (
    ExporterType,
    ObservabilityConfig,
    Telemetry,
    TracedProvider,
    TracingHook,
    build_telemetry,
)
from omicsclaw.permission import GatedTool
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role

_T = TypeVar("_T")


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, 10.0)

    return asyncio.run(guarded())


@dataclasses.dataclass
class _ScriptedProvider:
    """Structural conformance only; this file never calls a model."""

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None):
        return Completion(message=Message(role=Role.ASSISTANT, content="ok"))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError

    def bind(self, **overrides):
        return _ScriptedProvider()


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        assembly, "provider_from_env", lambda provider, model: _ScriptedProvider()
    )
    # build_telemetry reads the ambient OTEL_* variables; a developer who
    # has them exported must not change what these tests assert.
    monkeypatch.setattr(assembly, "build_telemetry", lambda: Telemetry())


def _config(workspace: pathlib.Path, **overrides: object) -> AppConfig:
    return AppConfig(workspace=workspace, **overrides)


def _active() -> Telemetry:
    return build_telemetry(
        ObservabilityConfig(enabled=True, exporter=ExporterType.STDOUT)
    )


def _unwrap(tool):
    while isinstance(tool, (GatedTool, HookedTool)):
        tool = tool.inner
    return tool


# ---- off by default -----------------------------------------------------


def test_the_default_deployment_observes_nothing(tmp_path, offline):
    app = build_app(_config(tmp_path))

    assert app.telemetry.active is False


def test_an_unobserved_deployment_keeps_its_provider_unwrapped(tmp_path, offline):
    """Identity: the provider chain must be what it was before this layer."""
    app = build_app(_config(tmp_path))

    assert not isinstance(app.provider, TracedProvider)
    assert app.provider.name == "scripted"


def test_an_unobserved_deployment_mounts_no_hook(tmp_path, offline):
    app = build_app(_config(tmp_path))

    hooked = [
        name
        for name in app.registry.names()
        if isinstance(_peel_gate(app.registry.get(name)), HookedTool)
    ]

    assert hooked == []


def test_telemetry_is_never_none(tmp_path, offline):
    """So ``entry/turn.py`` opens a scope without asking whether it may."""
    app = build_app(_config(tmp_path))

    assert isinstance(app.telemetry, Telemetry)
    _run(_exercise_scope(app))


def test_build_hooks_without_telemetry_is_what_it_always_was(tmp_path):
    assert build_hooks(_config(tmp_path)) == ()
    assert build_hooks(_config(tmp_path), Telemetry()) == ()


# ---- on --------------------------------------------------------------


def test_an_observed_deployment_wraps_its_provider(tmp_path, offline):
    app = build_app(_config(tmp_path), telemetry=_active())

    assert isinstance(app.provider, TracedProvider)
    assert app.provider.name == "scripted", "the wrapper does not rename the backend"


def test_the_engine_is_built_over_the_wrapped_provider(tmp_path, offline):
    """A wrapper the engine never sees would record nothing at all."""
    app = build_app(_config(tmp_path), telemetry=_active())

    assert app.engine._provider is app.provider


def test_the_model_name_reaches_the_span(tmp_path, offline):
    app = build_app(_config(tmp_path, model="gpt-5-test"), telemetry=_active())

    assert app.provider._model == "gpt-5-test"


def test_an_observed_deployment_mounts_exactly_one_hook(tmp_path, offline):
    app = build_app(_config(tmp_path), telemetry=_active())

    tool = _peel_gate(app.registry.get(app.registry.names()[0]))
    assert isinstance(tool, HookedTool)
    assert [type(hook) for hook in tool.hooks] == [TracingHook]


def test_the_audit_hook_is_first_and_the_tracing_hook_is_last(tmp_path):
    """Opposite ends, and neither position is negotiable."""
    hooks = build_hooks(
        _config(tmp_path, audit_log=tmp_path / "audit.jsonl"), _active()
    )

    assert [type(hook) for hook in hooks] == [AuditHook, TracingHook]


def test_an_explicit_hook_list_replaces_the_whole_chain(tmp_path, offline):
    """``hooks=()`` still means what it meant: no hooks, whatever is configured."""
    app = build_app(_config(tmp_path), hooks=(), telemetry=_active())

    hooked = [
        name
        for name in app.registry.names()
        if isinstance(_peel_gate(app.registry.get(name)), HookedTool)
    ]

    assert hooked == []


def test_the_registry_itself_is_never_wrapped(tmp_path, offline):
    """Defect R3: the engine probes it with ``isinstance`` for two Protocols."""
    from omicsclaw.engine.executor import ConcurrencyAwareExecutor, DeadlineAwareExecutor

    app = build_app(_config(tmp_path), telemetry=_active())

    assert isinstance(app.registry, ConcurrencyAwareExecutor)
    assert isinstance(app.registry, DeadlineAwareExecutor)


# ---- shutdown -----------------------------------------------------------


def test_closing_the_app_closes_the_telemetry(tmp_path, offline):
    closed: list[int] = []
    telemetry = Telemetry(on_shutdown=lambda: closed.append(1))

    app = build_app(_config(tmp_path), telemetry=telemetry)
    _run(app.aclose())

    assert closed == [1]


def test_telemetry_is_closed_even_when_something_before_it_fails(tmp_path, offline):
    """It is last in the chain, so it is the one a raise would skip."""
    closed: list[int] = []
    telemetry = Telemetry(on_shutdown=lambda: closed.append(1))
    app = build_app(_config(tmp_path), telemetry=telemetry)

    class Exploding:
        async def aclose(self) -> None:
            raise RuntimeError("mcp will not close")

    app = dataclasses.replace(app, mcp=Exploding())

    with pytest.raises(RuntimeError):
        _run(app.aclose())

    assert closed == [1]


# ---- the blocking path declares itself ----------------------------------


def test_the_blocking_exchange_really_produces_a_two_level_tree(tmp_path, offline):
    """The end-to-end check the two string assertions below cannot make.

    ``scope.py`` is covered on its own and ``turn.py`` is checked as text;
    neither proves the two are joined correctly. This drives the real
    :func:`~omicsclaw.entry.turn.run_turn` against a real
    :class:`~omicsclaw.observability.Telemetry` and reads the tree that
    comes out. What it is guarding is a **wrong number**, not a missing
    level: without ``turn_events=False`` at that call site, both model
    calls of this two-turn exchange would sit inside one span labelled
    ``agent.turn=1``.
    """
    from omicsclaw.entry.turn import run_turn

    from tests.observability._support import Echo, RecordingMeter, RecordingTracer

    tracer, meter = RecordingTracer(), RecordingMeter()
    telemetry = Telemetry(tracer=tracer, meter=meter)
    app = build_app(
        _config(tmp_path),
        tools=[Echo()],
        telemetry=telemetry,
        provider=_TwoTurnProvider(),
    )

    _run(run_turn(app, (), "hi", session_id="sess-blocking"))

    names = [span.name for span in tracer.spans]
    assert names.count("omicsclaw.interaction") == 1
    assert "omicsclaw.turn" not in names, (
        "a turn span here would be claiming a boundary nobody reported"
    )
    root = tracer.named("omicsclaw.interaction")[0]
    assert root.attributes["session.id"] == "sess-blocking"
    assert root.attributes["agent.turns"] == 2, "the turn count still arrives"
    requests = tracer.named("omicsclaw.llm_request")
    assert len(requests) == 2, "one request span per model call"
    assert all(span.chain == ["omicsclaw.llm_request", "omicsclaw.interaction"] for span in requests)
    assert all(
        span.chain == [span.name, "omicsclaw.interaction"]
        for span in tracer.spans
        if span.name != "omicsclaw.interaction"
    )
    assert all(span.ended == 1 for span in tracer.spans)


@dataclasses.dataclass
class _TwoTurnProvider:
    """Asks for one tool, then converges — so the run really has two turns."""

    calls: int = 0

    @property
    def name(self) -> str:
        return "two-turn"

    async def generate(self, messages, tools=None):
        from omicsclaw.schema import ToolCall

        self.calls += 1
        if self.calls == 1:
            return Completion(
                message=Message(
                    role=Role.ASSISTANT,
                    tool_calls=(ToolCall(id="c0", name="echo", arguments="{}"),),
                ),
                finish_reason="tool_calls",
            )
        return Completion(message=Message(role=Role.ASSISTANT, content="done"))

    def generate_stream(self, messages, tools=None):
        raise NotImplementedError

    def bind(self, **overrides):
        return self


def test_the_blocking_exchange_says_it_reports_no_turns():
    """Read as text: this test may not import what it is checking about.

    The failure it prevents is silent — one turn span containing every
    model call of the run — and the only place the flag can be set is the
    call site.
    """
    source = (
        pathlib.Path(assembly.__file__).parent / "turn.py"
    ).read_text(encoding="utf-8")

    assert source.count("telemetry.run(") == 3, "three exchange paths, three scopes"
    assert source.count("turn_events=False") == 1
    assert source.count("scope.observe(") == 3


def test_every_streaming_exchange_feeds_the_scope_its_events():
    source = (
        pathlib.Path(assembly.__file__).parent / "turn.py"
    ).read_text(encoding="utf-8")

    assert "scope.observe(event)" in source
    assert "scope.observe(EngineEvent.done(result))" in source


def _peel_gate(tool):
    return tool.inner if isinstance(tool, GatedTool) else tool


async def _exercise_scope(app) -> None:
    async with app.telemetry.run(session_id="s", prompt="p") as scope:
        assert scope is not None
