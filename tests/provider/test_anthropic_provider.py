"""The Anthropic adapter translates faithfully in both directions.

Plan 0026 §5 traps 5-9 and §6. Nothing here touches the network, and
nothing here requires the ``anthropic`` package to be installed: the
conversions are plain functions over plain data, and the one function
that needs the SDK (``_build_async_client``) is replaced by a fake.

Async tests are driven with :func:`asyncio.run` rather than an async
plugin, because ``pytest-asyncio`` is declared in ``pyproject.toml`` but
is not present in every environment this suite has to pass in.
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

from omicsclaw.provider import (
    LLMProvider,
    ProviderConfig,
    ProviderError,
    resolve_config,
)
from omicsclaw.provider import anthropic_provider as ap
from omicsclaw.provider.anthropic_provider import (
    MIN_THINKING_BUDGET_TOKENS,
    AnthropicProvider,
    ThinkingSupport,
    clamp_thinking_budget,
    decode_arguments,
    decode_content,
    decode_usage,
    effort_for_budget,
    encode_conversation,
    encode_thinking,
    encode_tools,
    thinking_support_for_model,
)
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

# --------------------------------------------------------------------------
# fakes — the SDK's shape, none of the SDK
# --------------------------------------------------------------------------


class FakeStream:
    """An ``AsyncStream`` stand-in that records whether it was closed."""

    def __init__(self, events):
        self._events = list(events)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        event = self._events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event

    async def close(self):
        self.closed = True


class FakeMessages:
    def __init__(self, response=None, stream=None, error=None):
        self.response = response
        self.stream = stream
        self.error = error
        self.calls = []

    async def create(self, **params):
        self.calls.append(params)
        if self.error is not None:
            raise self.error
        return self.stream if params.get("stream") else self.response


class FakeClient:
    def __init__(self, response=None, stream=None, error=None):
        self.messages = FakeMessages(response=response, stream=stream, error=error)


def refuse_to_build(_config):
    raise AssertionError("a test reached for the real anthropic SDK")


def make_provider(monkeypatch, client=None, **overrides) -> AnthropicProvider:
    """A provider wired to ``client`` instead of to the vendor SDK.

    The client cache is seeded directly and the builder is replaced with
    a tripwire, so two providers can coexist in one test and no test can
    silently fall through to the real package.
    """
    monkeypatch.setattr(ap, "_build_async_client", refuse_to_build)
    provider = AnthropicProvider(resolve_config("anthropic", env={}, **overrides))
    provider._cached_client = client
    return provider


def sent_params(provider: AnthropicProvider) -> dict:
    return provider._client().messages.calls[-1]


def event(kind: str, **fields) -> dict:
    """A raw stream event as the wire carries it."""
    return {"type": kind, **fields}


# --------------------------------------------------------------------------
# outbound conversion — the structural work
# --------------------------------------------------------------------------


def test_a_system_message_is_lifted_out_of_the_message_list():
    system, turns = encode_conversation(
        [Message.system("be terse"), Message.user("hello")]
    )

    assert system == "be terse"
    assert turns == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]


def test_several_system_messages_are_joined_into_one_prompt():
    system, _ = encode_conversation(
        [Message.system("base persona"), Message.system("task rules")]
    )

    assert system == "base persona\n\ntask rules"


def test_an_empty_system_message_contributes_nothing_to_the_prompt():
    system, turns = encode_conversation([Message.system(""), Message.user("hi")])

    assert system == ""
    assert len(turns) == 1


def test_an_assistant_tool_call_becomes_a_tool_use_block():
    message = Message.assistant(
        content="checking",
        tool_calls=(ToolCall(id="call_1", name="run_skill", arguments='{"n": 1}'),),
    )

    _, turns = encode_conversation([message])

    assert turns == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "checking"},
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "run_skill",
                    "input": {"n": 1},
                },
            ],
        }
    ]


def test_an_assistant_turn_with_neither_text_nor_tools_is_dropped():
    """Anthropic rejects a message whose content list is empty."""
    _, turns = encode_conversation([Message.user("hi"), Message.assistant("")])

    assert [turn["role"] for turn in turns] == ["user"]


def test_assistant_reasoning_is_not_replayed_as_an_unsigned_thinking_block():
    """A thinking block without its vendor signature is a 400 on the next turn.

    The schema has nowhere to keep the signature, so the adapter drops
    the Thought outbound rather than making every follow-up fail.
    """
    message = Message.assistant("answer", reasoning_content="long deliberation")

    _, turns = encode_conversation([message])

    blocks = turns[0]["content"]
    assert blocks == [{"type": "text", "text": "answer"}]
    assert all(block["type"] != "thinking" for block in blocks)


# ---- trap 5 --------------------------------------------------------------


def test_consecutive_tool_results_become_a_single_user_turn():
    """Trap 5: one user turn per tool result is rejected by the API.

    If this regresses, a turn that requested tools in parallel produces
    N user messages and the request fails outright — or, where it is
    tolerated, trains the model out of parallel tool use.
    """
    messages = [
        Message.user("do three things"),
        Message.assistant(
            tool_calls=(
                ToolCall(id="a", name="one", arguments="{}"),
                ToolCall(id="b", name="two", arguments="{}"),
                ToolCall(id="c", name="three", arguments="{}"),
            )
        ),
        ToolResult(tool_call_id="a", name="one", output="1").to_message(),
        ToolResult(tool_call_id="b", name="two", output="2").to_message(),
        ToolResult(tool_call_id="c", name="three", output="3").to_message(),
    ]

    _, turns = encode_conversation(messages)

    assert [turn["role"] for turn in turns] == ["user", "assistant", "user"]
    batched = turns[-1]["content"]
    assert [block["type"] for block in batched] == ["tool_result"] * 3
    assert [block["tool_use_id"] for block in batched] == ["a", "b", "c"]


def test_a_batch_of_tool_results_is_flushed_before_the_next_turn():
    """Trap 5: batching must not swallow ordering."""
    messages = [
        ToolResult(tool_call_id="a", output="1").to_message(),
        Message.user("and now this"),
        ToolResult(tool_call_id="b", output="2").to_message(),
    ]

    _, turns = encode_conversation(messages)

    assert [block["type"] for turn in turns for block in turn["content"]] == [
        "tool_result",
        "text",
        "tool_result",
    ]


# ---- trap 6 --------------------------------------------------------------


def test_tool_call_arguments_are_decoded_from_json_text_into_an_object():
    """Trap 6: ``tool_use.input`` is an object, not the schema's raw text."""
    call = ToolCall(id="x", name="t", arguments='{"path": "/tmp", "depth": 2}')

    assert decode_arguments(call) == {"path": "/tmp", "depth": 2}


