"""The OpenAI-compatible adapter (plan 0026 §8 task B, traps 2, 3, 4, 9).

No network, and no ``openai`` package either. The conversion halves are
pure functions asserted against literal payloads in both directions; the
call paths run against a fake client substituted for the SDK one, and the
client-construction tests install a fake ``openai`` module in
``sys.modules``. The adapter is therefore fully exercised on an
installation that has never seen the vendor SDK — which is also how it
will be run in CI.
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from omicsclaw.provider import Completion, LLMProvider, ProviderConfig, ProviderError
from omicsclaw.provider.openai_provider import (
    OpenAIProvider,
    apply_cache_breakpoints,
    breakpoints_enabled,
    decode_message,
    decode_usage,
    encode_message,
    encode_messages,
    encode_tools,
    wants_include_reasoning,
)
from omicsclaw.schema import (
    Message,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    Usage,
)


# --- doubles ---------------------------------------------------------------


class FakeStream:
    """An SDK stream: async-iterable, closeable, and able to blow up."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self._chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    async def close(self) -> None:
        self.closed = True


class FakeCompletions:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.payloads: list[dict[str, Any]] = []

    async def create(self, **payload: Any) -> Any:
        self.payloads.append(payload)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeClient:
    def __init__(self, result: Any) -> None:
        self.completions = FakeCompletions(result)
        self.chat = types.SimpleNamespace(completions=self.completions)


class Extras:
    """A typed SDK model that hides unknown fields in pydantic extras.

    The shape trap 2 is defensive about: ``reasoning`` is not in OpenAI's
    schema, so a strict model exposes it only through ``model_extra``.
    """

    def __init__(self, **fields: Any) -> None:
        self.content = fields.pop("content", None)
        self.model_extra = fields


def _config(**overrides: Any) -> ProviderConfig:
    config = ProviderConfig(provider="openai", model="gpt-5.5", temperature=0.3)
    return config.with_overrides(**overrides) if overrides else config


def _provider(result: Any = None, **overrides: Any) -> OpenAIProvider:
    provider = OpenAIProvider(_config(**overrides))
    provider._client = FakeClient(result)
    return provider


def _completion_response(
    *,
    message: dict[str, Any],
    usage: dict[str, Any] | None = None,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": usage,
    }


def _text_chunk(content: str) -> dict[str, Any]:
    return {"choices": [{"delta": {"content": content}}]}


def _drain(provider: OpenAIProvider, **kwargs: Any) -> list[Any]:
    async def collect() -> list[Any]:
        stream = provider.generate_stream([Message.user("hi")], **kwargs)
        return [chunk async for chunk in stream]

    return asyncio.run(collect())


def _sent(provider: OpenAIProvider) -> dict[str, Any]:
    return provider._client.chat.completions.payloads[-1]


# --- conformance -----------------------------------------------------------


def test_the_adapter_satisfies_the_provider_protocol():
    assert isinstance(OpenAIProvider(_config()), LLMProvider)


def test_bind_returns_a_new_provider_without_mutating_the_receiver():
    original = OpenAIProvider(_config())
    bound = original.bind(model="gpt-5-mini", max_tokens=512)

    assert bound._config.model == "gpt-5-mini"
    assert bound._config.max_tokens == 512
    assert original._config.model == "gpt-5.5"
    assert original._config.max_tokens == 0


def test_the_name_falls_back_to_openai_when_no_preset_was_resolved():
    assert OpenAIProvider(_config(provider="")).name == "openai"
    assert OpenAIProvider(_config(provider="deepseek")).name == "deepseek"


# --- conversion: schema → OpenAI -------------------------------------------


def test_the_four_roles_map_straight_onto_the_four_openai_roles():
    encoded = encode_messages(
        [
            Message.system("you are a bioinformatics agent"),
            Message.user("run a QC"),
            Message.assistant("done"),
            Message.tool(tool_call_id="call_1", content="ok", name="run_skill"),
        ]
    )

    assert [m["role"] for m in encoded] == ["system", "user", "assistant", "tool"]
    assert encoded[3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "ok",
        "name": "run_skill",
    }


