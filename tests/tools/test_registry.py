"""Contract tests for ``omicsclaw.tools.registry`` (plan 0028 §7).

One named test per trap, and the traps are mostly about what a registry
must refuse to do: refuse to reorder itself, refuse to raise at the model,
refuse to swallow a cancellation, refuse to let a second tool take a name
that is taken, refuse to learn what a request is.

``pytest-asyncio`` is not installed, so async cases are driven through
:func:`asyncio.run` under a hang guard — the convention
``tests/provider/`` and ``tests/engine/`` already follow.

Nothing here subclasses :class:`~omicsclaw.tools.base.Tool`. The doubles
below import :mod:`omicsclaw.schema` only, so every case is also evidence
that the Protocol is satisfiable by shape.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from omicsclaw.schema import ToolCall, ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import effective_policy
from omicsclaw.tools.registry import (
    ToolAlreadyRegistered,
    ToolNameMismatch,
    ToolRegistrationError,
    ToolRegistry,
)

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds one scenario may take. A hang guard, not a measurement."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


class Fake:
    """A tool whose behaviour is one callable, and nothing else."""

    def __init__(
        self,
        name: str,
        behaviour: Callable[[str], Awaitable[str]] | None = None,
        *,
        declared_name: str | None = None,
        policy: Any = None,
        description: str = "",
    ) -> None:
        self._name = name
        self._declared_name = name if declared_name is None else declared_name
        self._behaviour = behaviour
        self._description = description or f"the {name} tool"
        self.seen: list[str] = []
        if policy is not None:
            # Only set when given, so "the tool declared nothing" is the
            # genuine absence of the attribute rather than a ``None``.
            self.policy = policy

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._declared_name,
            description=self._description,
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: str) -> str:
        self.seen.append(arguments)
        if self._behaviour is None:
            return f"{self._name} ran"
        return await self._behaviour(arguments)


async def _raising(exc: BaseException) -> str:
    raise exc


def _call(name: str, arguments: str = "{}", identifier: str = "c1") -> ToolCall:
    return ToolCall(id=identifier, name=name, arguments=arguments)


# ---- trap 1: the order is registration order ----------------------------

_UNSORTED = ("zeta", "alpha", "mu")
"""Three names whose registration order differs from every derived order.