def test_malformed_tool_arguments_raise_instead_of_becoming_an_empty_object():
    """Trap 6: silently sending ``{}`` rewrites what the model asked for.

    If this regresses, a truncated argument payload is replayed to the
    vendor as a no-argument call and the run continues on a request
    nobody made.
    """
    call = ToolCall(id="x", name="run_skill", arguments='{"path": "/tm')

    with pytest.raises(ProviderError) as caught:
        decode_arguments(call)

    assert "run_skill" in str(caught.value)
    assert caught.value.provider == "anthropic"
    assert caught.value.status_code is None


def test_tool_arguments_that_decode_to_a_non_object_are_rejected():
    """Trap 6: ``tool_use.input`` must be a JSON object, not a scalar."""
    with pytest.raises(ProviderError, match="must be an object"):
        decode_arguments(ToolCall(id="x", name="t", arguments="[1, 2]"))


def test_a_malformed_tool_call_fails_the_whole_conversion():
    with pytest.raises(ProviderError):
        encode_conversation(
            [Message.assistant(tool_calls=(ToolCall(id="x", name="t", arguments="{"),))]
        )


# ---- trap 8 --------------------------------------------------------------


def test_a_failed_tool_result_carries_the_structured_is_error_flag():
    """Trap 8: the flag is what strengthens the model's self-correction.

    If this regresses, the model has to infer failure from an error
    prefix in the text, which it does less reliably.
    """
    failure = ToolResult(
        tool_call_id="a", name="run_skill", output="exit 2", is_error=True
    ).to_message()

    _, turns = encode_conversation([failure])

    assert turns[0]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "a",
        "content": "exit 2",
        "is_error": True,
    }


def test_a_successful_tool_result_carries_is_error_false():
    """Trap 8: the flag is always present, so its absence is never ambiguous."""
    ok = ToolResult(tool_call_id="a", output="done").to_message()

    _, turns = encode_conversation([ok])

    assert turns[0]["content"][0]["is_error"] is False


# ---- tools ---------------------------------------------------------------


def test_tool_definitions_forward_the_whole_json_schema():
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    assert encode_tools([ToolDefinition("read", "Read a file", schema)]) == [
        {"name": "read", "description": "Read a file", "input_schema": schema}
    ]


def test_a_tool_with_no_schema_still_gets_a_valid_object_schema():
    """Anthropic rejects an ``input_schema`` that is not an object schema."""
    encoded = encode_tools([ToolDefinition("ping", "Ping")])

    assert encoded[0]["input_schema"] == {"type": "object", "properties": {}}


def test_no_tools_encodes_to_an_empty_list():
    assert encode_tools(None) == []
    assert encode_tools([]) == []


# --------------------------------------------------------------------------
# inbound conversion
# --------------------------------------------------------------------------


def test_text_blocks_are_concatenated_into_the_message_content():
    message = decode_content(
        [{"type": "text", "text": "one "}, {"type": "text", "text": "two"}]
    )

    assert message.role == Role.ASSISTANT
    assert message.content == "one two"


def test_thinking_blocks_become_reasoning_content():
    message = decode_content(
        [
            {"type": "thinking", "thinking": "let me check"},
            {"type": "text", "text": "the answer"},
        ]
    )

    assert message.reasoning_content == "let me check"
    assert message.content == "the answer"


