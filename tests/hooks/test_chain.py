"""The onion: order, containment, and the pairing invariant.

Three properties this file exists to defend, each of which fails
silently if it breaks:

* **order** — forwards before, backwards after. A chain that closes in
  the wrong direction still returns an output, so only a test notices.
* **containment** — a hook that raises must not be reported to the model
  as the tool's failure (``tools/registry.py:330-332``). A broken hook
  in production looks exactly like a broken tool.
* **pairing** — every ``before_execute`` that returned gets exactly one
  of ``after_execute`` / ``on_failure``, *including when a later hook
  denies*. This is the property the reference harness's interface does
  not offer, so it is the one most worth pinning.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from omicsclaw.hooks import (
    Hook,
    HookAction,
    HookCall,
    HookDecision,
    HookDenied,
    HookedTool,
    ToolHook,
    allow,
    deny,
    hook_tools,
)
from omicsclaw.permission import PermissionGate, gate_tools
from omicsclaw.permission.rules import CONFIG_KEY, Rules
from omicsclaw.schema import ToolCall
from omicsclaw.tools import ToolRegistry

from ._support import Echo, Raiser, Recorder, run

_LONGER_THAN_THE_TEST = 30.0
"""A sleep the test's own five-second deadline will always beat.

So a hook that is *supposed* to be interrupted mid-await fails the test
by timing out rather than by quietly finishing early."""


async def _until(condition, *, tries: int = 500) -> None:
    """Yield to the loop until *condition* holds. Raises if it never does."""
    for _ in range(tries):
        if condition():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("the coroutine under test never reached its await")

# ---- pass-through -------------------------------------------------------


def test_no_hooks_wraps_nothing_at_all():
    """Identity, not equivalence.

    "This deployment mounts no hooks" has to mean the object graph did
    not change, or a regression anywhere can be blamed on this package.
    """
    tool = Echo()
    assert hook_tools([tool], ())[0] is tool


def test_a_hooked_tool_returns_what_the_tool_returned():
    tool = Echo()
    hooked = hook_tools([tool], (Recorder("a"),))[0]

    assert run(hooked.execute('{"text": "hi"}')) == 'echo:{"text": "hi"}'
    assert tool.calls == ['{"text": "hi"}']


def test_a_hooked_tool_forwards_name_and_definition():
    hooked = hook_tools([Echo("reader")], (Recorder("a"),))[0]

    assert hooked.name == "reader"
    assert hooked.definition().name == "reader"


def test_a_hooked_tool_forwards_the_authors_policy():
    """Not decoration: two callers read this attribute with ``getattr``.

    A wrapper that swallowed it would replace every author's declaration
    with ``ToolPolicy()`` — tightening most tools to ``ASK`` and turning
    a ``concurrency_safe`` tool into a scheduling barrier — and nothing
    would raise.
    """
    hooked = hook_tools([Echo()], (Recorder("a"),))[0]

    assert hooked.policy == Echo.policy
    assert hooked.policy is not None
    assert hooked.policy.concurrency_safe is True


def test_a_tool_without_a_policy_still_reports_none():
    class Bare(Echo):
        policy = None

    hooked = hook_tools([Bare()], (Recorder("a"),))[0]

    assert hooked.policy is None


def test_the_registry_reads_the_policy_through_the_wrapper():
    """The consequence of the previous test, at the place it is spent."""
    registry = ToolRegistry(hook_tools([Echo()], (Recorder("a"),)))

    assert registry.policy_for("echo") == Echo.policy
    assert registry.is_concurrency_safe("echo") is True


def test_the_inner_tool_is_reachable():
    tool = Echo()
    hooked = hook_tools([tool], (Recorder("a"),))[0]

    assert isinstance(hooked, HookedTool)
    assert hooked.inner is tool


# ---- order --------------------------------------------------------------


def test_before_runs_forwards_and_after_runs_backwards():
    first, second = Recorder("1"), Recorder("2")
    log: list[str] = []
    first.log = second.log = log

    hooked = hook_tools([Echo()], (first, second))[0]
    run(hooked.execute("{}"))

    assert log == ["before:1", "before:2", "after:2", "after:1"]


def test_the_outermost_hook_sees_what_the_inner_ones_made_of_the_output():
    """Onion, not pipeline: mount order decides who has the last word."""
    outer = Recorder("outer", rewrite="OUTER")
    inner = Recorder("inner", rewrite="INNER")

    hooked = hook_tools([Echo()], (outer, inner))[0]

    assert run(hooked.execute("{}")) == "OUTER"


def test_failures_are_announced_backwards_too():
    first, second = Recorder("1"), Recorder("2")
    log: list[str] = []
    first.log = second.log = log
    hooked = hook_tools([Raiser(ValueError("boom"))], (first, second))[0]

    with pytest.raises(ValueError):
        run(hooked.execute("{}"))

    assert log == ["before:1", "before:2", "failure:2", "failure:1"]


# ---- deny ---------------------------------------------------------------


def test_a_denied_call_never_reaches_the_tool():
    tool = Echo()
    hooked = hook_tools([tool], (Recorder("no", decision=deny("nope")),))[0]

    with pytest.raises(HookDenied) as caught:
        run(hooked.execute("{}"))

    assert tool.calls == []
    assert "nope" in str(caught.value)
    assert "echo" in str(caught.value)


def test_a_denial_names_the_hook_that_refused():
    """The model reads this string; "denied by a hook" is not actionable."""
    hooked = hook_tools([Echo()], (Recorder("no", decision=deny("why")),))[0]

    with pytest.raises(HookDenied) as caught:
        run(hooked.execute("{}"))

    assert "Recorder" in str(caught.value)


def test_hooks_that_already_decided_are_told_about_a_later_denial():
    """The pairing invariant, in the case the reference does not cover.

    ``hooks/hook.go:70-75`` returns on a deny without calling
    ``AfterExecute`` on any hook that already ran, so a hook that
    acquired something in ``BeforeExecute`` never releases it. Here it is
    told, and what it is told is the refusal itself.
    """
    watcher = Recorder("watcher")
    blocker = Recorder("blocker", decision=deny("no"))

    hooked = hook_tools([Echo()], (watcher, blocker))[0]
    with pytest.raises(HookDenied):
        run(hooked.execute("{}"))

    assert watcher.log == ["before:watcher", "failure:watcher"]
    assert len(watcher.failures) == 1
    assert isinstance(watcher.failures[0], HookDenied)


def test_the_hook_that_denied_is_not_told_about_its_own_denial():
    """It has not decided *yet* when it denies — it is deciding."""
    blocker = Recorder("blocker", decision=deny("no"))

    hooked = hook_tools([Echo()], (blocker,))[0]
    with pytest.raises(HookDenied):
        run(hooked.execute("{}"))

    assert blocker.log == ["before:blocker"]


def test_a_hook_after_the_one_that_denied_is_never_consulted():
    blocker = Recorder("blocker", decision=deny("no"))
    later = Recorder("later")

    hooked = hook_tools([Echo()], (blocker, later))[0]
    with pytest.raises(HookDenied):
        run(hooked.execute("{}"))

    assert later.log == []


def test_a_denial_reaches_the_model_as_an_error_observation():
    """Through the registry, which is the only path production has."""
    registry = ToolRegistry(
        hook_tools([Echo()], (Recorder("no", decision=deny("refused here")),))
    )

    result = run(registry.execute(ToolCall(id="1", name="echo", arguments="{}")))

    assert result.is_error
    assert "HookDenied" in result.output
    assert "refused here" in result.output


# ---- argument rewriting -------------------------------------------------


def test_a_hook_can_rewrite_the_payload_the_tool_receives():
    tool = Echo()
    rewriter = Recorder("r", decision=allow(arguments='{"text": "rewritten"}'))

    hooked = hook_tools([tool], (rewriter,))[0]
    run(hooked.execute('{"text": "original"}'))

    assert tool.calls == ['{"text": "rewritten"}']


def test_a_later_hook_sees_the_rewritten_payload():
    rewriter = Recorder("r", decision=allow(arguments='{"text": "B"}'))
    watcher = Recorder("w")

    hooked = hook_tools([Echo()], (rewriter, watcher))[0]
    run(hooked.execute('{"text": "A"}'))

    assert watcher.seen[0].arguments == '{"text": "B"}'


def test_after_execute_is_shown_the_rewritten_payload_too():
    """One ``HookCall`` per execution, carrying what actually ran."""
    rewriter = Recorder("r", decision=allow(arguments='{"text": "B"}'))

    hooked = hook_tools([Echo()], (rewriter,))[0]
    run(hooked.execute('{"text": "A"}'))

    assert [seen.arguments for seen in rewriter.seen] == [
        '{"text": "A"}',
        '{"text": "B"}',
    ]


def test_a_rewrite_is_not_re_judged_by_the_permission_gate():
    """The hazard, pinned so it is discovered here and not in a rule file.

    Hooks run **inside** the gate, so the verdict was resolved against
    what the model sent. A hook that rewrites the payload therefore runs
    something no rule ever saw. This test is the documentation being
    true; :attr:`omicsclaw.hooks.HookDecision.arguments` is the
    documentation.
    """
    tool = Echo("bash")
    gate = PermissionGate(
        rules=Rules.from_config({CONFIG_KEY: {"deny": ["bash(forbidden)"]}})
    )
    smuggler = Recorder("s", decision=allow(arguments='{"text": "forbidden"}'))

    gated = gate_tools(hook_tools([tool], (smuggler,)), gate)[0]
    registry = ToolRegistry()
    # AUTO so that nothing is *asked*: this test is about what a rule
    # judges, and an approval prompt would hide the answer behind a
    # missing channel.
    registry.register(gated, Echo.policy)

    result = run(
        registry.execute(
            ToolCall(id="1", name="bash", arguments=json.dumps({"text": "allowed"}))
        )
    )

    assert not result.is_error, result.output
    assert tool.calls == ['{"text": "forbidden"}']

    # And the same rule *does* bite when the model asks for it directly,
    # so the test above is about the ordering and not about a dead rule.
    direct = run(
        registry.execute(
            ToolCall(id="2", name="bash", arguments=json.dumps({"text": "forbidden"}))
        )
    )
    assert direct.is_error
    assert "PermissionDenied" in direct.output


def test_a_decision_without_a_rewrite_leaves_the_payload_alone():
    tool = Echo()
    hooked = hook_tools([tool], (Recorder("r", decision=HookDecision()),))[0]

    run(hooked.execute('{"text": "kept"}'))

    assert tool.calls == ['{"text": "kept"}']


# ---- containment --------------------------------------------------------


def test_a_hook_that_raises_before_does_not_stop_the_tool():
    """Fail-open, and the opposite of the gate on purpose.

    A broken observer must not break a working tool. A deployment that
    wants a call stopped when a check cannot run writes a permission
    rule, which is the layer that fails closed.
    """

    class Broken(Hook):
        async def before_execute(self, call: HookCall) -> HookDecision:
            raise RuntimeError("sink is down")

    tool = Echo()
    hooked = hook_tools([tool], (Broken(),))[0]

    assert run(hooked.execute("{}")) == "echo:{}"
    assert tool.calls == ["{}"]


def test_a_hook_that_raises_is_not_reported_as_the_tools_failure():
    """``tools/registry.py:330-332`` states the harm; this is the check.

    A hook that raised and escaped would reach the model as
    ``tool 'echo' raised RuntimeError`` — which sends it to fix a tool
    that is working.
    """

    class Broken(Hook):
        async def after_execute(self, call: HookCall, output: str) -> str:
            raise RuntimeError("sink is down")

    registry = ToolRegistry(hook_tools([Echo()], (Broken(),)))
    result = run(registry.execute(ToolCall(id="1", name="echo", arguments="{}")))

    assert not result.is_error, result.output
    assert result.output == "echo:{}"


def test_a_hook_that_raises_after_leaves_the_output_alone():
    class Broken(Hook):
        async def after_execute(self, call: HookCall, output: str) -> str:
            raise RuntimeError("sink is down")

    hooked = hook_tools([Echo()], (Recorder("keep"), Broken()))[0]

    assert run(hooked.execute("{}")) == "echo:{}"


def test_a_hook_that_raises_while_being_told_of_a_failure_is_contained():
    class Broken(Hook):
        async def on_failure(self, call: HookCall, error: BaseException) -> None:
            raise RuntimeError("sink is down")

    survivor = Recorder("survivor")
    hooked = hook_tools([Raiser(ValueError("real"))], (survivor, Broken()))[0]

    with pytest.raises(ValueError, match="real"):
        run(hooked.execute("{}"))

    assert survivor.log == ["before:survivor", "failure:survivor"]


def test_a_hook_whose_body_fell_off_the_end_allows():
    """``None.action`` here would be an ``AttributeError`` about the tool."""

    class Forgetful:
        async def before_execute(self, call: HookCall):
            return None

        async def after_execute(self, call: HookCall, output: str):
            return None

        async def on_failure(self, call: HookCall, error: BaseException) -> None:
            return None

    tool = Echo()
    hooked = hook_tools([tool], (Forgetful(),))[0]

    assert run(hooked.execute("{}")) == "echo:{}"
    assert tool.calls == ["{}"]


def test_a_synchronous_hook_is_heard_rather_than_silently_ignored():
    """``await`` on a returned value raises ``TypeError``, which this
    module contains and reads as "allow" — so a plain ``def`` hook would
    mount, register, and do nothing. The chain awaits only what is
    awaitable, the same way ``require_approval`` treats an approval
    channel.
    """

    class Synchronous:
        def __init__(self) -> None:
            self.log: list[str] = []

        def before_execute(self, call: HookCall) -> HookDecision:
            self.log.append("before")
            return HookDecision()

        def after_execute(self, call: HookCall, output: str) -> str:
            self.log.append("after")
            return output.upper()

        def on_failure(self, call: HookCall, error: BaseException) -> None:
            self.log.append("failure")

    hook = Synchronous()
    hooked = hook_tools([Echo()], (hook,))[0]

    assert run(hooked.execute("{}")) == "ECHO:{}"
    assert hook.log == ["before", "after"]


def test_a_synchronous_hook_can_deny_too():
    """The half that would have been a security hole rather than a no-op."""

    class Synchronous(Hook):
        def before_execute(self, call: HookCall) -> HookDecision:
            return deny("no")

    tool = Echo()
    hooked = hook_tools([tool], (Synchronous(),))[0]

    with pytest.raises(HookDenied):
        run(hooked.execute("{}"))
    assert tool.calls == []


def test_a_hook_that_returns_a_non_string_does_not_corrupt_the_output():
    class Sloppy(Hook):
        async def after_execute(self, call: HookCall, output: str):
            return 42

    hooked = hook_tools([Echo()], (Sloppy(),))[0]

    assert run(hooked.execute("{}")) == "echo:{}"


# ---- what is *not* contained --------------------------------------------


def test_the_tools_own_exception_propagates_unchanged():
    """A hook may not swap a failure for another one.

    The registry builds the model's error text out of the exception's
    class name; a chain that re-raised something of its own would make
    every tool failure read as a hooks bug.
    """
    original = ValueError("the real problem")
    hooked = hook_tools([Raiser(original)], (Recorder("a"),))[0]

    with pytest.raises(ValueError) as caught:
        run(hooked.execute("{}"))

    assert caught.value is original


def test_a_cancelled_call_stays_cancelled_and_hooks_still_hear_about_it():
    """``CancelledError`` is not a tool failure and is not caught.

    It is still announced, because a hook that started something in
    ``before_execute`` needs to release it on a cancelled turn as much
    as on a failed one — which is also the only way
    ``AuditOutcome.CANCELLED`` is ever reachable.
    """
    watcher = Recorder("watcher")
    hooked = hook_tools([Raiser(asyncio.CancelledError())], (watcher,))[0]

    with pytest.raises(asyncio.CancelledError):
        run(hooked.execute("{}"))

    assert watcher.log == ["before:watcher", "failure:watcher"]
    assert isinstance(watcher.failures[0], asyncio.CancelledError)


def test_a_cancellation_during_notification_wins_over_the_tool_failure():
    """**Rewritten from a test that pinned the harm.** Read this before
    reverting it.

    The first version asserted the opposite — that a cancellation raised
    while a hook was being told of a failure should be swallowed, leaving
    the tool's own exception to propagate — and justified it on the claim
    that awaiting inside a cancelled Task raises again on its own. That
    claim is false: catching a :exc:`asyncio.CancelledError` does not
    make later awaits re-raise. What the handler actually absorbed was a
    **new** cancellation, and the cost is in the test below it: a
    cancelled turn reaching
    :meth:`~omicsclaw.tools.ToolRegistry.execute` as an ordinary
    ``Exception``, which that method catches and turns into an
    ``is_error`` Observation the model can retry.

    If this test ever fails again, the question to ask is not "how do I
    keep the original exception" but "what will the registry do with it".
    """

    class Reraising(Hook):
        async def on_failure(self, call: HookCall, error: BaseException) -> None:
            raise asyncio.CancelledError()

    hooked = hook_tools([Raiser(ValueError("the real problem"))], (Reraising(),))[0]

    with pytest.raises(asyncio.CancelledError):
        run(hooked.execute("{}"))


def test_a_swallowed_cancellation_would_reach_the_model_as_a_retryable_error():
    """Why the test above is worth its rewrite, stated at the destination.

    ``tools/registry.py:314-321`` catches ``Exception`` and never
    ``BaseException``, so that a cancelled turn cannot come back as an
    Observation. A chain that downgraded a cancellation to the tool's
    ``ValueError`` would walk straight past that guard.
    """

    class Reraising(Hook):
        async def on_failure(self, call: HookCall, error: BaseException) -> None:
            raise asyncio.CancelledError()

    registry = ToolRegistry(
        hook_tools([Raiser(ValueError("the real problem"))], (Reraising(),))
    )

    with pytest.raises(asyncio.CancelledError):
        run(registry.execute(ToolCall(id="1", name="echo", arguments="{}")))


def test_a_real_task_cancel_during_notification_is_not_absorbed():
    """The same property under a genuine ``task.cancel()``.

    Every other cancellation test in this file raises
    :exc:`asyncio.CancelledError` by hand, which is a different thing
    from the loop delivering one — and the defect this pins was reachable
    only by the second. A hook that awaits anything in ``on_failure``
    (a socket, a queue) is an ordinary hook, so this is an ordinary path.
    """

    class Slow(Hook):
        def __init__(self) -> None:
            self.entered = False

        async def on_failure(self, call: HookCall, error: BaseException) -> None:
            self.entered = True
            await asyncio.sleep(_LONGER_THAN_THE_TEST)

    slow = Slow()
    hooked = hook_tools([Raiser(ValueError("ordinary tool failure"))], (slow,))[0]

    async def scenario() -> BaseException:
        task = asyncio.create_task(hooked.execute("{}"))
        await _until(lambda: slow.entered)
        task.cancel()
        try:
            await task
        except BaseException as exc:  # noqa: BLE001 — the point of the test
            return exc
        raise AssertionError("the cancelled call returned a value")

    assert isinstance(run(scenario()), asyncio.CancelledError)


def test_a_cancellation_while_deciding_still_closes_the_hooks_that_allowed():
    """The pairing invariant under a ``BaseException`` in ``before_execute``.

    The decision loop and the tool call used to be two blocks with a
    handler on only the second, so a hook cancelled while deciding left
    every hook before it with nothing — exactly the leak this package
    claims to fix in the reference's deny path, in a place nobody had
    looked.
    """

    class Canceller(Hook):
        async def before_execute(self, call: HookCall) -> HookDecision:
            raise asyncio.CancelledError()

    watcher = Recorder("watcher")
    hooked = hook_tools([Echo()], (watcher, Canceller()))[0]

    with pytest.raises(asyncio.CancelledError):
        run(hooked.execute("{}"))

    assert watcher.log == ["before:watcher", "failure:watcher"]
    assert isinstance(watcher.failures[0], asyncio.CancelledError)


def test_a_real_task_cancel_while_deciding_closes_them_too():
    """The same, delivered by the loop rather than raised by hand."""

    class Slow(Hook):
        def __init__(self) -> None:
            self.entered = False

        async def before_execute(self, call: HookCall) -> HookDecision:
            self.entered = True
            await asyncio.sleep(_LONGER_THAN_THE_TEST)
            return HookDecision()

    slow = Slow()
    watcher = Recorder("watcher")
    tool = Echo()
    hooked = hook_tools([tool], (watcher, slow))[0]

    async def scenario() -> None:
        task = asyncio.create_task(hooked.execute("{}"))
        await _until(lambda: slow.entered)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(scenario())

    assert watcher.log == ["before:watcher", "failure:watcher"]
    assert tool.calls == [], "the tool never ran"


def test_a_keyboard_interrupt_while_deciding_closes_them_too():
    """``BaseException``, not just cancellation: Ctrl-C takes the same path."""

    class Interrupter(Hook):
        async def before_execute(self, call: HookCall) -> HookDecision:
            raise KeyboardInterrupt()

    watcher = Recorder("watcher")
    hooked = hook_tools([Echo()], (watcher, Interrupter()))[0]

    with pytest.raises(KeyboardInterrupt):
        run(hooked.execute("{}"))

    assert watcher.log == ["before:watcher", "failure:watcher"]


# ---- construction -------------------------------------------------------


def test_a_half_written_hook_is_refused_when_the_chain_is_built():
    class MissingOne:
        async def before_execute(self, call: HookCall) -> HookDecision:
            return HookDecision()

        async def after_execute(self, call: HookCall, output: str) -> str:
            return output

    with pytest.raises(TypeError, match="on_failure"):
        HookedTool(Echo(), (MissingOne(),))


def test_the_refusal_names_the_class_and_points_at_the_base_class():
    with pytest.raises(TypeError) as caught:
        HookedTool(Echo(), (object(),))

    assert "object" in str(caught.value)
    assert "Hook" in str(caught.value)


def test_the_chain_is_readable_and_in_registration_order():
    first, second = Recorder("1"), Recorder("2")
    hooked = HookedTool(Echo(), (first, second))

    assert hooked.hooks == (first, second)


def test_hook_tools_preserves_order():
    """Tool order is prompt bytes a vendor caches on."""
    tools = [Echo("a"), Echo("b"), Echo("c")]

    hooked = hook_tools(tools, (Recorder("h"),))

    assert [tool.name for tool in hooked] == ["a", "b", "c"]


def test_hook_tools_is_deliberately_not_idempotent():
    """Two layers are two chains — how a sub-agent adds its own."""
    once = hook_tools([Echo()], (Recorder("1"),))
    twice = hook_tools(once, (Recorder("2"),))

    assert isinstance(twice[0], HookedTool)
    assert isinstance(twice[0].inner, HookedTool)


# ---- conformance --------------------------------------------------------


def test_the_base_class_satisfies_the_protocol():
    assert isinstance(Hook(), ToolHook)


def test_a_hook_that_inherits_nothing_satisfies_the_protocol():
    assert isinstance(Recorder("a"), ToolHook)


def test_the_base_class_does_nothing_to_a_call():
    tool = Echo()
    hooked = hook_tools([tool], (Hook(),))[0]

    assert run(hooked.execute('{"text": "x"}')) == 'echo:{"text": "x"}'
    assert tool.calls == ['{"text": "x"}']


def test_a_hook_is_shown_the_tools_name_and_raw_arguments():
    watcher = Recorder("w")
    hook_tools([Echo("reader")], (watcher,))[0]

    run(hook_tools([Echo("reader")], (watcher,))[0].execute('{"text": "raw"}'))

    call = watcher.seen[0]
    assert isinstance(call, HookCall)
    assert call.name == "reader"
    assert call.arguments == '{"text": "raw"}'


def test_a_hook_call_carries_no_tool_call_id():
    """The tool layer withholds it; a hook does not get it back by proxy."""
    assert not hasattr(HookCall(name="x", arguments="{}"), "id")


def test_allow_and_deny_build_what_they_say():
    assert allow().action is HookAction.ALLOW
    assert allow().arguments is None
    assert allow(arguments="{}").arguments == "{}"
    assert deny("why").action is HookAction.DENY
    assert deny("why").reason == "why"


def test_the_default_decision_allows_and_changes_nothing():
    """``return HookDecision()`` is the whole body of most hooks."""
    decision = HookDecision()

    assert decision.action is HookAction.ALLOW
    assert decision.arguments is None
    assert decision.reason == ""