Alphabetical gives ``alpha, mu, zeta`` and reverse gives ``zeta, mu,
alpha``; a hash-ordered set gives something else again. Any of those is a
distinguishable failure, which is what makes the assertion below able to
catch a ``sorted()`` slipped into the implementation.
"""


def _unsorted_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in _UNSORTED:
        registry.register(Fake(name))
    return registry


def test_available_tools_is_in_registration_order():
    """Trap 1. Not a style preference — a billing fact.

    Tool definitions sit inside the prompt prefix every vendor caches,
    and a list that reorders itself moves the cache breakpoint ahead of
    the tool segment, re-billing everything behind it at roughly ten
    times the hit rate. The reference harness documents its own order as
    unspecified because Go randomizes map iteration; copying that
    behaviour would copy a defect.
    """
    definitions = _unsorted_registry().available_tools()

    assert tuple(d.name for d in definitions) == _UNSORTED
    assert tuple(d.name for d in definitions) != tuple(sorted(_UNSORTED))


def test_names_is_in_registration_order():
    assert _unsorted_registry().names() == _UNSORTED


def test_available_tools_is_identical_between_calls():
    """The invariant the prefix cache actually pays for.

    Order being right once is not enough; it has to be the *same* order
    next turn, since the loop re-reads this every turn by design.
    """
    registry = _unsorted_registry()

    first = registry.available_tools()
    second = registry.available_tools()

    assert first == second


def test_replace_keeps_a_tool_in_its_place():
    """Swapping an implementation must not churn the prompt prefix."""
    registry = _unsorted_registry()

    registry.replace(Fake("alpha", description="a different alpha"))

    assert registry.names() == _UNSORTED
    assert registry.available_tools()[1].description == "a different alpha"


def test_unregister_then_register_moves_a_tool_to_the_end():
    """The difference ``replace`` exists to offer, asserted rather than implied."""
    registry = _unsorted_registry()

    registry.unregister("alpha")
    registry.register(Fake("alpha"))

    assert registry.names() == ("zeta", "mu", "alpha")


def test_the_constructor_registers_in_the_order_given():
    registry = ToolRegistry(Fake(name) for name in _UNSORTED)

    assert registry.names() == _UNSORTED


# ---- trap 2: an unknown tool is an Observation, not an exception --------


def test_an_unknown_tool_is_an_error_result_and_not_a_raise():
    """Trap 2. The model can correct a misspelled name; it cannot correct a crash."""
    registry = _unsorted_registry()

    result = _run(registry.execute(_call("no_such_tool", identifier="c7")))

    assert result.is_error is True
    assert result.tool_call_id == "c7"
    assert result.name == "no_such_tool"
    assert "no_such_tool" in result.output


def test_the_unknown_tool_message_says_what_is_available():
    """The Observation exists to be corrected from, so it carries the options."""
    output = _run(_unsorted_registry().execute(_call("nope"))).output

    assert all(name in output for name in _UNSORTED)


def test_an_unknown_tool_on_an_empty_registry_says_so():
    result = _run(ToolRegistry().execute(_call("nope")))

    assert result.is_error is True
    assert "no tools are registered" in result.output


# ---- traps 3 and 4: the exception boundary ------------------------------


def test_a_raising_tool_becomes_an_error_result():
    """Trap 3. The failure is the turn's answer for that call."""
    registry = ToolRegistry([Fake("boom", lambda _: _raising(ValueError("bad arg")))])

    result = _run(registry.execute(_call("boom", identifier="c3")))

    assert result.is_error is True
    assert result.tool_call_id == "c3"
    assert "ValueError" in result.output
    assert "bad arg" in result.output


def test_a_cancelled_tool_is_not_an_observation():
    """Trap 3, the half a literal translation gets wrong.

    The reference harness uses ``recover()``, which in Go catches
    everything. ``except BaseException`` here would turn an abandoned turn
    into a fabricated Observation and leave the cancellation unpropagated,
    so the scope that asked to stop never learns that it did.
    """
    registry = ToolRegistry(
        [Fake("gone", lambda _: _raising(asyncio.CancelledError()))]
    )

    try:
        _run(registry.execute(_call("gone")))
    except asyncio.CancelledError:
        return
    raise AssertionError("CancelledError was swallowed by the registry")


def test_a_keyboard_interrupt_passes_through():
    """Trap 4. ``except BaseException`` here is how Ctrl-C stops working."""
    registry = ToolRegistry([Fake("hang", lambda _: _raising(KeyboardInterrupt()))])

    try:
        _run(registry.execute(_call("hang")))
    except KeyboardInterrupt:
        return
    raise AssertionError("KeyboardInterrupt was swallowed by the registry")


def test_a_system_exit_passes_through():
    """Trap 4. A tool calling ``sys.exit`` means the process, not the turn."""
    registry = ToolRegistry([Fake("quit", lambda _: _raising(SystemExit(2)))])

    try:
        _run(registry.execute(_call("quit")))
    except SystemExit:
        return
    raise AssertionError("SystemExit was swallowed by the registry")


def test_an_ordinary_timeout_from_a_tool_is_still_a_tool_failure():
    """A tool's own expired budget is an ``Exception`` and belongs to the tool.

    The engine's per-call budget is applied outside this layer, so a
    ``TimeoutError`` arriving here is always the tool's own — an
    unreachable service, not an overrun of ours.
    """
    registry = ToolRegistry(
        [Fake("slow", lambda _: _raising(TimeoutError("read timeout=2")))]
    )

    result = _run(registry.execute(_call("slow")))

    assert result.is_error is True
    assert "read timeout=2" in result.output


# ---- trap 5: no policy reaches the model --------------------------------