def test_redacted_thinking_blocks_are_dropped():
    """Their payload is ciphertext; ``reasoning_content`` means the Thought."""
    message = decode_content(
        [
            {"type": "redacted_thinking", "data": "EncrYpt3d"},
            {"type": "text", "text": "x"},
        ]
    )

    assert message.reasoning_content == ""
    assert message.content == "x"


def test_tool_use_blocks_become_tool_calls_holding_raw_json_text():
    message = decode_content(
        [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "run_skill",
                "input": {"skill": "sc-de"},
            }
        ]
    )

    assert message.is_action
    call = message.tool_calls[0]
    assert (call.id, call.name) == ("toolu_1", "run_skill")
    assert json.loads(call.arguments) == {"skill": "sc-de"}


def test_a_recorded_response_decodes_thinking_text_and_tools_together():
    """The inbound direction, asserted against one whole vendor payload."""
    message = decode_content(
        [
            {"type": "thinking", "thinking": "plan it"},
            {"type": "text", "text": "running now"},
            {"type": "tool_use", "id": "toolu_9", "name": "qc", "input": {}},
        ]
    )

    assert message.reasoning_content == "plan it"
    assert message.content == "running now"
    assert message.tool_calls == (ToolCall(id="toolu_9", name="qc", arguments="{}"),)


def test_a_round_trip_through_both_directions_preserves_a_tool_call():
    original = Message.assistant(
        "text", tool_calls=(ToolCall(id="t1", name="n", arguments='{"a": 1}'),)
    )

    _, turns = encode_conversation([original])
    blocks = turns[0]["content"]
    restored = decode_content(blocks)

    assert restored.content == original.content
    assert restored.tool_calls == original.tool_calls


# ---- trap 7 --------------------------------------------------------------


def test_cache_reads_are_added_back_into_the_total_input_count():
    """Trap 7: Anthropic's ``input_tokens`` excludes the cached prefix.

    If this regresses, an agent run under prompt caching reports a
    fraction of the input it actually sent — on a long run, most of the
    conversation simply vanishes from the accounting.
    """
    usage = decode_usage(
        {
            "input_tokens": 120,
            "output_tokens": 40,
            "cache_read_input_tokens": 8_000,
            "cache_creation_input_tokens": 300,
        }
    )

    assert usage.input_tokens == 8_120
    assert usage.cache_read_tokens == 8_000
    assert usage.uncached_input_tokens == 120


def test_cache_creation_maps_to_cache_write_tokens():
    """Trap 7: the write half is billed as a miss and must stay separate."""
    usage = decode_usage({"input_tokens": 10, "cache_creation_input_tokens": 300})

    assert usage.cache_write_tokens == 300
    assert usage.input_tokens == 10


def test_a_response_with_no_usage_decodes_to_zeros_not_none():
    assert decode_usage(None).total_tokens == 0


# --------------------------------------------------------------------------
# request assembly
# --------------------------------------------------------------------------


