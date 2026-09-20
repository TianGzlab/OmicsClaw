"""The hub: registration, exposure, dispatch — and nothing else.

Plan 0028 §2. Three jobs in one place, so the loop can use tools while
knowing none of them:

    registry.register(tool)                 # mount
    defs = registry.available_tools()       # expose  → provider
    result = await registry.execute(call)   # dispatch → Observation

:class:`ToolRegistry` satisfies
:class:`omicsclaw.engine.executor.ToolExecutor` **structurally** — same
two methods, same signatures — without importing :mod:`omicsclaw.engine`.
That is the whole point of the seam being a Protocol: the dependency runs
one way, from the engine's test suite to here, and never back.

Two further methods satisfy that layer's two **optional** seams the same
way. :meth:`ToolRegistry.is_concurrency_safe` answers
``ConcurrencyAwareExecutor``, which is what finally gives
:attr:`~omicsclaw.tools.base.ToolPolicy.concurrency_safe` a consumer: a
tool that declares itself unsafe is scheduled alone instead of beside a
sibling writing the same file. :meth:`ToolRegistry.use_timeout_pause`
answers ``DeadlineAwareExecutor`` and carries the engine's per-call
timeout pause down to :func:`~omicsclaw.tools.context.require_approval`,
so a human's thinking time stops being reported as a tool running long.
Both report or relay; neither schedules and neither decides.

**What is absent is the design.** There is no ``request``, no
``surface``, no ``stage`` anywhere on this class. Deciding *which* tools
a particular caller may see is the assembly layer's business (plan 0028
§5); a registry that knew about requests would be the thing this rebuild
is walking away from. What is offered instead is the full set, in a
stable order, plus :meth:`ToolRegistry.policy_for` so a filter can be
written elsewhere.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.tools.base``,
``omicsclaw.tools.context``, and the standard library.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager

from omicsclaw.schema import ToolCall, ToolDefinition, ToolResult

from .base import Tool, ToolPolicy
from .context import TimeoutPause, use_effective_policy
from .context import use_timeout_pause as publish_timeout_pause

_DECLARED_NOTHING = ToolPolicy()
"""The policy of a tool nobody wrote a policy for. See :class:`ToolPolicy`."""


class ToolRegistrationError(ValueError):
    """:meth:`ToolRegistry.register` refused a tool.

    A ``ValueError`` because every way of reaching it is a programming or
    deployment mistake caught at mount time, never a model's doing — the
    model's mistakes come back as ``is_error`` Observations and never as
    exceptions. One base class so a caller mounting a batch of tools can
    catch the whole category in one clause.
    """


class ToolAlreadyRegistered(ToolRegistrationError):
    """A second tool claimed a name that is already taken.

    **The tool already mounted stays mounted.** The reference harness
    makes the same choice, and the reason is that the alternative is
    silent: last-writer-wins turns an import-order change into a
    different tool answering the same name, with nothing to notice it.
    Overwriting is available, but it has to be said out loud —
    :meth:`ToolRegistry.replace`.
    """


class ToolNameMismatch(ToolRegistrationError):
    """``tool.name`` and ``tool.definition().name`` disagree.

    Two independent sources for one identity, which the reference harness
    leaves unchecked. Left alone it fails in the least debuggable way
    available: the registry is keyed on one name, the model is shown the
    other, every call routes to nothing, and the tool merely appears not
    to work. Checked here, at mount, where the two values are both in
    hand.
    """


class ToolRegistry:
    """An ordered set of tools, dispatched by name.

    **Order is registration order, and that is a guarantee, not an
    accident of implementation.** The reference harness iterates a Go map
    and documents the resulting order as unspecified; Go randomizes map
    iteration deliberately, so copying the behaviour would copy a defect.
    The cost is not aesthetic. Tool definitions sit between the system
    prompt and the conversation, inside the region every vendor's
    prompt-prefix cache keys on, and a cache hit is charged around a
    tenth of a miss. A list that reorders itself each turn moves the
    cache breakpoint before the tool segment and re-bills everything
    after it. This repository already depends on that: the OpenAI
    adapter's ``apply_cache_breakpoints`` writes Anthropic's explicit
    breakpoint onto ``tools[-1]`` and its docstring claims the position is
    "deterministic every turn" — true only while this method is.

    Python's dict preserves insertion order for free, but free is not the
    same as guaranteed, so it is written down here, tested by name, and
    checked by mutation.

    **Not thread-safe, on purpose.** See :meth:`register`.
    """

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        self._policies: dict[str, ToolPolicy] = {}
        for tool in tools:
            self.register(tool)

    # ---- registration ---------------------------------------------------

    def register(self, tool: Tool, policy: ToolPolicy | None = None) -> None:
        """Mount ``tool`` at the end of the order.

        Raises :class:`ToolNameMismatch` if the tool disagrees with itself
        about its name, and :class:`ToolAlreadyRegistered` if the name is
        taken — in which case **nothing changes**, neither the incumbent
        tool nor its policy nor the order.

        ``policy`` is the *deployment's* view of this tool and outranks
        the tool's own ``policy`` attribute, which is the *author's*.
        Those are different claims — "what this code can do" versus "what
        we are willing to let it do here" — which is why both exist; see
        :meth:`policy_for` for the full resolution order.

        **No lock, and that is a finding rather than an omission.** The
        reference harness guards its map with a ``sync.RWMutex`` for one
        named case: a background goroutine injecting MCP tools while the
        engine reads. That case was looked for here and does not exist.
        ``omicsclaw.mcp`` connects its servers on the event loop and
        hands their tools over *before* the registry is built; the one
        genuinely non-loop
        thread in the process — the Feishu websocket reader — marshals
        back with :func:`asyncio.run_coroutine_threadsafe` rather than
        touching runtime state itself. A mutex here would make every read
        pay for a race with no producer.

        What is done instead is cheap and unconditional:
        :meth:`available_tools` snapshots before it iterates, so even a
        registration that did arrive mid-read cannot raise
        ``dictionary changed size during iteration``. If a cross-thread
        producer ever appears, this repository's own idiom for it is
        ``omicsclaw/skill/registry.py`` — a publication lock plus an
        atomic swap of an immutable snapshot, readers still lock-free —
        not a mutex on the read path.
        """
        name = self._verified_name(tool)
        if name in self._tools:
            raise ToolAlreadyRegistered(
                f"a tool named {name!r} is already registered; "
                "use replace() to mount this one over it"
            )
        self._tools[name] = tool
        self._policies[name] = self._resolved_policy(tool, policy)

    def replace(self, tool: Tool, policy: ToolPolicy | None = None) -> None:
        """Mount ``tool`` over whatever holds its name, **keeping its place**.

        The explicit form of the overwrite :meth:`register` refuses. It
        exists so that "I mean to shadow that" is a different keystroke
        from "I did not notice that".

        Position is preserved rather than moved to the end, which is the
        second reason this is not just ``unregister`` plus ``register``:
        swapping an implementation must not churn the tool order and
        invalidate the prompt prefix it sits in. ``unregister`` followed
        by ``register`` *does* move the tool to the end, and that
        difference is the choice being offered.

        Raises :exc:`KeyError` when nothing holds the name, symmetrically
        with :meth:`unregister` and for the same reason. Both sentences
        this method's contract is written in — "over whatever holds its
        name" and "keeping its place" — are false of an absent name: there
        is nothing to mount over and no place to keep. Registering it
        silently would mean that a typo in the name, or a teardown that
        already ran, turns "shadow the tool I mean" into "add a tool
        nobody reviewed", at the end of the order rather than in the
        position the caller believed they were preserving. ``register``
        is the call that means "mount something new", and it is one word
        away.
        """
        name = self._verified_name(tool)
        if name not in self._tools:
            raise KeyError(
                f"no tool named {name!r} is registered, so there is nothing "
                "to replace; use register() to mount a new tool"
            )
        self._tools[name] = tool
        self._policies[name] = self._resolved_policy(tool, policy)

    def unregister(self, name: str) -> None:
        """Unmount the tool called ``name``.

        Raises :exc:`KeyError` when there is nothing to unmount, because
        the two reasons to call this — tearing down an MCP server's tools,
        undoing a test fixture — both want to hear that the thing they
        meant to remove was not there.
        """
        if name not in self._tools:
            raise KeyError(f"no tool named {name!r} is registered")
        del self._tools[name]
        del self._policies[name]

    # ---- inspection -----------------------------------------------------

    def get(self, name: str) -> Tool | None:
        """The tool mounted under ``name``, or ``None``."""
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        """Registered names, in registration order."""
        return tuple(self._tools)

    def policy_for(self, name: str) -> ToolPolicy:
        """The local execution policy in force for ``name``.

        Resolution, most specific first:

        =================  ==================  ======================
        ``tool.policy``    ``register(policy)``  result
        =================  ==================  ======================
        set                set                 the registered one
        set                unset               ``tool.policy``
        unset              set                 the registered one
        unset              unset               ``ToolPolicy()``
        =================  ==================  ======================

        A deployment outranks an author because it is the one accepting
        the consequences. An unknown name — and a ``policy`` attribute
        that is not a :class:`ToolPolicy` — both resolve to
        ``ToolPolicy()``, whose defaults grant nothing; guessing
        generously about a tool nobody can find is the one answer with a
        blast radius.
        """
        return self._policies.get(name, _DECLARED_NOTHING)

    def is_concurrency_safe(self, name: str) -> bool:
        """Whether ``name`` may run beside other tools in one turn.

        Read by the engine's scheduler, which runs a ``False`` answer as a
        barrier — alone, with nothing else of that turn's in flight. The
        answer comes from :meth:`policy_for`, so the deployment's
        ``register(policy=)`` decides it and an unregistered name answers
        ``False`` along with every other ``ToolPolicy()`` default.

        This is the whole of the registry's part in it: it reports what a
        policy says and schedules nothing.
        """
        return self.policy_for(name).concurrency_safe

    def available_tools(self) -> tuple[ToolDefinition, ...]:
        """Every registered tool's definition, **in registration order**.

        Re-read by the loop every turn rather than cached, because tools
        arrive while a run is in flight; and byte-identical between turns
        while nothing is registered, because that is what the prefix cache
        is paying for. See the class docstring for why the order is a
        guarantee.

        Only :class:`~omicsclaw.schema.ToolDefinition` ever leaves here.
        :class:`~omicsclaw.tools.base.ToolPolicy` has no route into this
        return type, which is how local execution policy is kept out of
        prompts structurally instead of by remembering to.
        """
        return tuple(tool.definition() for tool in tuple(self._tools.values()))

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # ---- dispatch -------------------------------------------------------

    def use_timeout_pause(
        self, pause: TimeoutPause
    ) -> AbstractContextManager[None]:
        """Carry the scheduler's per-call timeout pause down to the tools.

        Entered by the engine around one call and closed after it, so a
        tool reaching :func:`~omicsclaw.tools.context.pause_tool_timeout`
        — which is what :func:`~omicsclaw.tools.context.require_approval`
        does around the human round trip — can stop the clock the engine
        started.

        The registry is a conduit and nothing more: it neither creates the
        pause nor uses it, exactly as it neither asks for approval nor
        decides one.
        """
        return publish_timeout_pause(pause)

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run one call and return its Observation. **Never raises.**

        Every ordinary failure — no such tool, a tool that raised — comes
        back as a :class:`~omicsclaw.schema.ToolResult` with
        ``is_error=True``, because the model is the one asked to fix it: a
        misspelled tool name or a bad argument is a correctable mistake,
        and an exception here would end a run that was otherwise going
        fine. The error text names the class and carries the message for
        the same reason — ``ValueError: threshold must be positive`` says
        what to change.

        ``except Exception``, and **never** ``BaseException``. The
        reference harness spells this ``recover()``, which catches every
        panic; translating it literally would swallow
        :exc:`asyncio.CancelledError` and turn a cancelled turn into a
        fake Observation, and would swallow :exc:`KeyboardInterrupt` and
        make Ctrl-C stop working. Those are not tool failures and they
        pass straight through.

        Timing is recorded in :attr:`~omicsclaw.schema.ToolResult.metadata`
        as ``duration_s``, and only when a tool actually ran: an
        unrecognised name has no duration to report, and a zero would read
        as one.

        Approval, sandboxing and path safety are not enforced here. This
        method routes and reports; a tool that needs permission asks for
        it inside its own ``execute``, where the thing being permitted is
        known. Lifecycle hooks, when they arrive, wrap this call from
        *outside* the ``try`` below — a hook that raised inside it would
        be reported to the model as the tool's own failure.

        **What is published, and why it is not the same as enforcing.**
        The call runs inside
        :func:`~omicsclaw.tools.context.use_effective_policy`, carrying
        this registry's :meth:`policy_for` answer for the name being
        dispatched. That is the only place the resolution of "author's
        policy versus deployment's policy" can be made to reach execution
        time: a tool asks with the policy *it* holds, which is the
        author's, so without this hop a deployment tightening ``AUTO`` to
        ``ASK`` through ``register(policy=)`` changed ``policy_for`` and
        nothing else — a control that reads as enforced and is not.
        Publishing it leaves every decision where it was: the registry
        still never asks anyone and never refuses anything, and it is
        :func:`~omicsclaw.tools.context.require_approval` inside the tool
        that consults a channel the registry cannot see.

        The binding is scoped to this one call and unwound on every exit
        path, so nothing else running on this Task can read a resolution
        that was not meant for it.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            return _failed(call, self._unknown_tool_message(call.name))

        started = time.perf_counter()
        try:
            with use_effective_policy(self.policy_for(call.name)):
                output = await tool.execute(call.arguments)
        except Exception as exc:
            return _failed(
                call,
                f"tool {call.name!r} raised {type(exc).__name__}: {exc}",
                _timing(time.perf_counter() - started),
            )
        return ToolResult(
            tool_call_id=call.id,
            name=call.name,
            output=output,
            metadata=_timing(time.perf_counter() - started),
        )

    # ---- internals ------------------------------------------------------

    def _unknown_tool_message(self, name: str) -> str:
        """What the model is told when it calls something that is not here.

        The registered names are listed. The reference harness names only
        the missing tool, but the Observation exists so the model can
        correct itself, and "here is what there is" is the correction. It
        rides at the tail of the conversation, not in the cached prefix,
        so its length costs nothing the next turn.
        """
        known = ", ".join(self._tools)
        if not known:
            return f"No tool named {name!r} is registered; no tools are registered."
        return f"No tool named {name!r} is registered. Registered tools: {known}."

    @staticmethod
    def _verified_name(tool: Tool) -> str:
        """The one name this tool answers to, or a refusal."""
        name = tool.name
        declared = tool.definition().name
        if name != declared:
            raise ToolNameMismatch(
                f"tool.name is {name!r} but definition().name is {declared!r}; "
                "the registry would be keyed on one and the model shown the other"
            )
        if not name:
            raise ToolRegistrationError(
                "a tool must have a non-empty name; an unnamed tool cannot be "
                "called, and would answer for any call whose name is missing"
            )
        return name

    @staticmethod
    def _resolved_policy(tool: Tool, policy: ToolPolicy | None) -> ToolPolicy:
        """Apply the precedence documented on :meth:`policy_for`."""
        if policy is not None:
            return policy
        declared = getattr(tool, "policy", None)
        return declared if isinstance(declared, ToolPolicy) else _DECLARED_NOTHING


def _timing(elapsed: float) -> Mapping[str, float]:
    """Per-tool duration, which no vendor has a field for.

    Plan 0028 §11: the registry is where a call's own elapsed time is
    measurable without the loop having to time a seam it does not own.
    """
    return {"duration_s": elapsed}


def _failed(
    call: ToolCall,
    description: str,
    metadata: Mapping[str, float] | None = None,
) -> ToolResult:
    """The Observation a failure becomes — a result like any other.

    Filed under the call's own id and name: from the loop's side a
    failure *is* this call's answer, and an unanswered call means
    something else entirely.
    """
    return ToolResult(
        tool_call_id=call.id,
        name=call.name,
        output=description,
        is_error=True,
        metadata=metadata if metadata is not None else {},
    )


__all__ = [
    "ToolAlreadyRegistered",
    "ToolNameMismatch",
    "ToolRegistrationError",
    "ToolRegistry",
]