def test_available_tools_leaks_no_policy_field_or_value():
    """Trap 5, checked on the payload that actually travels.

    ``test_base`` checks the two types share no field name; this checks
    the registry — which is the one object holding both a tool and its
    policy — does not helpfully fold one into the other on the way out.
    """
    loud = ToolPolicy(
        risk_level=RiskLevel.HIGH,
        approval_mode=ApprovalMode.DENY_UNLESS_TRUSTED,
        writes_workspace=True,
        tags=frozenset({"destructive"}),
    )
    registry = ToolRegistry()
    registry.register(Fake("danger"), loud)

    payload = json.dumps([dataclasses.asdict(d) for d in registry.available_tools()])

    leaked = [f.name for f in dataclasses.fields(ToolPolicy) if f.name in payload]
    assert not leaked, f"available_tools() leaked {leaked}"
    assert "deny_unless_trusted" not in payload
    assert "destructive" not in payload


# ---- trap 6: one tool, one name -----------------------------------------


def test_a_tool_that_disagrees_with_itself_about_its_name_is_refused():
    """Trap 6. Two sources for one identity fail in the least visible way.

    The registry would be keyed on ``tool.name`` while the model is shown
    ``definition().name``; every call then routes to nothing and the tool
    merely looks broken.
    """
    registry = ToolRegistry()

    try:
        registry.register(Fake("keyed_as", declared_name="shown_as"))
    except ToolNameMismatch as exc:
        assert "keyed_as" in str(exc) and "shown_as" in str(exc)
    else:
        raise AssertionError("a self-contradicting tool was registered")

    assert registry.names() == ()


def test_a_tool_with_no_name_is_refused():
    """An unnamed tool would answer for any call whose name is missing."""
    registry = ToolRegistry()

    try:
        registry.register(Fake(""))
    except ToolRegistrationError:
        pass
    else:
        raise AssertionError("an unnamed tool was registered")

    assert len(registry) == 0


# ---- trap 7: the incumbent survives a collision -------------------------


def test_a_duplicate_name_is_refused_and_the_first_tool_still_answers():
    """Trap 7. Asserting the raise alone would miss the half that matters.

    Last-writer-wins is the silent failure this refuses: an import-order
    change would otherwise hand the same name to a different tool with
    nothing to notice it.
    """
    first = Fake("dup", description="the incumbent")
    second = Fake("dup", description="the usurper")
    registry = ToolRegistry([first])
    registry.register(Fake("after"))

    try:
        registry.register(second, ToolPolicy(read_only=True))
    except ToolAlreadyRegistered as exc:
        assert "dup" in str(exc)
    else:
        raise AssertionError("a duplicate name was accepted")

    assert registry.get("dup") is first
    assert registry.available_tools()[0].description == "the incumbent"
    assert registry.names() == ("dup", "after")
    assert registry.policy_for("dup") == ToolPolicy()

    result = _run(registry.execute(_call("dup")))
    assert result.output == "dup ran"
    assert second.seen == []


def test_replace_is_the_way_to_overwrite_on_purpose():
    registry = ToolRegistry([Fake("dup", description="the incumbent")])

    registry.replace(Fake("dup", description="the replacement"))

    assert registry.available_tools()[0].description == "the replacement"


def test_unregistering_something_absent_is_an_error():
    try:
        ToolRegistry().unregister("ghost")
    except KeyError as exc:
        assert "ghost" in str(exc)
        return
    raise AssertionError("unregister() invented a tool to remove")


def test_replacing_something_absent_is_an_error_too():
    """Symmetry with ``unregister``, and for the same reason it has one.

    ``replace`` used to mount an unknown name silently, which made it a
    second ``register`` wearing a name that promises the opposite: both
    sentences of its contract — "over whatever holds its name" and
    "keeping its place" — are false when nothing holds the name. The
    silent version turns a typo, or a teardown that already ran, from
    "shadow the tool I mean" into "add a tool nobody reviewed", at the end
    of the order rather than in the position the caller thought they were
    preserving.

    The registry is asserted unchanged as well as the raise: a refusal
    that had already mutated the order would be the worse half of the
    same bug.
    """
    registry = ToolRegistry([Fake("alpha")])

    try:
        registry.replace(Fake("brand_new"))
    except KeyError as exc:
        assert "brand_new" in str(exc)
        assert registry.names() == ("alpha",)
        assert "brand_new" not in registry
        return
    raise AssertionError("replace() mounted a tool it was asked to replace")