def test_the_request_carries_the_model_named_by_the_config(monkeypatch):
    """Nothing else in this file would notice the wrong model being sent:
    every response here is a fake, so a hard-coded model string reaches the
    wire and the suite stays green."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        model="claude-haiku-4-5",
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["model"] == "claude-haiku-4-5"


def test_the_encoded_conversation_reaches_the_messages_parameter(monkeypatch):
    """``encode_conversation`` being correct is worth nothing if its result
    is not the thing handed to ``messages.create``."""
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))
    history = [
        Message.user("what is 2+2?"),
        Message.assistant("4"),
        Message.user("and 3+3?"),
    ]

    asyncio.run(provider.generate(history))

    _, expected = encode_conversation(history)
    assert sent_params(provider)["messages"] == expected
    assert [turn["role"] for turn in sent_params(provider)["messages"]] == [
        "user",
        "assistant",
        "user",
    ]


def test_a_system_prompt_reaches_the_system_parameter(monkeypatch):
    """Its absence is asserted two tests down; presence has to be asserted
    too, or an adapter that never sets the key passes both."""
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))

    asyncio.run(provider.generate([Message.system("be terse"), Message.user("hi")]))

    params = sent_params(provider)
    assert params["system"] == "be terse"
    assert all(turn["role"] != "system" for turn in params["messages"])


def test_encoded_tools_reach_the_tools_parameter(monkeypatch):
    """The Action half of the phase switch: tools passed in must actually
    be offered, not merely converted correctly and then dropped."""
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))
    tools = [
        ToolDefinition(
            name="run_skill",
            description="run an omics skill",
            input_schema={
                "type": "object",
                "properties": {"skill": {"type": "string"}},
                "required": ["skill"],
            },
        )
    ]

    asyncio.run(provider.generate([Message.user("hi")], tools=tools))

    assert sent_params(provider)["tools"] == encode_tools(tools)
    assert [tool["name"] for tool in sent_params(provider)["tools"]] == ["run_skill"]


def test_max_tokens_is_always_sent_because_anthropic_requires_it(monkeypatch):
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["max_tokens"] == provider.config.limits.output_tokens


def test_an_explicit_max_tokens_wins_over_the_model_ceiling(monkeypatch):
    provider = make_provider(
        monkeypatch, FakeClient(response={"content": []}), max_tokens=512
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["max_tokens"] == 512


def test_no_tools_omits_the_parameter_rather_than_sending_a_default_set(monkeypatch):
    """The Thinking/Action phase switch: no tools means the model must reason."""
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))

    asyncio.run(provider.generate([Message.user("think")], tools=[]))

    assert "tools" not in sent_params(provider)


def test_an_absent_system_prompt_omits_the_system_parameter(monkeypatch):
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))

    asyncio.run(provider.generate([Message.user("hi")]))

    assert "system" not in sent_params(provider)


# ---- thinking budget -----------------------------------------------------


def test_a_thinking_budget_below_the_floor_is_raised_to_the_floor():
    assert clamp_thinking_budget(1, 8_192) == MIN_THINKING_BUDGET_TOKENS
    assert clamp_thinking_budget(1_023, 8_192) == MIN_THINKING_BUDGET_TOKENS


def test_a_thinking_budget_at_or_above_max_tokens_is_lowered_below_it():
    assert clamp_thinking_budget(8_192, 8_192) == 8_191
    assert clamp_thinking_budget(99_999, 8_192) == 8_191


def test_a_thinking_budget_inside_the_legal_range_is_left_alone():
    assert clamp_thinking_budget(4_000, 8_192) == 4_000


def test_a_zero_thinking_budget_disables_extended_thinking():
    assert clamp_thinking_budget(0, 8_192) == 0
    assert clamp_thinking_budget(-5, 8_192) == 0


def test_a_thinking_budget_that_cannot_fit_max_tokens_is_refused():
    """Silently dropping the parameter would hide a contradiction."""
    with pytest.raises(ProviderError, match="cannot be satisfied"):
        clamp_thinking_budget(2_000, 1_024)


def test_extended_thinking_is_sent_as_an_enabled_budget(monkeypatch):
    """The legacy shape, on a model that still requires it.

    Haiku 4.5 has no adaptive mode, so ``budget_tokens`` is not a
    deprecated alternative there — it is the only way to ask for thinking
    at all.
    """
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        model="claude-haiku-4-5",
        max_tokens=8_192,
        thinking_budget_tokens=4_096,
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["thinking"] == {
        "type": "enabled",
        "budget_tokens": 4_096,
    }


def test_temperature_is_dropped_when_extended_thinking_is_enabled(monkeypatch):
    """Anthropic rejects any temperature but 1 while thinking is on."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        max_tokens=8_192,
        thinking_budget_tokens=4_096,
    )
    plain = make_provider(monkeypatch, FakeClient(response={"content": []}))

    asyncio.run(provider.generate([Message.user("hi")]))
    asyncio.run(plain.generate([Message.user("hi")]))

    assert "temperature" not in sent_params(provider)
    assert sent_params(plain)["temperature"] == provider.config.temperature


@pytest.mark.parametrize("model", ["claude-opus-4-7", "anthropic/claude-opus-4.7", "claude-sonnet-5"])
def test_no_temperature_is_sent_to_a_model_that_removed_sampling_parameters(monkeypatch, model):
    """Opus 4.7 and later answer any ``temperature`` with a 400, thinking or not."""
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}), model=model)

    asyncio.run(provider.generate([Message.user("hi")]))

    assert "temperature" not in sent_params(provider)


# ---- which thinking shape a model accepts --------------------------------


@pytest.mark.parametrize(
    "model",
    [
        "claude-fable-5",
        "claude-fable-5-1",
        "claude-fable-5.1",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4.7",
        "claude-opus-4-7-20260115",
        "claude-sonnet-5",
        "anthropic/claude-opus-4.7",
    ],
)
def test_models_that_reject_a_budget_are_classified_adaptive_only(model: str):
    """``budget_tokens`` was removed on these and now returns HTTP 400, so
    a misclassification here fails every call to the model."""
    assert thinking_support_for_model(model) is ThinkingSupport.ADAPTIVE_ONLY


@pytest.mark.parametrize("model", ["claude-opus-4-6", "claude-sonnet-4.6"])
def test_the_generation_where_both_shapes_work_is_classified_separately(
    model: str,
):
    assert thinking_support_for_model(model) is ThinkingSupport.ADAPTIVE_PREFERRED


@pytest.mark.parametrize(
    "model",
    [
        "claude-haiku-4-5",
        "claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "some-local-claude-proxy",
    ],
)
def test_older_and_unknown_models_keep_the_budgeted_shape(model: str):
    """``enabled`` + ``budget_tokens`` is the only way these think at all,
    and it is the safe answer for an unrecognized compatible endpoint."""
    assert thinking_support_for_model(model) is ThinkingSupport.BUDGET_ONLY