def test_tool_call_arguments_are_sent_as_the_raw_json_string():
    """Byte stability: a decode/re-encode round trip reorders keys and
    costs a prompt-cache hit on every subsequent turn."""
    raw = '{"skill":"spatial-de","output":"/tmp/de"}'
    encoded = encode_message(
        Message.assistant(tool_calls=[ToolCall(id="c1", name="run", arguments=raw)])
    )

    assert encoded["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "run", "arguments": raw}}
    ]
    assert encoded["tool_calls"][0]["function"]["arguments"] is raw


def test_an_assistant_turn_that_only_calls_tools_omits_its_empty_content():
    encoded = encode_message(
        Message.assistant(tool_calls=[ToolCall(id="c1", name="run")])
    )
    assert "content" not in encoded


def test_an_assistant_turn_without_tool_calls_omits_the_tool_calls_key():
    """A spurious ``"tool_calls": []`` changes the cached prefix bytes."""
    encoded = encode_message(Message.assistant("plain answer"))
    assert encoded == {"role": "assistant", "content": "plain answer"}


def test_reasoning_content_is_passed_back_on_historical_assistant_turns():
    """DeepSeek thinking endpoints reject a multi-turn request whose past
    assistant messages have lost the Thought; dropping it is an HTTP 400."""
    encoded = encode_message(
        Message.assistant("the answer", reasoning_content="first I check the QC")
    )
    assert encoded["reasoning_content"] == "first I check the QC"


def test_an_assistant_turn_with_no_thought_omits_the_reasoning_key():
    assert "reasoning_content" not in encode_message(Message.assistant("hi"))


def test_a_tool_result_without_a_name_omits_the_name_key():
    encoded = encode_message(Message.tool(tool_call_id="c1", content="ok"))
    assert encoded == {"role": "tool", "tool_call_id": "c1", "content": "ok"}


def test_tools_are_encoded_as_openai_function_definitions():
    encoded = encode_tools(
        [
            ToolDefinition(
                name="run_skill",
                description="run one omics skill",
                input_schema={"type": "object", "properties": {"skill": {}}},
            )
        ]
    )

    assert encoded == [
        {
            "type": "function",
            "function": {
                "name": "run_skill",
                "description": "run one omics skill",
                "parameters": {"type": "object", "properties": {"skill": {}}},
            },
        }
    ]


def test_a_tool_with_no_schema_still_gets_a_valid_object_schema():
    encoded = encode_tools([ToolDefinition(name="now", description="the time")])
    assert encoded[0]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
    }


def test_no_tools_and_empty_tools_both_strip_the_tools_key_entirely():
    """The Thinking/Action phase switch: no tools must mean no tools, not
    a default set the model can still act with."""
    assert encode_tools(None) is None
    assert encode_tools([]) is None

    provider = _provider(_completion_response(message={"content": "thought"}))
    asyncio.run(provider.generate([Message.user("think")], None))
    assert "tools" not in _sent(provider)


# --- conversion: OpenAI → schema -------------------------------------------


def test_a_null_content_decodes_to_the_empty_string():
    """How this dialect says "no text" on a pure tool-call turn."""
    message = decode_message({"content": None, "tool_calls": []})
    assert message.content == ""
    assert message.tool_calls == ()


def test_an_already_decoded_arguments_object_is_re_encoded_as_json_text():
    """Several OpenAI-compatible servers return ``arguments`` as an object;
    the schema's contract is that it is always parseable JSON *text*."""
    message = decode_message(
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "run", "arguments": {"skill": "spatial-de"}},
                }
            ],
        }
    )

    assert message.tool_calls[0].arguments == '{"skill":"spatial-de"}'
    assert message.tool_calls[0].parsed_arguments() == {"skill": "spatial-de"}


def test_a_tool_call_the_local_registry_cannot_run_is_dropped():
    message = decode_message(
        {
            "content": "",
            "tool_calls": [
                {"id": "c1", "type": "web_search", "function": {"name": "search"}},
                {"id": "c2", "type": "function", "function": {"name": "run"}},
            ],
        }
    )
    assert [call.id for call in message.tool_calls] == ["c2"]


def test_a_tool_call_whose_type_the_server_omitted_is_still_accepted():
    """Refusing those would silently lose real calls from compatible servers."""
    message = decode_message(
        {"content": "", "tool_calls": [{"id": "c1", "function": {"name": "run"}}]}
    )
    assert message.tool_calls[0].name == "run"