# ---- Q5: where a policy comes from --------------------------------------

_AUTHOR = ToolPolicy(risk_level=RiskLevel.LOW, read_only=True)
_DEPLOYMENT = ToolPolicy(risk_level=RiskLevel.MEDIUM, approval_mode=ApprovalMode.AUTO)


def test_policy_row_one_the_deployment_outranks_the_author():
    """Plan 0028 §4 Q5, row one. Both sources present.

    The tool's own policy is what its code can do; the registered one is
    what this deployment is willing to let it do. The second is the one
    accepting the consequences, so it wins.
    """
    registry = ToolRegistry()
    registry.register(Fake("t", policy=_AUTHOR), _DEPLOYMENT)

    assert registry.policy_for("t") == _DEPLOYMENT


def test_policy_row_two_only_the_author_declared():
    registry = ToolRegistry([Fake("t", policy=_AUTHOR)])

    assert registry.policy_for("t") == _AUTHOR


def test_policy_row_three_only_the_deployment_declared():
    registry = ToolRegistry()
    registry.register(Fake("t"), _DEPLOYMENT)

    assert registry.policy_for("t") == _DEPLOYMENT


def test_policy_row_four_nobody_declared_anything():
    """Row four, the one that decides what forgetting costs."""
    registry = ToolRegistry([Fake("t")])

    assert registry.policy_for("t") == ToolPolicy()
    assert registry.policy_for("t").approval_mode is ApprovalMode.ASK
    assert registry.policy_for("t").risk_level is RiskLevel.HIGH


def test_a_policy_for_a_name_that_is_not_registered_grants_nothing():
    """Guessing generously about a tool nobody can find is the one answer
    with a blast radius."""
    assert ToolRegistry().policy_for("ghost") == ToolPolicy()


def test_a_policy_attribute_that_is_not_a_policy_is_ignored():
    """Duck typing stops at the security boundary.

    A ``policy`` attribute that happens to be a dict from some other
    framework must not be mistaken for a declaration; the conservative
    default is what an unreadable claim resolves to.
    """
    registry = ToolRegistry([Fake("t", policy={"risk_level": "low"})])

    assert registry.policy_for("t") == ToolPolicy()


def test_a_policy_survives_unregistration():
    registry = ToolRegistry()
    registry.register(Fake("t"), _DEPLOYMENT)
    registry.unregister("t")

    assert registry.policy_for("t") == ToolPolicy()


def test_the_resolved_policy_is_published_to_the_running_tool():
    """Q5's whole table reaching execution time, which it did not before.

    ``policy_for`` had no callers in production: the four rows above were
    an accessor nobody consulted, while a tool asked for approval with the
    policy *it* held — the author's. So a deployment's ``register(policy=)``
    changed what an operator could read and nothing about what ran. Here
    the tool reads what is in force from inside its own ``execute``, which
    is the only place the answer matters.
    """
    seen: list[Any] = []

    async def peek(_: str) -> str:
        seen.append(effective_policy())
        return "ok"

    registry = ToolRegistry()
    registry.register(Fake("t", peek, policy=_AUTHOR), _DEPLOYMENT)

    _run(registry.execute(_call("t")))

    assert seen == [_DEPLOYMENT]


def test_the_publication_is_scoped_to_one_call():
    """Bound around the call and unwound on the way out, failures included.

    A resolution left bound would be read by whatever ran next on this
    Task — the next tool of the same turn, or a surface between turns —
    and the tool that inherited it would ask, or fail to ask, with another
    tool's permissions. Both exits are checked because the ``except``
    branch is the one written by hand.
    """

    async def boom(_: str) -> str:
        raise RuntimeError("no")

    registry = ToolRegistry()
    registry.register(Fake("fine"), _DEPLOYMENT)
    registry.register(Fake("boom", boom), _DEPLOYMENT)

    assert effective_policy() is None
    _run(registry.execute(_call("fine")))
    assert effective_policy() is None
    assert _run(registry.execute(_call("boom"))).is_error is True
    assert effective_policy() is None


