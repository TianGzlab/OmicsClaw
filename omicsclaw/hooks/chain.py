"""The onion: hooks around one tool, in order, with their failures contained.

:class:`HookedTool` decorates a :class:`~omicsclaw.tools.Tool`;
:func:`hook_tools` applies it to a list. Zero hooks produce no wrapper at
all, so a deployment that mounts none runs byte-for-byte what it ran
before this package existed.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging
from collections.abc import Iterable, Sequence

from omicsclaw.schema import ToolDefinition
from omicsclaw.tools.base import Tool, ToolPolicy

from .base import Hook, HookAction, HookCall, HookDecision, HookDenied, ToolHook

_log = logging.getLogger(__name__)

__all__ = ["HookedTool", "hook_tools"]


class HookedTool:
    """One tool with a hook chain around it.

    **Decorates a tool, not the registry**, which is the decision plan
    0038 §2 already made for :class:`~omicsclaw.permission.GatedTool` and
    the reason is unchanged: the engine probes the registry with
    :func:`isinstance` for two optional Protocols
    (``ConcurrencyAwareExecutor``, ``DeadlineAwareExecutor``), and a
    wrapper that forgets to forward either does not fail — it silently
    puts a human's approval time back inside the per-tool timeout.
    ``entry/assembly.py`` calls that defect R3. The reference harness
    wraps the registry (``hooks/hook.go:28-38``) and has no such
    Protocols to lose.

    **A hook's own failure is contained.**
    ``tools/registry.py:330-332`` states the rule this package has to
    live with: a lifecycle hook that raised inside the registry's ``try``
    would be reported to the model as *the tool's* failure. Decorating a
    tool puts this chain inside that ``try``, so the rule is honoured the
    other way round — every call into a hook is wrapped here, and a hook
    that raises is logged and treated as :data:`~omicsclaw.hooks.HookAction.ALLOW`.
    A broken metrics sink does not get to break a working tool.

    **Fail-open, and that is the opposite of the gate on purpose.**
    :func:`~omicsclaw.tools.require_approval` refuses when it cannot ask,
    because the absence of consent is not consent. A hook is not consent:
    it is interposition a deployment chose to add, and a deployment that
    wants a call stopped when a check cannot run writes a permission rule,
    which is the layer that fails closed. Two mechanisms with two failure
    directions, each documented where it is decided.

    A deliberate ``deny`` is the one exception: it raises
    :exc:`~omicsclaw.hooks.HookDenied` and the tool does not run.
    """

    __slots__ = ("_hooks", "_inner")

    def __init__(self, inner: Tool, hooks: Sequence[ToolHook]) -> None:
        """Wrap *inner* in *hooks*, applied in the order given.

        Order is registration order, forwards for
        :meth:`~omicsclaw.hooks.ToolHook.before_execute` and backwards
        for the two closing calls — the first hook mounted is the
        outermost. Deliberately unlike the reference's map iteration,
        for the reason ``ToolRegistry`` keeps its own order: a hook that
        rewrites an output must see a stable picture of what the hooks
        inside it did.

        :raises TypeError: a member of *hooks* is missing one of the
            three methods. Checked here rather than at the call, because
            a chain that is wrong is wrong before the first turn and an
            ``AttributeError`` in the middle of a run names the wrong
            thing.
        """
        for hook in hooks:
            if not isinstance(hook, ToolHook):
                raise TypeError(
                    f"{type(hook).__name__} is not a ToolHook: it must define "
                    "before_execute, after_execute and on_failure "
                    f"(inherit {Hook.__name__} for no-op defaults)"
                )
        self._inner = inner
        self._hooks = tuple(hooks)

    @property
    def inner(self) -> Tool:
        """The tool underneath. Mirrors
        :attr:`~omicsclaw.permission.GatedTool.inner` so one idiom
        unwraps either."""
        return self._inner

    @property
    def hooks(self) -> tuple[ToolHook, ...]:
        """The chain, in registration order. Read-only."""
        return self._hooks

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def policy(self) -> ToolPolicy | None:
        """The inner tool's declared policy, forwarded.

        Not decorative. Both
        :meth:`~omicsclaw.tools.ToolRegistry.register` and
        :meth:`~omicsclaw.permission.GatedTool.execute` read a tool's
        ``policy`` attribute with :func:`getattr` to find what its author
        declared; a wrapper that did not forward it would silently
        replace every author's declaration with ``ToolPolicy()`` —
        tightening most tools to ``ASK`` and, for anything the author had
        marked ``concurrency_safe``, turning a parallel batch into a
        serial one. Neither shows up as an error.
        """
        declared = getattr(self._inner, "policy", None)
        return declared if isinstance(declared, ToolPolicy) else None

    def definition(self) -> ToolDefinition:
        return self._inner.definition()

    async def execute(self, arguments: str) -> str:
        """Before, inner, then after — or on_failure.

        **One ``except`` covers the decision loop and the tool**, which
        is a repair and not a tidy-up. They were two blocks, and only the
        second had a handler: a hook whose ``before_execute`` raised a
        :exc:`BaseException` — a real ``task.cancel()`` landing on its
        ``await``, a ``KeyboardInterrupt`` — left every hook that had
        already allowed the call with no closing call at all. The
        advertised invariant is that a hook which opened something in
        ``before_execute`` always gets to release it, and a turn being
        cancelled is exactly when that matters.

        The refusal is raised rather than returned so it takes the same
        path. ``decided`` does not contain the hook that is refusing,
        because a hook is appended only after it allows — so it is not
        told about its own denial, which is not an omission: it has not
        finished deciding.

        :raises HookDenied: a hook refused. The inner tool did not run.
        """
        call = HookCall(name=self._inner.name, arguments=arguments)
        decided: list[ToolHook] = []

        try:
            for hook in self._hooks:
                decision = await self._decide(hook, call)
                if decision.action is HookAction.DENY:
                    raise HookDenied(
                        f"{call.name} refused by {type(hook).__name__}"
                        f"{f' — {decision.reason}' if decision.reason else ''}"
                    )
                if decision.arguments is not None:
                    call = dataclasses.replace(call, arguments=decision.arguments)
                decided.append(hook)

            output = await self._inner.execute(call.arguments)
        except BaseException as error:
            await self._notify(decided, call, error)
            raise

        for hook in reversed(decided):
            output = await self._rewrite(hook, call, output)
        return output

    # ---- internals ------------------------------------------------------

    async def _decide(self, hook: ToolHook, call: HookCall) -> HookDecision:
        """One ``before_execute``, contained.

        A hook that raises, or that returns something which is not a
        :class:`HookDecision`, allows. The second half matters as much as
        the first: a hook whose body falls off the end returns ``None``,
        and reading ``None.action`` here would report an
        :exc:`AttributeError` against the *tool*.
        """
        try:
            decision = await _resolved(hook.before_execute(call))
        except Exception:
            _log.exception(
                "hook %s raised before %s; allowing",
                type(hook).__name__,
                call.name,
            )
            return HookDecision()
        if isinstance(decision, HookDecision):
            return decision
        _log.error(
            "hook %s returned %s from before_execute, not a HookDecision; "
            "allowing",
            type(hook).__name__,
            type(decision).__name__,
        )
        return HookDecision()

    async def _rewrite(self, hook: ToolHook, call: HookCall, output: str) -> str:
        """One ``after_execute``, contained. A non-``str`` is ignored."""
        try:
            rewritten = await _resolved(hook.after_execute(call, output))
        except Exception:
            _log.exception(
                "hook %s raised after %s; keeping the output",
                type(hook).__name__,
                call.name,
            )
            return output
        if isinstance(rewritten, str):
            return rewritten
        _log.error(
            "hook %s returned %s from after_execute, not a str; "
            "keeping the output",
            type(hook).__name__,
            type(rewritten).__name__,
        )
        return output

    async def _notify(
        self,
        decided: Sequence[ToolHook],
        call: HookCall,
        error: BaseException,
    ) -> None:
        """Close every hook that decided, newest first.

        A hook that raises an :exc:`Exception` here is logged and the
        rest are still told — one broken sink must not cost the others
        their notification, and it must not mask *error*, which is the
        thing the caller is about to see.

        **A :exc:`BaseException` is not caught, and the first version of
        this method caught it.** It logged and stopped, on the stated
        reasoning that awaiting inside an already-cancelled Task raises
        :exc:`asyncio.CancelledError` again — which is not true: catching
        a cancellation does not make later awaits re-raise on their own.
        What that handler actually absorbed was a **new** cancellation
        arriving during the notification, after which ``execute``'s bare
        ``raise`` re-raised the *tool's* exception instead. A cancelled
        turn then reached :meth:`~omicsclaw.tools.ToolRegistry.execute`
        as an ordinary ``Exception``, was caught there, and came back to
        the model as an ``is_error`` Observation it could retry — which
        is precisely what ``tools/registry.py:314-321`` says must never
        happen, reached around the side of the check that forbids it.

        So a cancellation wins over the failure being reported. The
        hooks not yet told lose their notification, which is the lesser
        loss: the alternative is a turn that was cancelled continuing to
        run.
        """
        for hook in reversed(decided):
            try:
                await _resolved(hook.on_failure(call, error))
            except Exception:
                _log.exception(
                    "hook %s raised while being told %s failed",
                    type(hook).__name__,
                    call.name,
                )


async def _resolved(outcome: object) -> object:
    """Await *outcome* if it is awaitable, otherwise take it as it is.

    :class:`~omicsclaw.hooks.ToolHook` declares all three methods
    ``async``, and that is still the shape to write. This tolerates a
    hook that is a plain ``def`` because the alternative is **silent**:
    ``await`` on a returned :class:`~omicsclaw.hooks.HookDecision` raises
    :exc:`TypeError`, which this module then contains and reads as
    "allow" — so a synchronous hook would be mounted, would register, and
    would do nothing, with one line in a log nobody is reading.

    The same shape as :func:`~omicsclaw.tools.require_approval`'s
    treatment of an approval channel (``tools/context.py:614-615``), and
    for the same reason: a callback supplied from outside this package
    should not have to be a coroutine function to be heard.
    """
    return await outcome if inspect.isawaitable(outcome) else outcome


def hook_tools(
    tools: Iterable[Tool], hooks: Sequence[ToolHook]
) -> tuple[Tool, ...]:
    """Every tool, hooked, in the order given.

    **An empty chain wraps nothing.** Not an optimisation: it is what
    makes "this deployment mounts no hooks" mean *the object graph has
    not changed*, so a regression in a hook-less deployment cannot be
    blamed on this package and a test can assert the identity.

    Deliberately **not idempotent**, unlike
    :func:`~omicsclaw.permission.gate_tools`. A gate wrapped twice asks a
    person twice, which is a harm with no legitimate reading; two hook
    layers are two different chains, which is how a sub-agent adds its
    own without losing its parent's. A caller that wants one chain passes
    one list.
    """
    if not hooks:
        return tuple(tools)
    return tuple(HookedTool(tool, hooks) for tool in tools)