def test_a_tool_call_with_no_arguments_still_decodes_to_parseable_json():
    message = decode_message(
        {"tool_calls": [{"id": "c1", "function": {"name": "run", "arguments": ""}}]}
    )
    assert message.tool_calls[0].arguments == "{}"


def test_reasoning_content_is_read_back_off_a_blocking_response():
    message = decode_message({"content": "answer", "reasoning_content": "thought"})
    assert message.reasoning_content == "thought"


def test_encoding_and_decoding_an_assistant_turn_round_trips():
    original = Message.assistant(
        "here you go",
        reasoning_content="checking the counts first",
        tool_calls=(ToolCall(id="c1", name="run", arguments='{"a":1}'),),
    )
    assert decode_message(encode_message(original)) == original


# --- usage -----------------------------------------------------------------


def test_usage_reads_openais_nested_cache_split():
    usage = decode_usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 768},
        }
    )
    assert usage == Usage(input_tokens=1000, output_tokens=50, cache_read_tokens=768)
    assert usage.uncached_input_tokens == 232


def test_usage_reads_deepseeks_top_level_cache_split():
    usage = decode_usage(
        {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_cache_hit_tokens": 640,
            "prompt_cache_miss_tokens": 360,
        }
    )
    assert usage.cache_read_tokens == 640
    assert usage.input_tokens == 1000


def test_prompt_tokens_already_include_the_cached_ones_and_are_not_adjusted():
    """Unlike Anthropic's ``input_tokens``, this dialect's ``prompt_tokens``
    is the total; adding the cache figure back would double-count it."""
    usage = decode_usage(
        {"prompt_tokens": 800, "prompt_tokens_details": {"cached_tokens": 800}}
    )
    assert usage.input_tokens == 800
    assert usage.uncached_input_tokens == 0


def test_a_backend_that_reports_nothing_yields_zero_usage_not_none():
    assert decode_usage(None) == Usage()
    assert decode_usage({}) == Usage()


# --- generate --------------------------------------------------------------


def test_generate_returns_the_message_usage_and_finish_reason_together():
    provider = _provider(
        _completion_response(
            message={"content": "42"},
            usage={"prompt_tokens": 9, "completion_tokens": 2},
            finish_reason="stop",
        )
    )
    completion = asyncio.run(provider.generate([Message.user("the answer?")]))

    assert isinstance(completion, Completion)
    assert completion.message.content == "42"
    assert completion.usage == Usage(input_tokens=9, output_tokens=2)
    assert completion.finish_reason == "stop"


def test_the_request_carries_the_model_and_temperature_from_the_config():
    provider = _provider(
        _completion_response(message={"content": "ok"}), model="deepseek-v4-flash"
    )
    asyncio.run(provider.generate([Message.user("hi")]))

    payload = _sent(provider)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["temperature"] == 0.3
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_an_unset_max_tokens_is_omitted_rather_than_guessed():
    """Naming the table's conservative fallback here could only truncate a
    reply the backend would otherwise have allowed to finish."""
    provider = _provider(_completion_response(message={"content": "ok"}))
    asyncio.run(provider.generate([Message.user("hi")]))
    assert "max_tokens" not in _sent(provider)


def test_a_configured_max_tokens_reaches_the_request():
    provider = _provider(_completion_response(message={"content": "ok"}), max_tokens=64)
    asyncio.run(provider.generate([Message.user("hi")]))
    assert _sent(provider)["max_tokens"] == 64


def test_extra_config_knobs_are_merged_into_the_request_body():
    provider = _provider(
        _completion_response(message={"content": "ok"}),
        extra={"reasoning_effort": "high"},
    )
    asyncio.run(provider.generate([Message.user("hi")]))
    assert _sent(provider)["reasoning_effort"] == "high"


def test_a_vendor_sdk_failure_becomes_a_provider_error_carrying_its_status():
    """No caller may ever have to write ``except openai.APIError``."""

    class RateLimited(Exception):
        status_code = 429

    provider = _provider(RateLimited("slow down"))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate([Message.user("hi")]))

    assert caught.value.status_code == 429
    assert caught.value.provider == "openai"
    assert isinstance(caught.value.__cause__, RateLimited)


