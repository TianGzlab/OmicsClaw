"""Out-of-band channels: how a running tool reaches the caller that started it.

Plan 0028 §4 Q4. The seam step 3 published is ``execute(call)`` — one
argument, and deliberately not a ``ctx``. Go's ``context.Context`` carries
*values* as well as cancellation, and the reference harness uses that half
for seven keys, of which this module reproduces two: an approval callback
handed to the tool executor (``hooks/decision.go:60``) and a progress sink
handed to sub-agent streaming (``hooks/subagent_progress.go:18``). Python
has an environment-carried equivalent that does not require widening a
published Protocol, so this module is what the Go ``ctx`` value half
becomes: :mod:`contextvars`.

**Of the five not reproduced, three are observability spans and two are a
mechanism worth naming.** ``approvedContextKey`` and
``explicitlyAllowedContextKey`` (``hooks/decision.go:74`` and ``:89``,
read at ``hooks/hook.go:87``) mark a *call* as already decided, so one
tool call asks a human **at most once** however many layers of the hook
chain want to ask. There is no equivalent here: :func:`require_approval`
asks every time it is called. Every tool in this package calls it once, so
nothing is wrong today — but a wrapping tool (a skill wrapper, an MCP
proxy, a future sub-agent tool) would prompt twice, and the layer that
would own the fix is the hook layer this package deliberately does not
have.

That this works at all rests on one property of the engine:
``engine/executor.py`` runs each call in its own :class:`asyncio.Task`,
and ``Task.__init__`` calls :func:`contextvars.copy_context`, so every
worker runs on a **copy of the context current when the turn's tools were
scheduled**. A variable set by a surface before the turn is therefore
readable inside a tool running three levels down, and the engine needs no
change at all. A property nobody wrote down is a coincidence waiting to be
refactored away, so it is written down here, and
``tests/tools/test_context.py`` asserts it through the real
``execute_tool_calls`` rather than by reading a variable back in the
coroutine that set it.

**What would break it is narrower than it looks.** Neither
:class:`asyncio.TaskGroup` nor :func:`asyncio.gather` is a threat —
both create Tasks, and a Task copies. The two that are: awaiting a call
**inline** rather than in a Task, which leaves every tool writing into
the turn's own context; and creating the Tasks with one shared
``context=``, which is the only spelling that makes several workers share
a mutable context on purpose.

**The five questions plan 0028 §4 Q4 requires answering, answered.**

1. *What is carried — a value or a reference?* **A reference.** The
   variable holds the approval *callback* and the progress *sink*, never
   an approval result. A decision that was computed before the tool ran
   cannot be about the arguments the tool actually received, and a tool
   that must block until a human clicks needs something it can await.
   :func:`require_approval` awaits the callback, so the round trip is the
   callback's own business — see :class:`ApprovalRequest`.

2. *Who sets it?* **The surface** (CLI, Desktop, Channel), once, before
   entering the agent turn — :func:`use_tool_context` or
   :func:`set_tool_context`.

3. *Who reads it?* **The concrete tool**, inside its own ``execute``.
   :class:`~omicsclaw.tools.registry.ToolRegistry` reads neither channel
   and still has no opinion about approval: it makes them exist and takes
   no part in what travels down them. A registry that *enforced* approval
   would have to know who is asking, which is precisely the knowledge
   plan 0028 trap 12 keeps out of it.

   It does publish two things, and it has to. The first is the policy in
   force for a call, resolved by
   :meth:`~omicsclaw.tools.registry.ToolRegistry.policy_for` — the
   deployment's ``register(policy=)`` outranking the author's
   ``tool.policy``, per plan 0028 §4 Q5 — and a tool asking with the
   policy *it* holds would be asking with the author's, never the
   deployment's. That made the whole of Q5 decorative in the one
   direction that matters: a deployment tightening ``AUTO`` to ``ASK``
   gated nothing, because the tool went on self-approving from its own
   ``AUTO``. So :meth:`~omicsclaw.tools.registry.ToolRegistry.execute`
   binds its resolution through :func:`use_effective_policy` and
   :func:`require_approval` reads it from there. Publishing a resolution
   is not enforcing it; the registry still neither asks nor decides.

   The second is the scheduler's :data:`TimeoutPause`, bound through
   :func:`use_timeout_pause` from what the engine handed the registry for
   this call. Same shape and same reason: the thing a tool needs is owned
   by a layer the tool may not import, so the dispatcher in the middle
   passes it down instead.

4. *What happens when nothing is set?* **Fail closed.**
   :func:`require_approval` raises :exc:`ApprovalUnavailable` when a tool
   needs consent and no channel is bound, which the registry turns into an
   ``is_error`` Observation naming the reason. The absent channel is never
   read as consent. Progress is the opposite and deliberately so: a
   missing sink is the normal case, so :func:`report_progress` is a no-op
   that reports having done nothing.

5. *Can two sessions cross?* **Only if they share an asyncio Task.**
   ``contextvars`` isolates per Task, not per coroutine call, so two
   concurrent sessions in one process — which the Channel Surface has by
   construction, Telegram and Feishu conversations interleaving on one
   event loop — are isolated **iff each top-level session runs in its own
   Task**. Two sessions binding a context inside one shared Task is a
   real defect with a plausible-looking diff: the second ``set`` wins, and
   one user's tool call is offered to the other user's approval prompt.
   Both halves have a test.

**Not a general-purpose bag with two extras bolted on.** The two named
channels are named because they are the two that need a *reference*.
:attr:`ToolContext.values` carries the flat per-turn facts the existing
tool layer injects through ``ToolSpec.context_params`` — ``session_id``,
``chat_id``, ``surface``, ``workspace``, ``thread_id`` and the rest — and
exists so plan 0028 §5's "must have a one-for-one replacement" is true
rather than aspirational. It is deliberately untyped: this layer must not
learn what a ``surface`` is.

**A human's thinking time is no longer charged to the tool's timeout.**
``engine/executor.py::_execute`` wraps ``executor.execute(call)`` in
``asyncio.timeout(config.tool_timeout)`` — sixty seconds by default —
while Q4.3 above puts the approval await *inside* the tool's own
``execute``, so the two nest the wrong way round and a user who took
longer than ``tool_timeout`` to press "approve" used to have the tool
cancelled and the model told ``tool 'X' timed out after 60s``: false
(nothing ran long, nobody answered) and actively misleading, since it
sends the model to make the tool faster. :func:`asyncio.shield` was never
the fix — the outer budget still raises at the next await point in this
task — so the fix is the engine lifting its own deadline: it offers the
call a :data:`TimeoutPause`, :func:`require_approval` enters it around
the round trip, and the seconds that were left are restored on the way
out. The engine's half is ``DeadlineAwareExecutor``, and the registry is
what carries it here.

A pause stops the clock; it does not bound the wait. **A surface that
asks a person still owns the deadline on its own prompt** — an IM bot
posting an approval card runs its own timer and answers "nobody
responded" itself, so the refusal the model reads is the true one. What
changed is that missing that deadline is now the surface's own report
rather than a fabricated tool timeout.

It owns one more thing, and it is the shape that hangs. **Whatever
answers an :class:`ApprovalRequest` must be able to make progress while
the consumer of ``execute_tool_calls`` is suspended between events** — a
separate Task, or an ``await`` on the request queue from inside the
``async for`` body. A consumer that only *polls* for requests between
events never sees one, because the request is issued after it has gone
back to waiting for the next event. Before the pause, such a consumer was
released by ``tool_timeout`` — with the false sentence above — so this is
a hazard the pause exposed rather than one it introduced. The reference
harness has the same hazard in its own shape and spends eight lines on it
at ``stream.go:51-58``.

**Leaf-adjacent.** ``omicsclaw.tools.base`` and the standard library.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from .base import ApprovalMode, RiskLevel, ToolPolicy


class ApprovalDenied(RuntimeError):
    """Consent for this execution was not given, so the tool did not run.

    Raised out of :func:`require_approval`, which means the registry turns
    it into an ``is_error`` Observation and the model is told plainly that
    it was refused — the alternative, a silent no-op returning "done", is
    the one outcome that teaches a model to keep trying.
    """


class ApprovalUnavailable(ApprovalDenied):
    """A tool needed consent and there was nobody to ask. **Fail closed.**

    A subclass rather than a sibling because the two are the same answer
    to the tool: not permitted. Separate at all so an operator reading a
    log can tell "the human said no" from "this deployment forgot to bind
    an approval channel", which are the same refusal and completely
    different bugs.
    """


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """What the channel is asked to rule on.

    Carries the **raw argument payload**, not a parsed dict, for the
    reason :attr:`~omicsclaw.schema.ToolCall.arguments` is raw: an
    approval prompt showing re-encoded arguments is showing something
    other than what will run.
    """

    tool_name: str
    arguments: str = "{}"
    reason: str = ""
    """Why this tool is asking, in the tool's own words. Optional, and
    worth writing: "delete 412 files under /data/run-7" is a decision a
    human can make, where the tool's name alone is not."""
    risk_level: RiskLevel = RiskLevel.HIGH
    approval_mode: ApprovalMode = ApprovalMode.ASK


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """The channel's answer."""

    approved: bool
    reason: str = ""
    """Shown to the model when the answer is no, so a refusal is
    actionable rather than mysterious."""


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """A tool saying it is still working, and on what."""

    tool_name: str = ""
    message: str = ""
    fraction: float | None = None
    """Completed share in ``[0, 1]`` where the tool can compute one, and
    ``None`` where it cannot. Not clamped or invented here — a fabricated
    percentage is worse than an absent one."""


