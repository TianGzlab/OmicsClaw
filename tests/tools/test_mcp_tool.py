"""Contract tests for ``omicsclaw.tools.mcp_tool`` (plan 0028, task B).

Plan 0028 trap 10, restated after the fact-check that changed it: there is
**no existing naming convention in this repository to match**. ``mcp__``
appears once in every ``*.py`` here, at
``omicsclaw/runtime/tools/orchestration.py:193``, and that occurrence
reads a name rather than producing one. So these tests do not verify a
port; they pin a rule this step invents, and the one test that looks
outward —
:func:`test_the_name_survives_the_split_the_one_existing_reader_performs` —
re-performs that single reader's ``split("__", 2)`` rather than trusting a
description of it.

The MCP SDK is not installed and is not needed: an :class:`MCPTool` is
built from four plain values and a callable, so every case here runs off a
local fake and would run identically on a machine with no MCP client at
all.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.schema import ToolCall
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalMode,
    ApprovalRequest,
    MCPTool,
    RiskLevel,
    ToolAlreadyRegistered,
    ToolPolicy,
    ToolRegistry,
    mcp_tool_name,
    sanitize_mcp_name,
    use_tool_context,
)
from omicsclaw.tools.mcp_tool import MAX_TOOL_NAME_LENGTH

_T = TypeVar("_T")


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, 5.0))


def _run_approved(main: Coroutine[Any, Any, _T]) -> _T:
    """Run *main* with a human who approves everything.

    For the tests about what a call *does*; the tests about whether it may
    happen at all are in the approval section below.
    """
    with use_tool_context(approval=lambda request: True):
        return _run(main)


class FakeServer:
    """One MCP tool's far end: records the payload, answers with a string."""

    def __init__(self, answer: Any = "server said so") -> None:
        self.seen: list[str] = []
        self._answer = answer

    async def __call__(self, arguments: str) -> Any:
        self.seen.append(arguments)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


_NAME = "mcp__context7__resolve_library_id"


def _tool(
    server: str = "context7",
    tool: str = "resolve-library-id",
    **kwargs: Any,
) -> MCPTool:
    kwargs.setdefault("caller", FakeServer())
    return MCPTool(server, tool, **kwargs)


def _call(arguments: str = "{}") -> ToolCall:
    return ToolCall(id="c1", name=_NAME, arguments=arguments)


# ---- the naming rule this step invents -----------------------------------


def test_a_tool_is_named_for_its_server_and_its_tool():
    assert _tool().name == _NAME


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("context7", "context7"),
        ("resolve-library-id", "resolve_library_id"),
        ("a.b/c d", "a_b_c_d"),
        ("read:file", "read_file"),
        ("_leading_and_trailing_", "leading_and_trailing"),
        ("get__thing", "get_thing"),
        ("UPPER_and_9", "UPPER_and_9"),
    ],
)
def test_sanitizing_keeps_letters_digits_and_single_underscores(
    raw: str, expected: str
):
    assert sanitize_mcp_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["a--b", "a..b", "a b", "get__thing", "a-_-b", "···x···y···"],
)
def test_no_sanitized_name_contains_a_double_underscore(raw: str):
    """The invariant the whole naming scheme rests on.

    ``__`` is the segment separator, so a segment that could contain one
    would make the composed name ambiguous. Collapsing runs is what buys
    that, and it is the first of the three departures from the reference
    harness's sanitiser.
    """
    assert "__" not in sanitize_mcp_name(raw)


def test_the_name_survives_the_split_the_one_existing_reader_performs():
    """Forward compatibility with ``orchestration.py:193``, performed not quoted.

    That line tests ``startswith("mcp__")`` and then splits with
    ``maxsplit=2`` to attribute a call to a server. The reference
    harness's sanitiser would hand it ``mcp__my__server__do__it`` for a
    server called ``my--server``, and it would report the server as
    ``my``: a call attributed to a server that does not exist, in a
    telemetry field nobody would think to check.
    """
    name = mcp_tool_name("my--server", "do--it-now")

    assert name.startswith("mcp__")
    assert name.split("__", 2) == ["mcp", "my_server", "do_it_now"]


def test_a_non_ascii_name_does_not_reach_a_vendor_intact():
    """The second departure: the harness is Unicode-aware, and must not be here.

    Both vendors this project targets constrain a function name to
    ``[A-Za-z0-9_-]``, and a rejected name fails the whole request rather
    than the one tool. The readable original is not lost — it stays on the
    tool and in the description.
    """
    tool = _tool("生信服务", "分析")

    assert tool.name.isascii()
    assert tool.server == "生信服务"
    assert tool.tool == "分析"
    assert "生信服务" in tool.definition().description


