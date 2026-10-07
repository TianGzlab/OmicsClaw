"""Model request deadlines observed through the application's sessions."""

import asyncio
import sys
import time
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


def test_buffered_stream_chunks_do_not_bypass_the_deadline(tmp_path, monkeypatch):
    class BufferedStream:
        async def __aiter__(self):
            stop = asyncio.get_running_loop().time() + 0.15
            while asyncio.get_running_loop().time() < stop:
                # An SDK can drain already-buffered keepalives without suspending.
                yield {"choices": []}

        async def close(self):
            pass

    async def create(**kwargs):
        return BufferedStream()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        AsyncOpenAI=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        Timeout=lambda *args, **kwargs: None,
    ))
    provider = OpenAIProvider(ProviderConfig(provider="openai", model="test", timeout_seconds=0.05))

    async def drive():
        app = attach_sessions(build_app(AppConfig(workspace=tmp_path, memory=False), provider=provider, tools=[]))
        try:
            handle = await app.sessions.submit("buffered", "hi")
            await asyncio.wait_for(handle.wait(), 1)
            assert handle.terminal == "failed"
            assert "deadline" in str(handle.error).lower()
        finally:
            await app.aclose()

    asyncio.run(drive())


@pytest.mark.parametrize("backend", ["openai", "anthropic"])
def test_stream_ending_after_a_blocked_loop_still_exceeds_the_deadline(tmp_path, monkeypatch, backend):
    class Stream:
        closed = False

        async def __aiter__(self):
            yield {"choices": []} if backend == "openai" else {"type": "ping"}
            # The SDK reaches EOF before the event loop can run its timeout callback.
            time.sleep(0.06)

        async def close(self):
            self.closed = True

    stream = Stream()

    async def create(**kwargs):
        return stream

    endpoint = SimpleNamespace(create=create)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        AsyncOpenAI=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=endpoint)),
        Timeout=lambda *args, **kwargs: None,
    ))
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(
        AsyncAnthropic=lambda **kwargs: SimpleNamespace(messages=endpoint),
    ))
    adapter = OpenAIProvider if backend == "openai" else AnthropicProvider
    provider = adapter(ProviderConfig(provider=backend, model="test", timeout_seconds=0.02))

    async def drive():
        app = attach_sessions(build_app(AppConfig(workspace=tmp_path, memory=False), provider=provider, tools=[]))
        try:
            handle = await app.sessions.submit("late-eof", "hi")
            await asyncio.wait_for(handle.wait(), 1)
            assert handle.terminal == "failed"
            assert "deadline" in str(handle.error).lower()
            assert stream.closed
        finally:
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