def test_an_adaptive_only_model_is_sent_adaptive_thinking_and_an_effort(
    monkeypatch,
):
    """The offered ``claude-opus-4-7`` used to 400 on every single call:
    the adapter hard-coded the budgeted shape for every model."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        model="claude-opus-4-7",
        max_tokens=8_192,
        thinking_budget_tokens=4_096,
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    params = sent_params(provider)
    assert params["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in params["thinking"]
    assert params["output_config"] == {"effort": "medium"}
    assert "temperature" not in params


@pytest.mark.parametrize(
    ("budget", "effort"),
    [
        (1, "low"),
        (4_095, "low"),
        (4_096, "medium"),
        (16_383, "medium"),
        (16_384, "high"),
        (32_768, "xhigh"),
        (65_536, "max"),
        (200_000, "max"),
    ],
)
def test_a_thinking_budget_becomes_an_effort_level_on_an_adaptive_model(
    budget: int, effort: str
):
    """An adaptive model has no budget knob, so the caller's number is read
    as a depth request rather than silently discarded."""
    assert effort_for_budget(budget) == effort


def test_an_adaptive_model_is_never_refused_for_not_fitting_a_budget(
    monkeypatch,
):
    """``clamp_thinking_budget`` enforces a relationship to ``max_tokens``
    that adaptive models no longer have; applying it there would reject a
    request the API accepts."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        model="claude-opus-4-7",
        max_tokens=512,
        thinking_budget_tokens=2_000,
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["thinking"] == {"type": "adaptive"}


def test_a_deprecated_but_functional_model_still_gets_the_adaptive_shape(
    monkeypatch,
):
    """Sonnet 4.6 accepts both shapes; the adapter sends the surviving one.

    This is the default model of the ``anthropic`` preset, so pinning it
    to ``budget_tokens`` — already removed on every later model — would
    ship a latent 400 into the default path. It also matches what the
    pre-rebuild ``providers/models.get_default_features`` already returns
    for any ``4-6`` / ``4-7`` match, so the legacy shape here would be a
    regression against live behaviour rather than a safe choice.
    """
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        model="claude-sonnet-4-6",
        max_tokens=8_192,
        thinking_budget_tokens=4_096,
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["thinking"] == {"type": "adaptive"}
    assert sent_params(provider)["output_config"] == {"effort": "medium"}


def test_the_legacy_shape_stays_reachable_through_extra(monkeypatch):
    """An operator who needs the exact token number honoured on 4.6 can
    still ask for it; ``extra`` outranks anything the adapter computed."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        model="claude-sonnet-4-6",
        max_tokens=8_192,
        thinking_budget_tokens=4_096,
        extra={"thinking": {"type": "enabled", "budget_tokens": 4_096}},
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["thinking"] == {
        "type": "enabled",
        "budget_tokens": 4_096,
    }


def test_a_zero_budget_sends_no_thinking_block_whatever_the_model():
    assert encode_thinking("claude-opus-4-7", 0, 8_192) == {}
    assert encode_thinking("claude-haiku-4-5", 0, 8_192) == {}


# ---- extra: the vendor-specific escape hatch -----------------------------


def test_extra_config_knobs_are_merged_into_the_request_body(monkeypatch):
    """Without this, ``top_p``, ``stop_sequences`` and ``metadata`` are all
    unreachable on Anthropic — the OpenAI adapter has always merged it."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        extra={"top_p": 0.9, "stop_sequences": ["</done>"]},
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    params = sent_params(provider)
    assert params["top_p"] == 0.9
    assert params["stop_sequences"] == ["</done>"]


def test_an_extra_knob_outranks_what_the_adapter_computed(monkeypatch):
    """Applied last, exactly as the OpenAI adapter applies it: an escape
    hatch that cannot override a default is no escape hatch."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        max_tokens=512,
        extra={"max_tokens": 4_096},
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["max_tokens"] == 4_096


def test_extra_reaches_the_streaming_path_too(monkeypatch):
    provider = make_provider(
        monkeypatch, FakeClient(stream=FakeStream([])), extra={"top_p": 0.5}
    )

    asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert sent_params(provider)["top_p"] == 0.5


def test_enabling_thinking_through_extra_withdraws_the_computed_temperature(
    monkeypatch,
):
    """Anthropic rejects the pair, and this is the documented workaround
    for a model whose thinking shape this adapter does not yet know."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        extra={"thinking": {"type": "adaptive"}},
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    params = sent_params(provider)
    assert params["thinking"] == {"type": "adaptive"}
    assert "temperature" not in params


