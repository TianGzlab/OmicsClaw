"""Model request deadlines observed through the application's sessions."""

import asyncio
import sys
from types import SimpleNamespace

import pytest

from omicsclaw.entry import AppConfig, build_app, run_turn
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.session import attach_sessions
from omicsclaw.provider import AnthropicProvider, OpenAIProvider, ProviderConfig, ProviderError


@pytest.mark.parametrize("backend", ["openai", "anthropic"])
@pytest.mark.parametrize("closing_hangs", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
def test_a_dribbling_response_cannot_outlive_the_request_deadline(tmp_path, monkeypatch, backend, closing_hangs, cancel):
    started = asyncio.Event()

    class Stream:
        closed = False

        async def __aiter__(self):
            started.set()
            while True:
                await asyncio.sleep(0.01)
                yield ({"choices": [{"delta": {"content": "x"}}]} if backend == "openai" else
                       {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}})

        async def close(self):
            try:
                if closing_hangs:
                    await asyncio.Event().wait()
            finally:
                self.closed = True

    stream = Stream()

    async def create(**kwargs):
        return stream

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        AsyncOpenAI=lambda **kwargs: client, Timeout=lambda *args, **kwargs: None,
    ))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(
        AsyncAnthropic=lambda **kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)),
    ))
    adapter = OpenAIProvider if backend == "openai" else AnthropicProvider
    provider = adapter(ProviderConfig(provider=backend, model="test", timeout_seconds=0.05))

    async def drive():
        app = attach_sessions(build_app(AppConfig(workspace=tmp_path, memory=False),
                                        provider=provider, tools=[]))
        try:
            handle = await app.sessions.submit("deadline", "hi")
            if cancel:
                await asyncio.wait_for(started.wait(), 1)
                handle.cancel()
            await asyncio.wait_for(handle.wait(), 1)
            assert handle.terminal == ("cancelled" if cancel else "failed")
            if not cancel:
                assert "deadline" in str(handle.error).lower()
            assert handle.stream.retained()[-1].type is TurnEventType.EXCHANGE_END
            assert stream.closed
        finally:
            handle.cancel()
            await app.aclose()

    asyncio.run(drive())


@pytest.mark.parametrize("backend", ["openai", "anthropic"])
@pytest.mark.parametrize("streaming", [False, True])
def test_waiting_for_the_first_response_has_a_deadline(tmp_path, monkeypatch, backend, streaming):
    cancelled = asyncio.Event()

    async def create(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    endpoint = SimpleNamespace(create=create)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        AsyncOpenAI=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=endpoint)),
        Timeout=lambda *args, **kwargs: None,
    ))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(
        AsyncAnthropic=lambda **kwargs: SimpleNamespace(messages=endpoint),
    ))
    adapter = OpenAIProvider if backend == "openai" else AnthropicProvider
    provider = adapter(ProviderConfig(provider=backend, model="test", timeout_seconds=0.05))

    async def drive():
        app = attach_sessions(build_app(AppConfig(workspace=tmp_path, memory=False),
                                        provider=provider, tools=[]))
        handle = None
        try:
            if streaming:
                handle = await app.sessions.submit("first", "hi")
                await asyncio.wait_for(handle.wait(), 1)
                assert handle.terminal == "failed"
                assert "deadline" in str(handle.error).lower()
            else:
                with pytest.raises(ProviderError, match="deadline"):
                    await asyncio.wait_for(run_turn(app, user_text="hi"), 1)
            assert cancelled.is_set()
        finally:
            if handle:
                handle.cancel()
            await app.aclose()

    asyncio.run(drive())