def test_an_unknown_name_publishes_nothing():
    """There is no tool to grant anything to, so nothing is in force.

    Publishing ``ToolPolicy()`` here would be harmless today and wrong in
    principle: the value would outlive the lookup that failed, and the
    next reader would be told a policy applies to a call that never ran.
    """
    assert _run(ToolRegistry().execute(_call("ghost"))).is_error is True
    assert effective_policy() is None


# ---- trap 12: the registry does not know what a request is --------------

_ASSEMBLY_LAYER_WORDS = ("request", "surface", "stage")


def test_no_public_method_knows_about_requests_surfaces_or_stages():
    """Trap 12. Guards against the registry growing back into what it was.

    Per-request gating, surface gating and per-stage subsets belong to
    the assembly layer, which knows who is asking. This layer only offers
    "the full set, in order" plus ``policy_for`` so the filter can be
    written elsewhere. The check is on the public surface, because that is
    where the temptation lands: one convenience parameter and the seam is
    gone.
    """
    offenders: list[str] = []
    for attribute, member in vars(ToolRegistry).items():
        if attribute.startswith("_") or not callable(member):
            continue
        if any(word in attribute for word in _ASSEMBLY_LAYER_WORDS):
            offenders.append(attribute)
            continue
        offenders += [
            f"{attribute}({parameter})"
            for parameter in inspect.signature(member).parameters
            if any(word in parameter for word in _ASSEMBLY_LAYER_WORDS)
        ]

    assert not offenders, f"the registry learned about {offenders}"


# ---- dispatch details ---------------------------------------------------


def test_the_raw_argument_string_reaches_the_tool_unparsed():
    """Byte-exact, because a decode and re-encode rewrites the payload.

    The bytes the model produced are what prompt-prefix caching and replay
    evidence are keyed on, and parsing them is the tool's business.

    **The payload has to be one a round trip would change**, which is the
    whole trick here. The first version of this test used
    ``'{"b": 1, "a": 2}'`` — already exactly what :func:`json.dumps`
    emits for that dict, since Python preserves key order and defaults to
    those separators — so a registry that decoded and re-encoded passed
    it. The mutation survived. The second assertion pins the property the
    payload is chosen for, so tidying it into canonical form cannot
    quietly restore that false pass.
    """
    tool = Fake("t")
    payload = '{"b":1,\n    "a": 2}'
    assert json.dumps(json.loads(payload)) != payload

    _run(ToolRegistry([tool]).execute(_call("t", payload)))

    assert tool.seen == [payload]


def test_a_result_mirrors_the_call_id_and_names_the_tool():
    result = _run(ToolRegistry([Fake("t")]).execute(_call("t", identifier="c9")))

    assert result.tool_call_id == "c9"
    assert result.name == "t"
    assert result.is_error is False
    assert result.output == "t ran"


def test_a_result_records_how_long_the_tool_took():
    """Plan 0028 §11: the per-call duration no vendor has a field for."""

    async def slow(_: str) -> str:
        await asyncio.sleep(0.01)
        return "done"

    result = _run(ToolRegistry([Fake("t", slow)]).execute(_call("t")))

    assert result.metadata["duration_s"] >= 0.01


def test_a_failing_tool_still_reports_its_duration():
    registry = ToolRegistry([Fake("t", lambda _: _raising(ValueError("x")))])

    result = _run(registry.execute(_call("t")))

    assert "duration_s" in result.metadata


def test_an_unknown_tool_reports_no_duration():
    """Nothing ran, so there is no elapsed time; a zero would read as one."""
    result = _run(ToolRegistry().execute(_call("ghost")))

    assert "duration_s" not in result.metadata


def test_membership_and_length_answer_without_running_anything():
    registry = _unsorted_registry()

    assert "alpha" in registry
    assert "ghost" not in registry
    assert len(registry) == 3
    assert registry.get("ghost") is None