def test_a_failure_that_never_reached_the_wire_has_no_status_code():
    provider = _provider(ValueError("bad payload"))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate([Message.user("hi")]))
    assert caught.value.status_code is None


def test_a_response_with_no_choices_is_an_error_not_an_empty_message():
    provider = _provider({"choices": [], "usage": None})
    with pytest.raises(ProviderError, match="no choices"):
        asyncio.run(provider.generate([Message.user("hi")]))


# --- streaming -------------------------------------------------------------


def test_text_deltas_are_emitted_and_accumulated_into_the_done_message():
    provider = _provider(FakeStream([_text_chunk("par"), _text_chunk("tial")]))
    chunks = _drain(provider)

    assert [c.type for c in chunks[:-1]] == [
        StreamChunkType.TEXT_DELTA,
        StreamChunkType.TEXT_DELTA,
    ]
    assert chunks[-1].type is StreamChunkType.DONE
    assert chunks[-1].message.content == "partial"


def test_tool_calls_split_across_chunks_are_reassembled_on_done():
    provider = _provider(
        FakeStream(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {
                                            "name": "run_skill",
                                            "arguments": '{"skill":',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": '"spatial-de"}'},
                                    }
                                ]
                            }
                        }
                    ]
                },
            ]
        )
    )
    message = _drain(provider)[-1].message

    assert message.is_action
    assert message.tool_calls == (
        ToolCall(id="c1", name="run_skill", arguments='{"skill":"spatial-de"}'),
    )


def test_partial_tool_arguments_are_never_exposed_before_done():
    """A consumer must not be able to act on a call the model is still
    spelling out."""
    provider = _provider(
        FakeStream(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {"arguments": '{"a":'},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        )
    )
    chunks = _drain(provider)
    assert [c.type for c in chunks] == [StreamChunkType.DONE]


def test_a_streaming_failure_becomes_a_provider_error():
    provider = _provider(FakeStream([_text_chunk("a"), RuntimeError("socket died")]))
    with pytest.raises(ProviderError, match="socket died"):
        _drain(provider)


# --- trap 2: the Thought arrives under several field names ----------------


def test_deepseeks_reasoning_content_is_streamed_as_reasoning_deltas():
    """Trap 2. Miss this field and DeepSeek-R1's entire Thought is lost —
    nothing is emitted to the UI and nothing is passed back next turn."""
    provider = _provider(
        FakeStream(
            [
                {"choices": [{"delta": {"reasoning_content": "first, "}}]},
                {"choices": [{"delta": {"reasoning_content": "check QC"}}]},
                _text_chunk("done"),
            ]
        )
    )
    chunks = _drain(provider)

    assert [c.delta for c in chunks if c.type is StreamChunkType.REASONING_DELTA] == [
        "first, ",
        "check QC",
    ]
    assert chunks[-1].message.reasoning_content == "first, check QC"
    assert chunks[-1].message.content == "done"


def test_openrouters_reasoning_field_is_streamed_as_reasoning_deltas():
    """Trap 2. OpenRouter proxying a GPT model spells the same thing
    ``reasoning``; reading only ``reasoning_content`` yields silence."""
    provider = _provider(
        FakeStream([{"choices": [{"delta": {"reasoning": "weighing options"}}]}])
    )
    chunks = _drain(provider)

    assert chunks[0].type is StreamChunkType.REASONING_DELTA
    assert chunks[0].delta == "weighing options"
    assert chunks[-1].message.reasoning_content == "weighing options"


def test_a_reasoning_field_hidden_in_sdk_extras_is_still_found():
    """Trap 2. Neither spelling is in OpenAI's schema, so a typed SDK model
    parks it in ``model_extra`` instead of exposing it as an attribute."""
    provider = _provider(
        FakeStream([{"choices": [{"delta": Extras(content=None, reasoning="hidden")}]}])
    )
    chunks = _drain(provider)

    assert chunks[0].type is StreamChunkType.REASONING_DELTA
    assert chunks[0].delta == "hidden"