ApprovalChannel = Callable[[ApprovalRequest], Any]
"""What a surface binds so tools can ask permission.

Returns an :class:`ApprovalDecision` or a plain ``bool``, either directly
or as an awaitable. Async is the expected shape — waiting for a human is
the whole point — but a synchronous channel is accepted so a test double
is one ``lambda``.
"""

ProgressSink = Callable[[ProgressUpdate], Any]
"""What a surface binds so tools can report progress. May be async."""

_EMPTY_VALUES: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Everything a tool can learn about the turn it is running inside.

    One object rather than three variables so that binding is atomic:
    three separate ``set`` calls have a window in which a tool sees this
    session's approval channel beside the last session's ``session_id``.
    """

    approval: ApprovalChannel | None = None
    progress: ProgressSink | None = None
    values: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_VALUES)
    """Flat per-turn facts, read with :func:`context_value`.

    The replacement for ``ToolSpec.context_params`` plus
    ``build_executor_kwargs``: that pair let a tool *declare* the runtime
    keys it wanted and receive them as keyword arguments. Declaration is
    dropped on purpose — it bought a second place to edit when a tool
    started needing a new key, and forgetting it failed silently, by
    passing nothing. A tool that reads a key it was not given gets its own
    default here, at the line that needed the value.

    **Always a read-only view over a private copy**, whichever way the
    context was bound — see :meth:`__post_init__`.
    """

    def __post_init__(self) -> None:
        """Copy :attr:`values` and seal it, here rather than at one binder.

        :func:`use_tool_context` used to be the only path that wrapped the
        bag, which left :func:`set_tool_context` handing out a live dict:
        one tool could edit what its siblings read, and the caller's own
        dict with it. That is the worse of the two paths to leave open,
        because ``set_tool_context`` is the form recommended to a surface
        that owns a whole Task and therefore holds its binding longest.

        Doing it in the constructor makes the property true of *every*
        :class:`ToolContext` rather than of the ones built by the blessed
        helper. The copy is not redundant with the proxy: a
        :class:`~types.MappingProxyType` over a dict the caller still
        holds is read-only only from this side.
        """
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


_NOTHING = ToolContext()
"""The context of a tool running outside any surface — a test, a script.

