"""``omicsclaw.entry`` — where a user reaches the agent.

Plan 0031, step 6 of the staged rebuild. The five layers before it are
each complete and **none of them can be reached**: ``schema`` knows what
a message looks like but not where one comes from, ``engine`` knows how
to run a conversation to convergence but not where the conversation was
stored, ``context`` knows how to assemble a prompt but not where
``OMICSCLAW.md`` lives. This package is the answer to all five at once::

    from omicsclaw.entry import attach_sessions, open_app, resolve_app_config

    config = resolve_app_config(argv, env)     # both are required, plan 0037
    app = attach_sessions(await open_app(config))
    handle = await app.sessions.submit("session-1", "分析这份 Visium 数据")
    async for event in handle.observe():
        ...
    await app.aclose()

**The top layer, not a leaf.** Every package below declares what it may
import; this one is the single place allowed to import all of them. Its
layering test is therefore inverted — ``tests/entry/
test_entry_is_the_top_layer.py`` asserts that nothing in the five layers
imports ``omicsclaw.entry``, and that driving this package loads none of
the packages this rebuild replaces (``omicsclaw.runtime``,
``omicsclaw.control``, ``omicsclaw.providers``, ``omicsclaw.skill``,
``omicsclaw.surfaces``) and no optional dependency
(``fastapi``, ``textual``, either vendor SDK). Behaviourally, in a
subprocess, because a static check catches spellings and only a probe
catches facts — plan 0028 lost 286 green tests to one lazy
``importlib``.

**The three surfaces import this package; it does not import them.**
``omicsclaw/surfaces/`` is this step's *input*, not its output: the
owner's ruling of 2026-09-19 is that the channel, CLI and desktop
implementations are reused rather than rebuilt. They depend on
:class:`~omicsclaw.entry.ingress.InboundMessage`, the turn event stream
and the renderer, and on nothing deeper.

**What a surface may depend on.** Plan 0031 §7 holds the three surfaces
to three things — :class:`~omicsclaw.entry.events.TurnEvent`, the
renderer, and the ingress types — so all three are exported here
alongside the deployment and the registry. Nothing below
:mod:`omicsclaw.entry` should appear in a surface's imports; if it does,
the seam moved.

**The surface subpackages are ports, not rewrites.** All three have
landed — :mod:`omicsclaw.entry.channel`, :mod:`omicsclaw.entry.cli` and
:mod:`omicsclaw.entry.desktop` — and between them they are what has
exercised the contracts above; a contract only a reference consumer has
exercised has not been exercised. None of them is imported here: a
surface costs an optional dependency and a deployment runs one.

:func:`~omicsclaw.entry.build_app` still leaves
:attr:`~omicsclaw.entry.assembly.AgentApp.sessions` as ``None`` — the
registry and the app name each other, and
:func:`~omicsclaw.entry.session.attach_sessions` is the one line that
ties that knot.
"""

from .approval import ApprovalBroker
from .assembly import AgentApp, build_app, build_skill_index, open_app
from .config import (
    AppConfig,
    AppConfigError,
    SandboxMode,
    SkillsIndex,
    fields_set_by_argv,
    resolve_app_config,
)
from .display import inert_prose
from .events import Terminal, TurnEvent, TurnEventType
from .ingress import Acceptance, DeliveryResult, InboundMessage, SenderPolicy
from .memory import MemoryBinding, open_memory, prepare_memory, session_store
from .render import TextRenderer, to_wire
from .planning import build_injector, build_plan_book
from .sandbox import SandboxBinding, open_sandbox
from .session import (
    InMemorySessionStore,
    QueueFull,
    RegistryClosed,
    Session,
    SessionRegistry,
    SessionStore,
    SubmissionRefused,
    attach_sessions,
)
from .stream import (
    EventObserverDetached,
    ObserverCapacityError,
    TurnObservation,
    TurnStream,
)
from .subagent import ChildRunner, build_subagent_registry
from .turn import (
    TurnHandle,
    TurnOutcome,
    TurnRunner,
    at_least,
    compose,
    prepare,
    run_turn,
    stream_turn,
)

__all__ = [
    "Acceptance",
    "AgentApp",
    "AppConfig",
    "AppConfigError",
    "ApprovalBroker",
    "ChildRunner",
    "DeliveryResult",
    "EventObserverDetached",
    "InMemorySessionStore",
    "InboundMessage",
    "MemoryBinding",
    "ObserverCapacityError",
    "QueueFull",
    "RegistryClosed",
    "SandboxBinding",
    "SandboxMode",
    "SenderPolicy",
    "Session",
    "SessionRegistry",
    "SessionStore",
    "SkillsIndex",
    "SubmissionRefused",
    "Terminal",
    "TextRenderer",
    "TurnEvent",
    "TurnEventType",
    "TurnHandle",
    "TurnObservation",
    "TurnOutcome",
    "TurnRunner",
    "TurnStream",
    "at_least",
    "attach_sessions",
    "build_app",
    "build_injector",
    "build_plan_book",
    "build_skill_index",
    "build_subagent_registry",
    "compose",
    "fields_set_by_argv",
    "inert_prose",
    "open_app",
    "open_memory",
    "open_sandbox",
    "prepare",
    "prepare_memory",
    "resolve_app_config",
    "run_turn",
    "session_store",
    "stream_turn",
    "to_wire",
]