def test_a_temperature_named_in_extra_is_taken_at_its_word(monkeypatch):
    """Only the value the adapter itself chose is withdrawn above."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": []}),
        extra={"thinking": {"type": "adaptive"}, "temperature": 1.0},
    )

    asyncio.run(provider.generate([Message.user("hi")]))

    assert sent_params(provider)["temperature"] == 1.0


# --------------------------------------------------------------------------
# client construction
# --------------------------------------------------------------------------


class FakeTimeout:
    def __init__(self, total, connect=None):
        self.total = total
        self.connect = connect


class FakeSDK:
    """Just enough of the ``anthropic`` module to build a client."""

    Timeout = FakeTimeout

    def __init__(self):
        self.kwargs = None

    def AsyncAnthropic(self, **kwargs):  # the SDK's own spelling
        self.kwargs = kwargs
        return object()


def build_with_fake_sdk(monkeypatch, sdk, **fields) -> dict:
    """Build a client from a config stated outright, not resolved.

    ``resolve_config`` substitutes the preset endpoint for an empty
    ``base_url``, so the "omit the argument" case is unreachable through
    it — the config is constructed directly to reach it.
    """
    monkeypatch.setattr(ap, "_load_sdk", lambda: sdk)
    ap._build_async_client(
        ProviderConfig(provider="anthropic", model="claude-sonnet-4-6", **fields)
    )
    return sdk.kwargs


def test_an_empty_base_url_omits_the_argument_instead_of_passing_none(monkeypatch):
    """``None`` would override the SDK's own default endpoint with nothing."""
    sdk = FakeSDK()

    kwargs = build_with_fake_sdk(monkeypatch, sdk, base_url="", api_key="")

    assert "base_url" not in kwargs
    assert "api_key" not in kwargs


def test_a_configured_base_url_and_key_are_passed_through(monkeypatch):
    sdk = FakeSDK()

    kwargs = build_with_fake_sdk(
        monkeypatch, sdk, base_url="https://gateway.example/v1", api_key="sk-test"
    )

    assert kwargs["base_url"] == "https://gateway.example/v1"
    assert kwargs["api_key"] == "sk-test"


def test_the_timeout_object_is_built_from_the_class_the_sdk_re_exports(monkeypatch):
    """Importing httpx directly would be both a layering and a version bug."""
    sdk = FakeSDK()

    kwargs = build_with_fake_sdk(
        monkeypatch, sdk, timeout_seconds=90.0, connect_timeout_seconds=3.0
    )

    assert isinstance(kwargs["timeout"], FakeTimeout)
    assert (kwargs["timeout"].total, kwargs["timeout"].connect) == (90.0, 3.0)


def test_an_sdk_without_a_timeout_class_falls_back_to_plain_seconds(monkeypatch):
    sdk = FakeSDK()
    sdk.Timeout = None

    kwargs = build_with_fake_sdk(monkeypatch, sdk, timeout_seconds=42.0)

    assert kwargs["timeout"] == 42.0


def test_the_configured_retry_count_reaches_the_client(monkeypatch):
    sdk = FakeSDK()

    assert build_with_fake_sdk(monkeypatch, sdk, max_retries=7)["max_retries"] == 7


def test_a_missing_anthropic_package_is_reported_as_a_provider_error(monkeypatch):
    """The SDK is an optional extra; its absence must not be an ImportError.

    Blocks the name at the import-system level rather than stubbing a
    loader function, so the test still describes reality now that
    ``_load_sdk`` uses a plain ``import anthropic`` statement — the form
    that keeps the dependency visible to tooling.
    """

    class _Blocker:
        @staticmethod
        def find_spec(name, *_args, **_kwargs):
            if name.split(".")[0] == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return None

    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_Blocker(), *sys.meta_path])

    with pytest.raises(ProviderError, match="pip install anthropic"):
        ap._load_sdk()


# --------------------------------------------------------------------------
# the interface
# --------------------------------------------------------------------------


def test_the_adapter_satisfies_the_llm_provider_protocol():
    provider = AnthropicProvider(resolve_config("anthropic", env={}))

    assert isinstance(provider, LLMProvider)


def test_the_provider_is_named_for_its_backend():
    assert AnthropicProvider(resolve_config("anthropic", env={})).name == "anthropic"


def test_bind_returns_a_new_provider_and_leaves_the_receiver_alone():
    original = AnthropicProvider(resolve_config("anthropic", env={}, max_tokens=1_000))

    bound = original.bind(max_tokens=2_000, model="claude-haiku-4-5")

    assert isinstance(bound, AnthropicProvider)
    assert bound is not original
    assert (bound.config.max_tokens, bound.config.model) == (2_000, "claude-haiku-4-5")
    assert (original.config.max_tokens, original.config.model) == (
        1_000,
        "claude-sonnet-4-6",
    )


def test_bind_rejects_an_unknown_configuration_field():
    provider = AnthropicProvider(resolve_config("anthropic", env={}))

    with pytest.raises(ProviderError, match="unknown provider configuration field"):
        provider.bind(max_token=10)


def test_generate_returns_the_message_the_usage_and_the_raw_stop_reason(monkeypatch):
    response = {
        "content": [{"type": "text", "text": "hello"}],
        "usage": {"input_tokens": 12, "output_tokens": 3},
        "stop_reason": "end_turn",
    }
    provider = make_provider(monkeypatch, FakeClient(response=response))

    completion = asyncio.run(provider.generate([Message.user("hi")]))

    assert completion.message.content == "hello"
    assert completion.usage.total_tokens == 15
    assert completion.finish_reason == "end_turn"