Not ``None``: :func:`current_context` always answering with a
:class:`ToolContext` means a tool reads ``ctx.progress`` without first
proving a context exists, and "no channel bound" is expressed once, here,
rather than at every call site.
"""

_CONTEXT: ContextVar[ToolContext] = ContextVar(
    "omicsclaw.tools.context", default=_NOTHING
)


def current_context() -> ToolContext:
    """The context in force for this Task, or an empty one."""
    return _CONTEXT.get()


def set_tool_context(context: ToolContext) -> Token[ToolContext]:
    """Bind ``context`` for this Task and everything it starts.

    The raw form, for a surface that owns the Task outright — a
    per-conversation worker that binds once at the top and never unbinds.
    :func:`use_tool_context` is the scoped form and is what a request
    handler wants.

    Binds ``context`` as given; ``context.values`` was already copied and
    sealed when the object was constructed, so this path and the scoped
    one offer a tool exactly the same read-only bag.
    """
    return _CONTEXT.set(context)


def reset_tool_context(token: Token[ToolContext]) -> None:
    """Undo the :func:`set_tool_context` that produced ``token``."""
    _CONTEXT.reset(token)


@contextmanager
def use_tool_context(
    *,
    approval: ApprovalChannel | None = None,
    progress: ProgressSink | None = None,
    values: Mapping[str, Any] | None = None,
) -> Iterator[ToolContext]:
    """Bind a context for the duration of a block, then restore it.

    **Replaces rather than merges, and that is a safety property.**
    Inheriting whatever was already bound is how one session's approval
    channel ends up answering another session's question: the omitted
    argument reads as "I did not need to set that", never as "keep the
    previous one". A nested scope that genuinely wants an outer channel
    passes it explicitly::

        outer = current_context()
        with use_tool_context(approval=outer.approval, values=extra):
            ...

    Restores on the way out however the block ends, so an exception
    escaping a turn cannot leave a stale channel bound to a pooled Task.
    """
    context = ToolContext(
        approval=approval,
        progress=progress,
        values=values if values is not None else _EMPTY_VALUES,
    )
    token = _CONTEXT.set(context)
    try:
        yield context
    finally:
        _CONTEXT.reset(token)


_EFFECTIVE_POLICY: ContextVar[ToolPolicy | None] = ContextVar(
    "omicsclaw.tools.effective_policy", default=None
)
"""The policy the dispatching registry resolved for the running call.