def test_two_unrenderable_names_do_not_collide_on_one_placeholder():
    """The third departure: an empty sanitisation must still be distinct.

    A server whose tools are all non-ASCII would otherwise register one
    tool and have the registry reject the rest as duplicates of a name
    nobody chose.
    """
    first = _tool("srv", "分析")
    second = _tool("srv", "注释")

    assert first.name != second.name
    assert "unnamed" in first.name


def test_two_names_that_differ_only_by_a_separator_collide():
    """The third kind of loss, pinned as a known cost rather than fixed.

    Truncation and emptiness are fingerprinted; **substitution is not**,
    so ``get-thing`` and ``get_thing`` from one server sanitise to one
    name and :meth:`ToolRegistry.register` refuses the second — a server's
    tool disappearing with an error naming a key nobody chose, which is
    the exact failure :func:`_capped` pays a digest to avoid. Asserted
    through the registry rather than only on the strings, because the
    string equality is a curiosity and the refused mount is the damage.

    Left as it is, and the reasoning is on
    :func:`~omicsclaw.tools.mcp_tool.sanitize_mcp_name` in full. In
    short: sanitising is idempotent, so *every* lossy original collides
    with its own sanitised form, and no function of one name can tell the
    colliding ones apart — the digest would have to be paid on every name
    containing a hyphen. That is the common case, where the two
    fingerprinted losses are rare ones, and it would also turn the server
    segment ``omicsclaw/runtime/tools/orchestration.py:193`` attributes
    calls by into noise. Collision resolution wants to see the whole
    server's tool list at once, and the layer that does is plan 0028 §5's
    assembly layer, which does not exist yet.

    This test is what a later step changes when it does.
    """
    first = _tool("srv", "get-thing")
    second = _tool("srv", "get_thing")

    assert first.name == second.name == "mcp__srv__get_thing"
    assert first.tool != second.tool, "the server's own names stay distinct"

    registry = ToolRegistry([first])
    with pytest.raises(ToolAlreadyRegistered) as refused:
        registry.register(second)

    assert "mcp__srv__get_thing" in str(refused.value)
    assert registry.get("mcp__srv__get_thing") is first


@pytest.mark.parametrize(
    ("server", "tool"),
    [("s" * 80, "t"), ("s", "t" * 80), ("s" * 60, "t" * 60), ("srv", "tool")],
)
def test_a_name_never_exceeds_the_narrowest_vendor_limit(server: str, tool: str):
    assert len(mcp_tool_name(server, tool)) <= MAX_TOOL_NAME_LENGTH


def test_shortening_keeps_two_similar_long_names_apart():
    """A plain truncation would make the second tool a duplicate of the first.

    The registry refuses a duplicate name, so the failure mode is one of a
    server's tools vanishing with an error naming a truncation nobody
    chose — which is why the shortened form carries a digest of the whole
    segment rather than just its beginning.
    """
    stem = "search_pubmed_by_author_with_a_very_long_and_shared_stem"
    first = mcp_tool_name("srv", f"{stem}_alpha")
    second = mcp_tool_name("srv", f"{stem}_beta")

    assert first != second
    assert first.split("__", 2) == ["mcp", "srv", first[len("mcp__srv__") :]]
    assert first[:40] == second[:40], "the shared stem is genuinely shared"


def test_shortening_spends_the_budget_on_the_server_last():
    """``orchestration.py`` attributes a call by the server segment."""
    name = mcp_tool_name("context7", "t" * 90)

    assert name.split("__", 2)[1] == "context7"


def test_an_impossible_length_budget_is_refused_rather_than_silently_mangled():
    with pytest.raises(ValueError):
        mcp_tool_name("srv", "tool", max_length=6)


# ---- what the model is told ----------------------------------------------


def test_the_description_says_where_the_tool_comes_from():
    tool = _tool(description="Resolve a library name to an ID.")

    assert tool.definition().description == (
        "[MCP:context7] Resolve a library name to an ID."
    )


def test_a_server_that_wrote_no_description_still_gets_the_tag():
    assert _tool(description="   ").definition().description == "[MCP:context7]"


def test_a_schema_mapping_is_passed_through_unchanged():
    """The server author knows what the tool takes; this process does not."""
    schema = {
        "type": "object",
        "properties": {"libraryName": {"type": "string"}},
        "required": ["libraryName"],
    }

    assert _tool(input_schema=schema).definition().input_schema == schema


def test_a_json_schema_string_is_decoded():
    raw = '{"type": "object", "properties": {"q": {"type": "string"}}}'

    assert _tool(input_schema=raw).definition().input_schema == json.loads(raw)


@pytest.mark.parametrize("raw", [None, "", "   ", {}, b""])
def test_an_absent_schema_becomes_an_empty_object_schema(raw: Any):
    """A function with no ``parameters`` at all is rejected by the vendors."""
    tool = _tool(input_schema=raw)

    assert tool.definition().input_schema == {"type": "object", "properties": {}}
    assert tool.schema_error == ""