def test_a_truncated_reply_is_reported_through_the_raw_stop_reason(monkeypatch):
    """``max_tokens`` is the one case ``is_action`` cannot express."""
    provider = make_provider(
        monkeypatch,
        FakeClient(response={"content": [], "stop_reason": "max_tokens"}),
    )

    assert asyncio.run(provider.generate([Message.user("hi")])).finish_reason == (
        "max_tokens"
    )


def test_a_vendor_failure_is_reraised_as_a_provider_error_carrying_its_status(
    monkeypatch,
):
    """No caller should ever have to write ``except anthropic.APIError``."""

    class VendorError(Exception):
        status_code = 429

    provider = make_provider(monkeypatch, FakeClient(error=VendorError("slow down")))

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate([Message.user("hi")]))

    assert caught.value.status_code == 429
    assert caught.value.provider == "anthropic"
    assert "slow down" in str(caught.value)


def test_a_conversion_failure_is_not_rewrapped_as_a_network_failure(monkeypatch):
    provider = make_provider(monkeypatch, FakeClient(response={"content": []}))
    broken = Message.assistant(tool_calls=(ToolCall(id="x", name="t", arguments="{"),))

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate([broken]))

    assert caught.value.status_code is None
    assert "unparseable" in str(caught.value)


# --------------------------------------------------------------------------
# streaming
# --------------------------------------------------------------------------

def text_delta(text: str, index: int = 0) -> dict:
    return event(
        "content_block_delta", index=index, delta={"type": "text_delta", "text": text}
    )


TEXT_STREAM = [
    event("message_start", message={"usage": {"input_tokens": 100}}),
    event("content_block_start", index=0, content_block={"type": "text"}),
    text_delta("he"),
    text_delta("llo"),
    event("content_block_stop", index=0),
    event(
        "message_delta",
        delta={"stop_reason": "end_turn"},
        usage={"output_tokens": 7},
    ),
    event("message_stop"),
]


async def drain(iterator) -> list[StreamChunk]:
    return [chunk async for chunk in iterator]


def test_streaming_yields_text_deltas_and_exactly_one_terminal_done_chunk(monkeypatch):
    stream = FakeStream(TEXT_STREAM)
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert [chunk.type for chunk in chunks] == [
        StreamChunkType.TEXT_DELTA,
        StreamChunkType.TEXT_DELTA,
        StreamChunkType.DONE,
    ]
    assert chunks[-1].message.content == "hello"