def test_reasoning_content_wins_when_a_gateway_sends_both_spellings():
    provider = _provider(
        FakeStream(
            [
                {
                    "choices": [
                        {"delta": {"reasoning_content": "native", "reasoning": "proxy"}}
                    ]
                }
            ]
        )
    )
    assert _drain(provider)[0].delta == "native"


def test_a_reasoning_details_object_is_not_mistaken_for_reasoning_text():
    """Some gateways put a structured block under ``reasoning``; only text
    belongs in a reasoning delta."""
    provider = _provider(
        FakeStream([{"choices": [{"delta": {"reasoning": {"summary": "x"}}}]}])
    )
    assert [c.type for c in _drain(provider)] == [StreamChunkType.DONE]


# --- trap 3: gateways that need include_reasoning -------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "https://openrouter.ai/api/v1",
        "https://router.requesty.ai/v1",
        "https://OpenRouter.ai/api/v1",
    ],
)
def test_openrouter_and_requesty_get_include_reasoning_injected(base_url: str):
    """Trap 3. Without the flag these gateways return no reasoning at all,
    so the Thought is missing for reasons no response field explains."""
    assert wants_include_reasoning(base_url)

    provider = _provider(
        _completion_response(message={"content": "ok"}), base_url=base_url
    )
    asyncio.run(provider.generate([Message.user("hi")]))
    assert _sent(provider)["include_reasoning"] is True


@pytest.mark.parametrize(
    "base_url", ["", "https://api.deepseek.com", "http://localhost:11434/v1"]
)
def test_other_backends_do_not_get_include_reasoning(base_url: str):
    assert not wants_include_reasoning(base_url)

    provider = _provider(
        _completion_response(message={"content": "ok"}), base_url=base_url
    )
    asyncio.run(provider.generate([Message.user("hi")]))
    assert "include_reasoning" not in _sent(provider)


def test_include_reasoning_is_injected_on_the_streaming_path_too():
    provider = _provider(
        FakeStream([_text_chunk("hi")]), base_url="https://openrouter.ai/api/v1"
    )
    _drain(provider)
    assert _sent(provider)["include_reasoning"] is True


# --- trap 4: streaming usage has to be opted into and read first ----------


def test_streaming_opts_into_usage_reporting():
    """Trap 4. Without ``stream_options.include_usage`` OpenAI never fills
    the usage block and every streamed turn is billed as zero tokens."""
    provider = _provider(FakeStream([_text_chunk("hi")]))
    _drain(provider)
    assert _sent(provider)["stream_options"] == {"include_usage": True}


def test_a_streamed_finish_reason_reaches_the_done_chunk():
    """Plan 0027 §5. It rides the last content-bearing chunk, whose
    ``delta`` is empty — so reading it off the delta finds nothing."""
    provider = _provider(
        FakeStream(
            [
                _text_chunk("hi"),
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
        )
    )
    assert _drain(provider)[-1].finish_reason == "stop"


def test_a_stream_truncated_by_the_output_ceiling_says_so():
    """The case the Main Loop must not read as a converged turn: a reply
    cut off mid-sentence also ends with a ``DONE`` chunk requesting no
    tools, so ``message.is_action`` alone cannot tell them apart."""
    provider = _provider(
        FakeStream(
            [
                _text_chunk("half a sen"),
                {"choices": [{"delta": {}, "finish_reason": "length"}]},
            ]
        )
    )
    done = _drain(provider)[-1]

    assert done.finish_reason == "length"
    assert done.message.is_action is False


def test_a_stream_that_never_reports_a_finish_reason_leaves_it_empty():
    provider = _provider(FakeStream([_text_chunk("hi")]))
    assert _drain(provider)[-1].finish_reason == ""


def test_a_null_finish_reason_on_earlier_chunks_does_not_erase_the_real_one():
    """The field is null on every chunk until the model stops, so the
    last *non-empty* value wins rather than the last value seen."""
    provider = _provider(
        FakeStream(
            [
                {"choices": [{"delta": {"content": "a"}, "finish_reason": None}]},
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
                {"choices": [{"delta": {}, "finish_reason": None}]},
            ]
        )
    )
    assert _drain(provider)[-1].finish_reason == "tool_calls"


def test_a_blocking_call_does_not_ask_for_stream_options():
    provider = _provider(_completion_response(message={"content": "ok"}))
    asyncio.run(provider.generate([Message.user("hi")]))
    assert "stream_options" not in _sent(provider)


def test_usage_in_the_final_empty_choices_chunk_is_not_lost():
    """Trap 4. The usage-bearing chunk has an EMPTY ``choices`` array, so
    code that skips empty-choice chunks *before* reading usage drops all
    token accounting for the whole run."""
    provider = _provider(
        FakeStream(
            [
                _text_chunk("hi"),
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 7,
                        "prompt_tokens_details": {"cached_tokens": 64},
                    },
                },
            ]
        )
    )
    done = _drain(provider)[-1]

    assert done.type is StreamChunkType.DONE
    assert done.usage == Usage(input_tokens=120, output_tokens=7, cache_read_tokens=64)


