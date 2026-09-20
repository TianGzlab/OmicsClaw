"""What a hook *is*, and what one is allowed to say.

Four types and one convenience base class. :class:`HookCall` is what a
hook is shown, :class:`HookDecision` is what it may say back,
:class:`ToolHook` is the shape, and :class:`Hook` is three no-ops to
inherit when only one of them is interesting.

**The vocabulary is deliberately narrower than the reference harness's.**
``hooks/decision.go:15-22`` has three actions — allow, deny, *ask* — and
two context keys (``approvedContextKey``, ``explicitlyAllowedContextKey``)
whose only job is to stop the third one asking the same person twice.
This package has two actions and no keys, because asking already has an
owner here: :mod:`omicsclaw.permission` resolves mode, rules and danger
patterns in one pass and puts the question at most once
(``permission/gate.py``). See :mod:`omicsclaw.hooks` for why a third
answer to "why was I asked?" is worth refusing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

__all__ = [
    "Hook",
    "HookAction",
    "HookCall",
    "HookDecision",
    "HookDenied",
    "ToolHook",
    "allow",
    "deny",
]


class HookDenied(RuntimeError):
    """A hook refused this call. The tool did not run.

    Raised by :class:`~omicsclaw.hooks.chain.HookedTool` out of
    ``execute``, so it reaches the model the way every other tool failure
    does — as an ``is_error`` Observation naming the class and carrying
    the reason (``tools/registry.py:302-372``). That is the same shape
    :exc:`~omicsclaw.permission.PermissionDenied` already has, on
    purpose: a refusal the model can read and act on should not depend on
    which layer refused.

    Distinct from :exc:`~omicsclaw.permission.PermissionDenied` because
    the two answer different questions. Permission answers *may this
    happen at all*, from configuration a person wrote. A hook answers
    *does this deployment want to interpose something*, from code a
    composition root mounted. Collapsing them would put a deployment's
    interposition in the rule file's error vocabulary, where an operator
    would go looking for a rule that does not exist.
    """


@dataclass(frozen=True, slots=True)
class HookCall:
    """The call a hook is shown: a name and a raw argument payload.

    ``arguments`` is the **unparsed JSON string**, exactly as
    :attr:`~omicsclaw.schema.ToolCall.arguments` carries it and exactly
    as :meth:`~omicsclaw.tools.Tool.execute` receives it. A hook that
    wants a ``dict`` decodes one itself; the seam does not decode,
    because a decode-then-re-encode reorders keys and the byte-exact
    payload is what prompt-prefix caching and replay evidence rest on
    (``tools/base.py:89-99``).

    **``ToolCall.id`` is absent, and that is the same decision the tool
    layer made.** A tool has no business knowing the call id, so handing
    it to a hook would reintroduce the dependency one layer down —
    ``hooks/offload.go:83-85`` names files after it and has to check for
    the empty string it is not guaranteed against. A hook that needs to
    correlate two records uses a digest of what it was actually shown;
    see :class:`~omicsclaw.hooks.audit.AuditRecord`.
    """

    name: str
    """The tool being called, as the registry knows it."""

    arguments: str
    """The raw JSON payload. **Never log this** — it is a ``bash``
    command line, a ``write_file`` body, a ``web_fetch`` URL."""


class HookAction(StrEnum):
    """What a :class:`HookDecision` says. Two values, not three.

    A :class:`~enum.StrEnum` so ``HookAction.ALLOW == "allow"`` holds and
    a decision survives a round trip through a config file or a log line
    without a converter.
    """

    ALLOW = "allow"
    """Run the call. The default, and what a broken hook is treated as."""

    DENY = "deny"
    """Refuse the call. The tool does not run and the model is told why."""


@dataclass(frozen=True, slots=True)
class HookDecision:
    """What a hook says before the tool runs.

    The default instance allows and changes nothing, so
    ``return HookDecision()`` is the whole body of a hook that only cares
    about what happens afterwards.
    """

    action: HookAction = HookAction.ALLOW

    reason: str = ""
    """Why, in words meant for a person and for the model. Required in
    spirit on a ``DENY`` — it becomes the text of the
    :exc:`HookDenied` the model reads, and "denied by a hook" tells it
    nothing it can act on."""

    arguments: str | None = None
    """A rewritten raw payload, or ``None`` to leave the call alone.

    **Read the hazard before using this.** The hook chain runs *inside*
    the permission gate (see :mod:`omicsclaw.hooks`), so a rewrite is not
    re-judged: the gate resolved its verdict against the arguments the
    model sent, and the inner tool receives these instead. A hook that
    rewrites ``{"command": "ls"}`` into ``{"command": "rm -rf /"}``
    executes a command no rule ever saw.

    That is not an accident of the ordering, it is the price of it —
    putting hooks outside the gate would make rewrites judged and make
    every hook able to ask a person a second question. Hooks are code a
    composition root mounted, at the same trust level as the tools they
    wrap, and this field is where that trust is actually spent.
    ``tests/hooks/test_chain.py`` pins the behaviour so nobody discovers
    it from a rule file that silently stopped meaning anything."""


def allow(*, arguments: str | None = None) -> HookDecision:
    """Run the call, optionally with a rewritten payload."""
    return HookDecision(action=HookAction.ALLOW, arguments=arguments)


def deny(reason: str) -> HookDecision:
    """Refuse the call, with a reason the model will be shown."""
    return HookDecision(action=HookAction.DENY, reason=reason)


@runtime_checkable
class ToolHook(Protocol):
    """Three moments around one tool call.

    A :class:`~typing.Protocol` for the reason
    :class:`~omicsclaw.tools.Tool` is one: conformance is a matter of
    shape, so a test double imports nothing from here. ``runtime_checkable``
    makes :func:`isinstance` work, which
    :func:`~omicsclaw.hooks.chain.hook_tools` uses to refuse a
    half-written hook at composition time rather than mid-run.

    **Three methods, where the reference harness has two.** Go's inner
    ``Registry.Execute`` returns a ``ToolResult{IsError}`` instead of
    raising, so ``AfterExecute`` can take one argument and cover both
    outcomes (``hooks/hook.go:23-26``). In Python the tool *raises*, and
    flattening an exception into a string to fit one signature would
    throw away the type — which is exactly what
    :meth:`~omicsclaw.tools.ToolRegistry.execute` builds the model's
    error text out of. So the failure path is its own method, and it
    returns ``None`` because that is the honest signature: a hook cannot
    rewrite a failure, and a return value that is silently ignored is a
    contract nobody can test.

    **Exactly one of :meth:`after_execute` and :meth:`on_failure` runs
    for every :meth:`before_execute` that *allowed* the call.** So a hook
    that acquires something in ``before_execute`` always gets the chance
    to release it — including when a *later* hook denies, when the tool
    raises, and when the turn is cancelled, whether that cancellation
    lands on the tool or on another hook still deciding. The reference's
    interface offers none of that: ``hooks/hook.go:70-75`` returns on a
    deny without calling ``AfterExecute`` on any hook that already ran.

    *Allowed*, not *returned*, and the difference is one case: a hook
    that **denies** gets no closing call of its own. It has not finished
    deciding when it refuses, so there is nothing yet to close; see
    ``tests/hooks/test_chain.py::test_the_hook_that_denied_is_not_told_about_its_own_denial``.

    All three are declared ``async`` so a hook may await — a sink that
    writes over a socket, a check that reads a file — and that is the
    shape to write. A plain ``def`` is nevertheless *heard*: the chain
    awaits only what is awaitable
    (:func:`~omicsclaw.hooks.chain._resolved`), because the alternative
    is silent. ``await`` on a returned :class:`HookDecision` raises
    :exc:`TypeError`, which the chain contains and reads as "allow", so a
    synchronous hook would mount, register, and do nothing.
    """

    async def before_execute(self, call: HookCall) -> HookDecision:
        """Decide, and optionally rewrite the payload.

        Raising is not how a hook refuses — a raise is contained and read
        as :data:`HookAction.ALLOW` (see
        :class:`~omicsclaw.hooks.chain.HookedTool`). Refuse with
        :func:`deny`.
        """
        ...

    async def after_execute(self, call: HookCall, output: str) -> str:
        """The tool succeeded. Return the output, or a replacement.

        Runs in reverse registration order, so the first hook mounted is
        the outermost and sees what every other hook made of the output.
        """
        ...

    async def on_failure(self, call: HookCall, error: BaseException) -> None:
        """The tool raised, or a later hook denied. Observe only.

        ``error`` may be a :exc:`HookDenied` raised by a hook further
        down the chain, or anything the tool raised —
        :exc:`asyncio.CancelledError` included, because a hook that
        started something in :meth:`before_execute` needs to hear about
        a cancelled turn as much as about a failed one.
        """
        ...


class Hook:
    """Three no-ops. Inherit to write a hook that only cares about one.

    Optional: :class:`ToolHook` is structural, so a hook that inherits
    nothing is a hook. This exists because the common case is a hook that
    overrides exactly one of the three, and making it spell the other two
    out is how a no-op body acquires a typo.

    Not an :class:`~abc.ABC`: there is no method a subclass *must*
    override. A subclass that overrides none of them is a valid hook that
    does nothing, which is a useful thing for a test to be able to build.
    """

    __slots__ = ()

    async def before_execute(self, call: HookCall) -> HookDecision:
        """Allow, unchanged."""
        return HookDecision()

    async def after_execute(self, call: HookCall, output: str) -> str:
        """The output, unchanged."""
        return output

    async def on_failure(self, call: HookCall, error: BaseException) -> None:
        """Nothing."""
        return None