A second variable rather than a field on :class:`ToolContext` because the
two have different owners and different lifetimes: a surface binds a
context once per turn, while this is bound and unbound around **each
individual call**, by whatever dispatched it. Folding it in would mean
the registry rebuilding a surface's context object per call, which is
both a wider blast radius and a way to drop a channel by forgetting a
field.
"""


def effective_policy() -> ToolPolicy | None:
    """The policy in force for the call running now, or ``None``.

    ``None`` means nothing resolved one — a tool invoked directly, from a
    script or a test, with no registry in the path. That is not "no
    policy applies": :func:`require_approval` falls back to the tool's own
    declaration and then to ``ToolPolicy()``, which asks.
    """
    return _EFFECTIVE_POLICY.get()


@contextmanager
def use_effective_policy(
    policy: ToolPolicy | None,
) -> Iterator[ToolPolicy | None]:
    """Publish ``policy`` as authoritative for the block, then restore.

    Bound by a dispatcher around one call —
    :meth:`~omicsclaw.tools.registry.ToolRegistry.execute` does it with
    what :meth:`~omicsclaw.tools.registry.ToolRegistry.policy_for`
    resolved — and read by :func:`require_approval`. This is the wire that
    makes ``register(policy=)`` mean something at execution time rather
    than only in an accessor nobody calls.

    Restores on the way out however the block ends, so one call's
    resolution cannot be read by the next thing to run on this Task.
    """
    token = _EFFECTIVE_POLICY.set(policy)
    try:
        yield policy
    finally:
        _EFFECTIVE_POLICY.reset(token)


TimeoutPause: TypeAlias = Callable[[], AbstractContextManager[None]]
"""A scheduler's way of not charging a block to the per-tool timeout.

Produced by whatever imposed the timeout — ``engine/executor.py`` — and
consumed by :func:`pause_tool_timeout`. Typed structurally rather than
imported, because this layer may not reach into
:mod:`omicsclaw.engine`; all it needs to know is that calling it yields a
context manager.
"""


_TIMEOUT_PAUSE: ContextVar[TimeoutPause | None] = ContextVar(
    "omicsclaw.tools.timeout_pause", default=None
)
"""The pause published for the call running now, or ``None``.