def test_two_tools_that_fell_back_do_not_share_one_schema():
    """One server's repair must not appear on another server's tool."""
    first = _tool("a", "x", input_schema="not json")
    second = _tool("b", "y", input_schema=None)

    first.definition().input_schema["properties"]["leaked"] = {"type": "string"}

    assert second.definition().input_schema == {"type": "object", "properties": {}}


@pytest.mark.parametrize(
    ("raw", "complaint"),
    [
        ('{"type": "object"', "not decodable"),
        ("[1, 2]", "not a JSON object"),
        ("7", "not a JSON object"),
        (object(), "not a schema"),
    ],
)
def test_an_unusable_schema_does_not_stop_the_tool_being_registered(
    raw: Any, complaint: str
):
    """One malformed tool must not take a server's working tools down with it.

    ``schema_error`` is the addition over the reference harness, which
    falls back silently. Without it "this tool takes no arguments" and
    "this tool's description of its arguments was garbage" are the same
    observable state, and the model is confidently told the first.
    """
    tool = _tool(input_schema=raw)
    registry = ToolRegistry([tool])

    assert registry.get(tool.name) is tool
    assert tool.definition().input_schema == {"type": "object", "properties": {}}
    assert complaint in tool.schema_error


# ---- calling it ----------------------------------------------------------


def test_the_raw_payload_reaches_the_server_unaltered():
    """Byte-exact, with a payload a decode-and-re-encode would rewrite.

    The whitespace and the missing space after the first colon are the
    test: ``json.dumps(json.loads(payload))`` produces a different string,
    so an implementation that parsed on the way out fails here. A payload
    that is already in canonical form would let that implementation pass —
    the first assertion is what stops this test from being tidied into
    uselessness.
    """
    server = FakeServer()
    payload = '{"b":1,\n    "a": 2}'
    assert json.dumps(json.loads(payload)) != payload
    registry = ToolRegistry([_tool(caller=server)])

    _run_approved(registry.execute(_call(payload)))

    assert server.seen == [payload]


def test_a_string_answer_is_returned_as_it_stands():
    registry = ToolRegistry([_tool(caller=FakeServer("42 results"))])

    result = _run_approved(registry.execute(_call()))

    assert result.is_error is False
    assert result.output == "42 results"


def test_a_structured_answer_becomes_json_the_model_can_read():
    registry = ToolRegistry([_tool(caller=FakeServer({"hits": [1, 2]}))])

    assert _run_approved(registry.execute(_call())).output == '{"hits": [1, 2]}'


def test_a_synchronous_caller_is_accepted():
    registry = ToolRegistry([_tool(caller=lambda arguments: f"got {arguments}")])

    assert _run_approved(registry.execute(_call("{}"))).output == "got {}"


def test_a_transport_failure_becomes_an_error_result_carrying_its_message():
    """"Connection refused" and "unknown tool" need different fixes."""
    broken = FakeServer(ConnectionError("connection refused"))
    registry = ToolRegistry([_tool(caller=broken)])

    result = _run_approved(registry.execute(_call()))

    assert result.is_error is True
    assert "connection refused" in result.output


def test_arguments_are_not_validated_here():
    """The server enforces its own schema; enforcing a copy invents refusals.

    A mismatch between the schema this process cached and the one the
    server actually applies would produce a rejection citing a rule the
    model was never shown.
    """
    server = FakeServer()
    tool = _tool(
        caller=server,
        input_schema={"type": "object", "required": ["libraryName"]},
    )

    _run_approved(ToolRegistry([tool]).execute(_call("{}")))

    assert server.seen == ["{}"]


# ---- approval ------------------------------------------------------------
#
# The default policy is ASK, and until the MCP layer was wired in nothing
# enforced it: ``execute`` called the server directly, so the policy read
# as enforced in ``policy_for`` while every call self-approved. These pin
# the effect, including in the tightening direction.


def test_with_no_approval_channel_the_server_is_never_called():
    server = FakeServer()
    registry = ToolRegistry([_tool(caller=server)])

    result = _run(registry.execute(_call()))

    assert result.is_error is True
    assert "ApprovalUnavailable" in result.output
    assert server.seen == []


def test_the_human_is_shown_the_whole_payload_before_it_leaves():
    """An HTTP server sends the arguments off this machine; the prompt is
    where a person sees what is about to go."""
    asked: list[ApprovalRequest] = []
    server = FakeServer()
    payload = '{"sample": "HG00123"}'

    def human(request: ApprovalRequest) -> bool:
        asked.append(request)
        return True

    with use_tool_context(approval=human):
        _run(ToolRegistry([_tool(caller=server)]).execute(_call(payload)))

    (request,) = asked
    assert request.tool_name == _NAME
    assert request.arguments == payload
    assert "context7" in request.reason and "resolve-library-id" in request.reason
    assert server.seen == [payload]