def test_thinking_deltas_are_streamed_as_reasoning_and_land_in_the_message(monkeypatch):
    stream = FakeStream(
        [
            event("content_block_start", index=0, content_block={"type": "thinking"}),
            event(
                "content_block_delta",
                index=0,
                delta={"type": "thinking_delta", "thinking": "hmm"},
            ),
            text_delta("ok", index=1),
        ]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert chunks[0].type == StreamChunkType.REASONING_DELTA
    assert chunks[0].delta == "hmm"
    assert chunks[-1].message.reasoning_content == "hmm"
    assert chunks[-1].message.content == "ok"


def test_streamed_tool_calls_that_start_above_index_zero_are_all_reassembled(
    monkeypatch,
):
    """Trap 1, in its Anthropic form: the index is the content-block index.

    With a leading thinking block the tool_use blocks occupy 1 and 2. A
    positional loop over the accumulators finds nothing at 0 and drops
    the model's last tool call without a word.
    """
    stream = FakeStream(
        [
            event("content_block_start", index=0, content_block={"type": "thinking"}),
            event(
                "content_block_start",
                index=1,
                content_block={"type": "tool_use", "id": "t1", "name": "alpha"},
            ),
            event(
                "content_block_delta",
                index=1,
                delta={"type": "input_json_delta", "partial_json": '{"a":'},
            ),
            event(
                "content_block_delta",
                index=1,
                delta={"type": "input_json_delta", "partial_json": " 1}"},
            ),
            event(
                "content_block_start",
                index=2,
                content_block={"type": "tool_use", "id": "t2", "name": "beta"},
            ),
            event(
                "content_block_delta",
                index=2,
                delta={"type": "input_json_delta", "partial_json": "{}"},
            ),
        ]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert chunks[-1].message.tool_calls == (
        ToolCall(id="t1", name="alpha", arguments='{"a": 1}'),
        ToolCall(id="t2", name="beta", arguments="{}"),
    )


def test_partial_tool_arguments_are_never_visible_before_the_done_chunk(monkeypatch):
    stream = FakeStream(
        [
            event(
                "content_block_start",
                index=0,
                content_block={"type": "tool_use", "id": "t", "name": "n"},
            ),
            event(
                "content_block_delta",
                index=0,
                delta={"type": "input_json_delta", "partial_json": '{"a"'},
            ),
        ]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert [chunk.type for chunk in chunks] == [StreamChunkType.DONE]


def test_the_done_chunk_keeps_the_input_count_reported_at_message_start(monkeypatch):
    """Input arrives at ``message_start``, output only at ``message_delta``."""
    stream = FakeStream(TEXT_STREAM)
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert chunks[-1].usage.input_tokens == 100
    assert chunks[-1].usage.output_tokens == 7


def test_streamed_cache_reads_are_added_back_into_total_input(monkeypatch):
    """Trap 7 again, on the streaming path, where usage arrives in halves."""
    stream = FakeStream(
        [
            event(
                "message_start",
                message={
                    "usage": {
                        "input_tokens": 20,
                        "cache_read_input_tokens": 4_000,
                        "cache_creation_input_tokens": 90,
                    }
                },
            ),
            event("message_delta", usage={"output_tokens": 5}),
        ]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    usage = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))[-1].usage

    assert usage.input_tokens == 4_020
    assert usage.cache_read_tokens == 4_000
    assert usage.cache_write_tokens == 90
    assert usage.output_tokens == 5


def test_a_streamed_stop_reason_reaches_the_done_chunk(monkeypatch):
    """Plan 0027 §5. Anthropic puts it on ``message_delta``'s own delta —
    a message-level delta, not a content block."""
    stream = FakeStream(
        [event("message_delta", delta={"stop_reason": "end_turn"})]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert chunks[-1].finish_reason == "end_turn"


def test_a_stream_truncated_by_max_tokens_says_so(monkeypatch):
    """The case the Main Loop must not read as a converged turn."""
    stream = FakeStream(
        [
            event(
                "content_block_delta",
                index=0,
                delta={"type": "text_delta", "text": "half a sen"},
            ),
            event("message_delta", delta={"stop_reason": "max_tokens"}),
        ]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    done = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))[-1]

    assert done.finish_reason == "max_tokens"
    assert done.message.is_action is False


def test_a_stream_with_no_stop_reason_leaves_finish_reason_empty(monkeypatch):
    stream = FakeStream([event("message_delta", usage={"output_tokens": 5})])
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert chunks[-1].finish_reason == ""
    assert chunks[-1].usage.output_tokens == 5


def test_a_stream_that_reports_no_usage_still_ends_with_a_zeroed_usage(monkeypatch):
    stream = FakeStream([event("message_stop")])
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    chunks = asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert chunks[-1].usage.total_tokens == 0


def test_generate_stream_raises_at_the_call_site_for_a_malformed_tool_call(monkeypatch):
    provider = make_provider(monkeypatch, FakeClient(stream=FakeStream([])))
    broken = Message.assistant(tool_calls=(ToolCall(id="x", name="t", arguments="{"),))

    with pytest.raises(ProviderError):
        provider.generate_stream([broken])


def test_a_midstream_failure_is_reraised_as_a_provider_error(monkeypatch):
    stream = FakeStream(
        [
            text_delta("a"),
            RuntimeError("connection reset"),
        ]
    )
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    with pytest.raises(ProviderError, match="connection reset"):
        asyncio.run(drain(provider.generate_stream([Message.user("hi")])))

    assert stream.closed is True


# ---- trap 9 --------------------------------------------------------------


def test_an_abandoned_stream_is_closed_when_the_generator_is_disposed(monkeypatch):
    """Trap 9: a consumer that stops early must not leak the connection.

    If the ``try/finally`` regresses, the HTTP response stays open for
    the lifetime of the process every time a turn ends early.
    """
    stream = FakeStream(TEXT_STREAM)
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    async def take_one_then_walk_away():
        iterator = provider.generate_stream([Message.user("hi")])
        async for _chunk in iterator:
            break
        assert stream.closed is False
        await iterator.aclose()

    asyncio.run(take_one_then_walk_away())

    assert stream.closed is True


def test_a_cancelled_turn_closes_the_stream_and_stays_cancelled(monkeypatch):
    """Trap 9: cancellation must reach the socket, not be swallowed.

    A ``CancelledError`` caught and re-raised as ``ProviderError`` would
    also make a cancelled turn indistinguishable from a backend outage.
    """

    class BlockingStream(FakeStream):
        async def __anext__(self):
            if self._events:
                return self._events.pop(0)
            await asyncio.Event().wait()

    stream = BlockingStream([text_delta("a")])
    provider = make_provider(monkeypatch, FakeClient(stream=stream))

    async def cancel_mid_flight():
        iterator = provider.generate_stream([Message.user("hi")])
        task = asyncio.create_task(drain(iterator))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_mid_flight())

    assert stream.closed is True


def test_closing_a_stream_that_cannot_be_closed_is_not_an_error():
    """The finally must never replace the failure that triggered it."""

    class Hostile:
        async def close(self):
            raise RuntimeError("already detached")

    asyncio.run(ap._close_stream(Hostile()))
    asyncio.run(ap._close_stream(object()))