def test_an_empty_choices_chunk_without_usage_emits_nothing():
    provider = _provider(FakeStream([{"choices": []}, _text_chunk("hi")]))
    chunks = _drain(provider)
    assert [c.type for c in chunks[:-1]] == [StreamChunkType.TEXT_DELTA]


def test_a_stream_that_reports_no_usage_still_ends_with_zero_usage():
    provider = _provider(FakeStream([_text_chunk("hi")]))
    assert _drain(provider)[-1].usage == Usage()


# --- trap 9: cancellation must not leak the stream ------------------------


def test_a_fully_drained_stream_is_closed():
    stream = FakeStream([_text_chunk("hi")])
    provider = _provider(stream)
    _drain(provider)
    assert stream.closed


def test_an_abandoned_stream_is_closed():
    """Trap 9. A consumer that breaks out after the first delta — the loop
    hitting a stop condition — must not leave the connection open."""
    stream = FakeStream([_text_chunk("a"), _text_chunk("b"), _text_chunk("c")])
    provider = _provider(stream)

    async def take_one() -> None:
        iterator = provider.generate_stream([Message.user("hi")])
        async for _ in iterator:
            break
        await iterator.aclose()

    asyncio.run(take_one())
    assert stream.closed


def test_a_cancelled_turn_closes_the_stream():
    """Trap 9. Cancellation is how a turn ends when the user interrupts;
    the HTTP connection has to be released on that path too."""
    slow = FakeStream([_text_chunk("a")])

    async def cancel_mid_stream() -> None:
        provider = OpenAIProvider(_config())
        provider._client = FakeClient(slow)

        async def consume() -> None:
            async for _ in provider.generate_stream([Message.user("hi")]):
                await asyncio.sleep(3600)

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_mid_stream())
    assert slow.closed


def test_a_failing_stream_is_closed_before_the_error_propagates():
    stream = FakeStream([RuntimeError("socket died")])
    provider = _provider(stream)
    with pytest.raises(ProviderError):
        _drain(provider)
    assert stream.closed


# --- prompt-cache breakpoints (ADR 0024) ----------------------------------


def _breakpoint_payload(**overrides: Any) -> dict[str, Any]:
    provider = _provider(_completion_response(message={"content": "ok"}), **overrides)
    asyncio.run(
        provider.generate(
            [Message.system("you are an agent"), Message.user("hi")],
            [
                ToolDefinition(name="first", description="a"),
                ToolDefinition(name="last", description="b"),
            ],
        )
    )
    return _sent(provider)


