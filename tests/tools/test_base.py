"""Contract tests for ``omicsclaw.tools.base`` (plan 0028 §7, traps 5 and 6).

Two properties, and both are about a boundary rather than a behaviour.

The first is that :class:`~omicsclaw.tools.base.Tool` is satisfiable by
*shape*: the tool defined below imports :mod:`omicsclaw.schema` and
nothing else, which is the evidence that the Protocol costs an
implementer nothing and that a future adapter is not forced to inherit.

The second is that :class:`~omicsclaw.tools.base.ToolPolicy` and
:class:`~omicsclaw.schema.ToolDefinition` cannot be confused for one
another. Policy is what this machine will permit; a definition is what a
model is told. The tests below check the two share no field name and that
a fully-populated policy leaves no trace in a definition — because the
failure mode is silent, and by the time approval rules are visible in a
prompt the model has already been invited to argue with them.
"""

from __future__ import annotations

import dataclasses
import json

from omicsclaw.schema import ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, Tool, ToolPolicy

_LOUD_POLICY = ToolPolicy(
    risk_level=RiskLevel.MEDIUM,
    approval_mode=ApprovalMode.DENY_UNLESS_TRUSTED,
    read_only=True,
    concurrency_safe=True,
    writes_workspace=True,
    writes_config=True,
    touches_network=True,
    allowed_in_background=True,
    tags=frozenset({"destructive", "omics"}),
)
"""Every field set away from its default, so a leak has something to leak."""


class Echo:
    """A tool in a dozen lines that imports nothing from the layer tested.

    Structurally typed on purpose: it never subclasses
    :class:`~omicsclaw.tools.base.Tool`, which is how we know the Protocol
    is satisfied by shape.
    """

    policy = _LOUD_POLICY

    @property
    def name(self) -> str:
        return "echo"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Repeat the text back.",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        )

    async def execute(self, arguments: str) -> str:
        return arguments


class NoExecute:
    @property
    def name(self) -> str:
        return "half"

    def definition(self) -> ToolDefinition:
        return ToolDefinition(name="half", description="")


class NoDefinition:
    name = "half"

    async def execute(self, arguments: str) -> str:
        return ""


# ---- the Protocol is satisfied by shape ---------------------------------


def test_a_plain_class_is_a_tool_without_inheriting_anything():
    assert isinstance(Echo(), Tool)


def test_a_class_with_no_execute_is_not_a_tool():
    assert not isinstance(NoExecute(), Tool)


def test_a_class_with_no_definition_is_not_a_tool():
    assert not isinstance(NoDefinition(), Tool)


# ---- trap 5: policy has no route into a definition ----------------------


def test_a_definition_and_a_policy_share_no_field_name():
    """The structural half of trap 5, checked where a leak would start.

    ``ToolDefinition`` has three fields and none of them is a policy
    field. If that ever stops being true — a ``risk_level`` added
    "just for the UI" — a policy value acquires a legal place to sit in
    the payload sent to a model, and every downstream test that inspects
    behaviour would still pass.
    """
    definition_fields = {f.name for f in dataclasses.fields(ToolDefinition)}
    policy_fields = {f.name for f in dataclasses.fields(ToolPolicy)}

    assert definition_fields == {"name", "description", "input_schema"}
    assert definition_fields & policy_fields == set()


def test_a_serialized_definition_mentions_no_policy_field_or_value():
    """The behavioural half: a tool carrying a loud policy stays quiet.

    Driven by :func:`dataclasses.fields` rather than a hand-written list,
    so a field added to ``ToolPolicy`` is covered the day it is added
    rather than the day someone remembers this test exists.
    """
    payload = json.dumps(dataclasses.asdict(Echo().definition()))

    leaked = [f.name for f in dataclasses.fields(ToolPolicy) if f.name in payload]
    assert not leaked, f"definition() leaked policy fields {leaked}"

    values = [str(v) for v in (RiskLevel.MEDIUM, ApprovalMode.DENY_UNLESS_TRUSTED)]
    values += sorted(_LOUD_POLICY.tags)
    assert not [v for v in values if v in payload]


# ---- the defaults of a policy nobody wrote ------------------------------


def test_a_blank_policy_grants_nothing():
    """Plan 0028 §4 Q5, row four: declaring nothing must cost, not pay.

    Every permission field resolves to its guarded value and every claim
    field to the absence of a claim, so a tool whose author never thought
    about policy cannot acquire privilege by silence. Plan 0028 §2
    sketches ``LOW`` / ``AUTO`` / ``concurrency_safe=True`` instead, which
    is the most *convenient* set and would make Q5 unenforceable; Q5 is
    the requirement, so it wins.
    """
    blank = ToolPolicy()

    assert blank.risk_level is RiskLevel.HIGH
    assert blank.approval_mode is ApprovalMode.ASK
    assert blank.concurrency_safe is False
    assert blank.allowed_in_background is False
    assert blank.read_only is False
    assert blank.writes_workspace is False
    assert blank.writes_config is False
    assert blank.touches_network is False
    assert blank.prompts_for_itself is False
    assert blank.tags == frozenset()


def test_the_prompts_for_itself_default_is_the_one_that_costs():
    """The ninth field, classified: a **claim**, and the asymmetric one.

    Every other claim is read by something deciding whether to *grant*, so
    the absence of the claim withholds. This one is read by
    :class:`omicsclaw.permission.GatedTool` deciding whether to *stand back*,
    so the absence of the claim makes the gate ask — the guarded direction
    for a field whose ``True`` means "somebody else will handle consent".

    The alternative was inferring it from ``approval_mode`` being ``ASK``,
    which a test in ``tests/permission/test_gate.py`` shows is unsound: a
    tool that never calls ``require_approval`` runs whatever its mode says.
    """
    assert ToolPolicy().prompts_for_itself is False
    assert ToolPolicy(approval_mode=ApprovalMode.ASK).prompts_for_itself is False


def test_the_policy_fields_are_exactly_the_ones_classified_above():
    """A forcing function, not an inventory.

    The previous test can only assert conservative defaults for fields it
    knows about. Pinning the field set means adding a tenth field breaks
    this test, and whoever adds it has to decide in public whether it is a
    permission or a claim.

    ``prompts_for_itself`` is the ninth, added for the permission layer and
    classified as a claim — see the test above for which way its default
    points and why that is the guarded direction.
    """
    assert [f.name for f in dataclasses.fields(ToolPolicy)] == [
        "risk_level",
        "approval_mode",
        "read_only",
        "concurrency_safe",
        "writes_workspace",
        "writes_config",
        "touches_network",
        "prompts_for_itself",
        "allowed_in_background",
        "tags",
    ]


def test_the_enum_values_are_the_strings_already_in_use():
    """Wire values, not display names.

    These strings are what the existing tool layer writes into approval
    records, so a rename here would be a silent data migration. Spelled
    out literally rather than imported from ``omicsclaw.runtime.tools``,
    which this layer may not reach.
    """
    assert [str(level) for level in RiskLevel] == ["low", "medium", "high"]
    assert [str(mode) for mode in ApprovalMode] == [
        "auto",
        "ask",
        "deny_unless_trusted",
    ]


def test_a_policy_is_frozen_and_hashable():
    """Frozen so a registry's copy cannot be edited through the caller's."""
    policy = ToolPolicy()

    assert hash(policy) == hash(ToolPolicy())
    assert policy == ToolPolicy()
    try:
        policy.read_only = True  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ToolPolicy is mutable")