A third variable rather than a field on :class:`ToolContext`, for
:data:`_EFFECTIVE_POLICY`'s reason: a surface binds a context once per
turn, while this belongs to **one call** and is bound and unbound around
it by whatever dispatched it.
"""


@contextmanager
def use_timeout_pause(pause: TimeoutPause | None) -> Iterator[None]:
    """Publish ``pause`` for the block, then restore what was there.

    Bound by a dispatcher around one call, from the Task that call runs
    on, and read by :func:`pause_tool_timeout`. ``None`` publishes nothing,
    which is the same as never having called this.
    """
    token = _TIMEOUT_PAUSE.set(pause)
    try:
        yield
    finally:
        _TIMEOUT_PAUSE.reset(token)


@contextmanager
def pause_tool_timeout() -> Iterator[bool]:
    """Keep the block's wall-clock time out of the engine's per-tool timeout.

    For a wait that is not the tool's own work — a human's approval
    decision above all. Yields whether a pause was actually in force:
    ``False`` when no scheduler published one, in which case the block is
    timed exactly as the rest of the call.

    A pause only stops the clock. It does not bound the wait, so a caller
    who may wait on a person is the one that has to decide how long it
    will wait for them.
    """
    pause = _TIMEOUT_PAUSE.get()
    if pause is None:
        yield False
        return
    with pause():
        yield True


def context_value(key: str, default: Any = None) -> Any:
    """One flat per-turn fact, or ``default``.

    The read half of :attr:`ToolContext.values`. ``default`` is the tool's
    own answer to "what if the surface did not provide this", which is the
    question ``build_executor_kwargs`` answered by omitting the keyword
    argument and letting the executor's signature default apply.
    """
    return current_context().values.get(key, default)


async def report_progress(
    message: str,
    *,
    tool_name: str = "",
    fraction: float | None = None,
) -> bool:
    """Tell whoever is watching that this tool is still working.

    Returns whether the update was **delivered**, so a long-running tool
    can decide once whether computing progress is worth the arithmetic
    rather than formatting strings into nothing. ``False`` covers both
    ways nobody heard it: no sink bound, and a sink that raised.

    **Never fails closed, and that now includes a sink that is broken
    rather than absent.** An unbound progress sink is the ordinary case —
    a script, a test, a background turn with no audience — and a tool that
    refused to run without one would be unusable outside a surface. A
    *failing* sink is the same situation arriving later: the websocket the
    Desktop Surface was streaming over closed, the Telegram edit hit a
    rate limit. Letting that escape turned a finished tool's work into
    ``tool 'X' raised RuntimeError: the websocket closed`` — a Surface
    transport fault wearing a tool failure's clothes, delivered to a model
    that will try to fix the tool. Progress is not a permission, and an
    audience that cannot speak must not be able to fail the speaker.

    ``except Exception``, never ``BaseException``:
    :exc:`asyncio.CancelledError` and :exc:`KeyboardInterrupt` are not a
    sink's opinion about progress and pass straight through — the same
    discipline :meth:`~omicsclaw.tools.registry.ToolRegistry.execute`
    keeps.

    The sink's exception is **not** re-reported anywhere, because there is
    nowhere in this layer to report it that is not the model's
    conversation. A surface that wants to know its own sink is broken
    wraps it in its own logging, where the traceback is of use to an
    operator rather than to a language model.
    """
    sink = current_context().progress
    if sink is None:
        return False
    try:
        outcome = sink(
            ProgressUpdate(tool_name=tool_name, message=message, fraction=fraction)
        )
        if inspect.isawaitable(outcome):
            await outcome
    except Exception:
        return False
    return True


async def require_approval(
    tool_name: str,
    arguments: str = "{}",
    *,
    policy: ToolPolicy | None = None,
    reason: str = "",
) -> ApprovalDecision:
    """Ask for consent, and refuse to proceed without it.

    Called by a tool from inside its own ``execute``, before the
    irreversible part. Returns the decision when consent is given and
    raises :exc:`ApprovalDenied` otherwise, so a tool that forgets to
    check the return value still does not run — the failure mode of a
    boolean return is a tool that asks politely and then ignores the
    answer.

    **The authoritative policy is the one the dispatching registry
    resolved, not the one the tool asks with.** ``policy`` is the caller's
    own :class:`~omicsclaw.tools.base.ToolPolicy` — the *author's* view —
    and it is a **fallback**, consulted only when nothing published a
    resolution. Full order, most authoritative first:

    1. :func:`effective_policy`, bound by
       :meth:`~omicsclaw.tools.registry.ToolRegistry.execute` from
       :meth:`~omicsclaw.tools.registry.ToolRegistry.policy_for`, which is
       where a deployment's ``register(policy=)`` outranks the author's
       ``tool.policy`` (plan 0028 §4 Q5);
    2. the ``policy`` argument, for a tool invoked with no registry in the
       path — directly, from a script or a test;
    3. ``ToolPolicy()``, whose ``approval_mode`` is ``ASK``, so the
       forgetful call asks rather than proceeds.

    The order is this way round because the reverse is not a preference
    but a hole: a deployment tightening a tool from ``AUTO`` to ``ASK``
    through ``register(policy=)`` would be ignored by a tool that went on
    self-approving from the ``AUTO`` its author wrote, and the tightening
    would show up in ``policy_for`` — where an operator would read it and
    believe it — while changing nothing at execution time. Note that
    step 1 already *contains* step 2's answer whenever a deployment named
    no policy, because that is what ``policy_for`` resolves to.

    :attr:`~omicsclaw.tools.base.ApprovalMode.DENY_UNLESS_TRUSTED` is put
    to the channel exactly like ``ASK``. Whether a caller is trusted is
    knowledge the channel's owner has and this layer does not; with no
    channel bound it is the same refusal, which is the right answer for
    the stricter of the two modes.

    **The absence of a channel is not consent.** That is the whole of
    plan 0028 §4 Q4's fourth question, and it is decided here rather than
    per tool because a security default chosen forty times is a security
    default chosen inconsistently.

    **The human's thinking time is not charged to the tool's timeout.**
    The round trip to the channel runs inside :func:`pause_tool_timeout`,
    so a person who takes longer than ``EngineConfig.tool_timeout`` to
    decide no longer has the tool cancelled and reported to the model as
    having run long. The pause does not bound the wait — a channel that
    never answers blocks the call — so a surface that posts an approval
    card owns the deadline on its own prompt and answers "nobody
    responded" itself, which is the refusal the model can act on.
    """
    effective = _resolved_policy(policy)
    if effective.approval_mode is ApprovalMode.AUTO:
        return ApprovalDecision(approved=True, reason="policy: auto")

    channel = current_context().approval
    if channel is None:
        raise ApprovalUnavailable(
            f"{tool_name} requires approval "
            f"(approval_mode={effective.approval_mode.value}, "
            f"risk={effective.risk_level.value}) and no approval channel "
            "is bound to this session; refusing rather than assuming consent"
        )

    with pause_tool_timeout():
        outcome = channel(
            ApprovalRequest(
                tool_name=tool_name,
                arguments=arguments,
                reason=reason,
                risk_level=effective.risk_level,
                approval_mode=effective.approval_mode,
            )
        )
        if inspect.isawaitable(outcome):
            outcome = await outcome

    decision = _as_decision(outcome)
    if not decision.approved:
        detail = f": {decision.reason}" if decision.reason else ""
        raise ApprovalDenied(f"{tool_name} was not approved{detail}")
    return decision


_NO_POLICY = ToolPolicy()
"""What a tool that passed no policy is treated as having declared."""


def _resolved_policy(declared: ToolPolicy | None) -> ToolPolicy:
    """The three-step order documented on :func:`require_approval`.

    One function rather than an expression inline so that the precedence
    has a name, a docstring and a place for a test to point at: it is a
    security rule, and a security rule spelled as a conditional expression
    is a security rule nobody reviews.
    """
    published = _EFFECTIVE_POLICY.get()
    if published is not None:
        return published
    return declared if declared is not None else _NO_POLICY


def _as_decision(outcome: Any) -> ApprovalDecision:
    """Read a channel's answer, and read silence as no.

    ``None`` is the interesting case: a callback that opened a dialog and
    forgot to return its result yields ``None``, and the only safe reading
    of "I did not answer" is that nothing was approved. Anything else
    unrecognised raises rather than being guessed at — the tool still does
    not run, and the deployment hears about its bug instead of the model
    hearing a refusal it cannot act on.
    """
    if isinstance(outcome, ApprovalDecision):
        return outcome
    if outcome is None:
        return ApprovalDecision(
            approved=False, reason="the approval channel returned no decision"
        )
    if isinstance(outcome, bool):
        return ApprovalDecision(approved=outcome)
    raise TypeError(
        "an approval channel must return ApprovalDecision, bool or None; "
        f"got {type(outcome).__name__}"
    )


__all__ = [
    "ApprovalChannel",
    "ApprovalDecision",
    "ApprovalDenied",
    "ApprovalRequest",
    "ApprovalUnavailable",
    "ProgressSink",
    "ProgressUpdate",
    "TimeoutPause",
    "ToolContext",
    "context_value",
    "current_context",
    "effective_policy",
    "pause_tool_timeout",
    "report_progress",
    "require_approval",
    "reset_tool_context",
    "set_tool_context",
    "use_effective_policy",
    "use_timeout_pause",
    "use_tool_context",
]
