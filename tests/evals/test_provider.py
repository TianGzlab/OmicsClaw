"""ScriptedProvider: script order, exhaustion, the side path, bind, concurrency."""

from __future__ import annotations

import asyncio
import json

import pytest

from omicsclaw.evals import ScriptedProvider, ScriptedTurn, tool_call
from omicsclaw.provider import LLMProvider, ProviderError
from omicsclaw.schema import Message, Role, StreamChunkType, ToolDefinition, Usage

_USER = (Message(role=Role.USER, content="hi"),)
_TOOLS = (ToolDefinition(name="read_file", description="read"),)


def test_it_satisfies_the_provider_protocol():
    assert isinstance(ScriptedProvider(), LLMProvider)


def test_turns_come_back_in_order_and_every_call_is_recorded():
    provider = ScriptedProvider(ScriptedTurn(text="one"), ScriptedTurn(text="two"))

    first = asyncio.run(provider.generate(_USER, _TOOLS))
    second = asyncio.run(provider.generate(_USER, _TOOLS))

    assert (first.message.content, second.message.content) == ("one", "two")
    assert provider.turn_index == 2
    assert [call.tools for call in provider.calls] == [("read_file",), ("read_file",)]
    assert provider.calls[0].messages == _USER


def test_a_tool_turn_reports_tool_use_and_a_text_turn_end_turn():
    provider = ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "a"}),)),
        ScriptedTurn(text="done"),
    )
    acting = asyncio.run(provider.generate(_USER, _TOOLS))
    answering = asyncio.run(provider.generate(_USER, _TOOLS))
    assert acting.finish_reason == "tool_use"
    assert acting.message.is_action
    assert answering.finish_reason == "end_turn"


def test_an_exhausted_script_converges_by_default_and_counts_it():
    provider = ScriptedProvider(ScriptedTurn(text="only"), exhausted_text="fallback")
    asyncio.run(provider.generate(_USER, _TOOLS))
    extra = asyncio.run(provider.generate(_USER, _TOOLS))
    assert extra.message.content == "fallback"
    assert not extra.message.tool_calls
    assert provider.exhausted == 1


def test_an_exhausted_script_can_raise_instead():
    provider = ScriptedProvider(on_exhausted="raise")
    with pytest.raises(ProviderError) as raised:
        asyncio.run(provider.generate(_USER, _TOOLS))
    assert raised.value.status_code == 400


def test_on_exhausted_must_be_one_of_two_values():
    with pytest.raises(ValueError):
        ScriptedProvider(on_exhausted="loop")


def test_a_scripted_error_is_raised_on_both_paths():
    boom = ProviderError("down", status_code=503)
    blocking = ScriptedProvider(ScriptedTurn(err=boom))
    with pytest.raises(ProviderError):
        asyncio.run(blocking.generate(_USER, _TOOLS))

    streaming = ScriptedProvider(ScriptedTurn(err=boom))

    async def drain() -> None:
        async for _ in streaming.generate_stream(_USER, _TOOLS):
            pass

    with pytest.raises(ProviderError):
        asyncio.run(drain())


def test_the_stream_is_one_done_chunk_with_message_and_usage():
    provider = ScriptedProvider(ScriptedTurn(text="streamed"), usage=Usage(input_tokens=7, output_tokens=3))

    async def collect():
        return [chunk async for chunk in provider.generate_stream(_USER, _TOOLS)]

    chunks = asyncio.run(collect())
    assert [chunk.type for chunk in chunks] == [StreamChunkType.DONE]
    assert chunks[0].message.content == "streamed"
    assert chunks[0].usage == Usage(input_tokens=7, output_tokens=3)
    assert chunks[0].finish_reason == "end_turn"


def test_calls_without_tools_take_the_side_replies_and_leave_the_script_alone():
    provider = ScriptedProvider(
        ScriptedTurn(text="main"),
        side_replies=("summary one",),
        side_default="later",
    )
    first_side = asyncio.run(provider.generate(_USER, None))
    second_side = asyncio.run(provider.generate(_USER, None))
    main = asyncio.run(provider.generate(_USER, _TOOLS))

    assert (first_side.message.content, second_side.message.content) == ("summary one", "later")
    assert main.message.content == "main"
    assert len(provider.side_calls) == 2
    assert len(provider.calls) == 1
    assert provider.side_calls[0].tools == ()


def test_a_bound_view_shares_the_script_and_the_records():
    provider = ScriptedProvider(ScriptedTurn(text="a"), ScriptedTurn(text="b"))
    view = provider.bind(model="cheap")

    asyncio.run(view.generate(_USER, _TOOLS))
    reply = asyncio.run(provider.generate(_USER, _TOOLS))

    assert reply.message.content == "b"
    assert provider.calls[0].bound == {"model": "cheap"}
    assert provider.calls[1].bound == {}
    assert view.calls == provider.calls


def test_concurrent_callers_never_receive_the_same_turn():
    provider = ScriptedProvider(*(ScriptedTurn(text=str(i)) for i in range(50)))

    async def many():
        return await asyncio.gather(*(provider.generate(_USER, _TOOLS) for _ in range(50)))

    replies = asyncio.run(many())
    assert sorted(int(r.message.content) for r in replies) == list(range(50))


def test_reset_rewinds_the_script_and_clears_the_records():
    provider = ScriptedProvider(ScriptedTurn(text="first"))
    asyncio.run(provider.generate(_USER, _TOOLS))
    asyncio.run(provider.generate(_USER, None))
    provider.reset()
    assert provider.turn_index == 0
    assert provider.calls == () and provider.side_calls == ()
    again = asyncio.run(provider.generate(_USER, _TOOLS))
    assert again.message.content == "first"


def test_tool_call_encodes_a_mapping_and_the_provider_numbers_missing_ids():
    call = tool_call("read_file", {"path": "x"})
    assert json.loads(call.arguments) == {"path": "x"}
    assert tool_call("bash", '{"command": "ls"}').arguments == '{"command": "ls"}'

    def script():
        return ScriptedProvider(
            ScriptedTurn(tool_calls=(tool_call("a", {}), tool_call("b", {}, id="mine"))),
            ScriptedTurn(tool_calls=(tool_call("c", {}),)),
        )

    for _ in range(2):
        provider = script()
        first = asyncio.run(provider.generate(_USER, _TOOLS))
        second = asyncio.run(provider.generate(_USER, _TOOLS))
        ids = [c.id for c in first.message.tool_calls + second.message.tool_calls]
        assert ids == ["call_1", "mine", "call_2"]