@pytest.mark.parametrize("payload", ["[1]", "not json", '"x"'])
def test_a_payload_that_is_not_an_object_is_refused_before_anyone_is_asked(
    payload: str,
):
    """A human should not be asked to approve a call that cannot run."""
    asked: list[ApprovalRequest] = []
    server = FakeServer()

    with use_tool_context(approval=lambda request: asked.append(request) or True):
        result = _run(ToolRegistry([_tool(caller=server)]).execute(_call(payload)))

    assert result.is_error and "ToolArgumentError" in result.output
    assert asked == []
    assert server.seen == []


def test_the_prompt_names_the_origin_when_one_is_given():
    asked: list[ApprovalRequest] = []

    with use_tool_context(approval=lambda request: asked.append(request) or True):
        _run(
            ToolRegistry([_tool(origin="remote https://x/mcp")]).execute(_call())
        )

    assert "via remote https://x/mcp" in asked[0].reason


def test_a_refusal_never_reaches_the_server():
    server = FakeServer()

    with use_tool_context(
        approval=lambda request: ApprovalDecision(approved=False, reason="no")
    ):
        result = _run(ToolRegistry([_tool(caller=server)]).execute(_call()))

    assert result.is_error is True
    assert "not approved" in result.output
    assert server.seen == []


def test_a_trusting_deployment_can_let_it_run_unasked():
    server = FakeServer()
    registry = ToolRegistry()
    registry.register(
        _tool(caller=server), ToolPolicy(approval_mode=ApprovalMode.AUTO)
    )

    result = _run(registry.execute(_call()))

    assert result.is_error is False
    assert server.seen == ["{}"]


def test_a_deployment_tightening_an_auto_tool_to_ask_is_obeyed():
    """The direction that matters: the author said AUTO, the deployment
    said ASK, and no channel is bound — so nothing may run."""
    server = FakeServer()
    tool = _tool(caller=server, policy=ToolPolicy(approval_mode=ApprovalMode.AUTO))
    registry = ToolRegistry()
    registry.register(tool, ToolPolicy(approval_mode=ApprovalMode.ASK))

    result = _run(registry.execute(_call()))

    assert result.is_error is True
    assert server.seen == []


# ---- policy --------------------------------------------------------------


def test_an_mcp_tool_defaults_to_the_guarded_policy():
    """Third-party code, neither written nor reviewed here."""
    policy = ToolRegistry([_tool()]).policy_for(_NAME)

    assert policy.approval_mode is ApprovalMode.ASK
    assert policy.risk_level is RiskLevel.HIGH
    assert policy.concurrency_safe is False
    assert policy.allowed_in_background is False


def test_the_default_policy_tags_the_server_for_the_assembly_layer():
    """Where surface gating lands: the registry offers labels, not decisions."""
    assert _tool().policy.tags == frozenset({"mcp", "mcp:context7"})


def test_the_default_policy_asserts_no_effect_it_cannot_know():
    """Stdio or HTTPS is captured inside ``caller`` and never reaches here.

    ``ToolPolicy`` is explicit that a gate must not grant anything on the
    strength of a ``False`` nobody wrote, so leaving these unasserted is
    the honest state rather than a gap — and ``approval_mode`` is the
    authoritative field either way.
    """
    policy = _tool().policy

    assert policy.touches_network is False
    assert policy.read_only is False
    assert policy.writes_workspace is False


def test_a_deployment_policy_outranks_the_default():
    trusted = ToolPolicy(approval_mode=ApprovalMode.AUTO, read_only=True)
    tool = _tool(policy=trusted)

    assert tool.policy is trusted
    assert ToolRegistry([tool]).policy_for(tool.name) is trusted


def test_no_policy_field_reaches_the_definition():
    """Plan 0028 trap 5, re-checked on the adapter most likely to leak.

    An MCP tool's definition is assembled from a third party's data, so
    this is the one place a stray field could arrive from outside.
    """
    definition = _tool().definition()
    serialized = json.dumps(
        {
            "name": definition.name,
            "description": definition.description,
            "input_schema": definition.input_schema,
        }
    )

    for field in (
        "risk_level",
        "approval_mode",
        "read_only",
        "concurrency_safe",
        "writes_workspace",
        "writes_config",
        "touches_network",
        "allowed_in_background",
        "tags",
        "mcp:context7",
    ):
        assert field not in serialized


def test_the_registry_accepts_an_mcp_tool_without_a_name_mismatch():
    """Two sources for one identity, agreeing — checked, not assumed."""
    tool = _tool()

    assert tool.name == tool.definition().name
    assert ToolRegistry([tool]).names() == (tool.name,)