def test_an_anthropic_model_gets_breakpoints_on_the_system_prompt_and_last_tool():
    payload = _breakpoint_payload(
        provider="openrouter",
        model="anthropic/claude-sonnet-4.6",
        base_url="https://openrouter.ai/api/v1",
    )

    assert payload["messages"][0]["content"] == [
        {
            "type": "text",
            "text": "you are an agent",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert payload["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in payload["tools"][0]


def test_a_backend_that_caches_automatically_is_left_byte_identical():
    """OpenAI and DeepSeek cache the stable prefix on their own; adding a
    block they do not understand would only change the bytes."""
    payload = _breakpoint_payload(provider="deepseek", model="deepseek-v4-flash")

    assert payload["messages"][0]["content"] == "you are an agent"
    assert "cache_control" not in payload["tools"][-1]


def test_a_localhost_endpoint_gets_no_breakpoints():
    """ccproxy and friends reject the block shape outright."""
    payload = _breakpoint_payload(
        provider="anthropic",
        model="claude-sonnet-4-6",
        base_url="http://localhost:8082",
    )
    assert payload["messages"][0]["content"] == "you are an agent"


def test_the_env_kill_switch_disables_the_breakpoints(monkeypatch):
    monkeypatch.setenv("OMICSCLAW_PROMPT_CACHE_BREAKPOINTS", "0")
    payload = _breakpoint_payload(provider="anthropic", model="claude-sonnet-4-6")
    assert payload["messages"][0]["content"] == "you are an agent"


def test_the_kill_switch_reads_the_same_variable_the_query_engine_reads():
    assert breakpoints_enabled({}) is True
    assert breakpoints_enabled({"OMICSCLAW_PROMPT_CACHE_BREAKPOINTS": "0"}) is False
    assert breakpoints_enabled({"OMICSCLAW_PROMPT_CACHE_BREAKPOINTS": "1"}) is True


def test_applying_the_breakpoints_does_not_mutate_the_caller_payload():
    """Applied every turn, so a mutation would compound across the run."""
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    tools = [{"type": "function", "function": {"name": "t"}}]

    marked, marked_tools = apply_cache_breakpoints(
        messages, tools, provider="anthropic", model="claude-sonnet-4-6", base_url=""
    )

    assert messages[0]["content"] == "s"
    assert "cache_control" not in tools[0]
    assert marked is not messages and marked_tools is not tools


def test_the_breakpoints_are_identical_when_applied_to_the_same_turn_twice():
    """The mark must not itself churn the prefix it exists to cache."""
    messages = [{"role": "system", "content": "s"}]
    once = apply_cache_breakpoints(
        messages, None, provider="anthropic", model="claude-sonnet-4-6", base_url=""
    )
    twice = apply_cache_breakpoints(
        messages, None, provider="anthropic", model="claude-sonnet-4-6", base_url=""
    )
    assert once == twice


# --- client construction ---------------------------------------------------


def _install_fake_sdk(monkeypatch) -> types.ModuleType:
    module = types.ModuleType("openai")

    class AsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    module.AsyncOpenAI = AsyncOpenAI
    module.Timeout = lambda total, **kw: ("timeout", total, kw)
    monkeypatch.setitem(sys.modules, "openai", module)
    return module


def test_an_empty_base_url_omits_the_kwarg_so_the_sdk_default_wins():
    """Passing ``None`` instead would override the default with nothing."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install_fake_sdk(monkeypatch)
        client = OpenAIProvider(_config(base_url=""))._create_client()
    assert "base_url" not in client.kwargs


def test_a_configured_base_url_reaches_the_sdk():
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install_fake_sdk(monkeypatch)
        client = OpenAIProvider(
            _config(base_url="https://api.deepseek.com")
        )._create_client()
    assert client.kwargs["base_url"] == "https://api.deepseek.com"


def test_the_sdk_timeout_is_built_here_from_the_configs_plain_seconds():
    """``ProviderConfig`` carries numbers because it may not import httpx."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install_fake_sdk(monkeypatch)
        client = OpenAIProvider(
            _config(timeout_seconds=42.0, connect_timeout_seconds=3.0, max_retries=7)
        )._create_client()

    assert client.kwargs["timeout"] == ("timeout", 42.0, {"connect": 3.0})
    assert client.kwargs["max_retries"] == 7


def test_a_keyless_local_endpoint_still_constructs():
    """Ollama authenticates nothing, but the SDK refuses an empty key."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install_fake_sdk(monkeypatch)
        client = OpenAIProvider(_config(provider="ollama", api_key=""))._create_client()
    assert client.kwargs["api_key"]


def test_the_client_is_built_once_and_reused():
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install_fake_sdk(monkeypatch)
        provider = OpenAIProvider(_config())
        assert provider._client_or_create() is provider._client_or_create()


def test_a_missing_sdk_is_a_provider_error_not_an_import_error():
    """Every backend problem reaches the caller as this layer's exception."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setitem(sys.modules, "openai", None)
        with pytest.raises(ProviderError, match="openai"):
            OpenAIProvider(_config())._create_client()
