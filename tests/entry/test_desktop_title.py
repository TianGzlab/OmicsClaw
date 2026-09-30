"""``POST /chat/title`` as a plain function (plan 0065 §3.5).

The desktop client (``lib/session-title.ts``) sends
``{schema_version: 1, source_request_id, user_text}`` and reads either
``{schema_version: 1, title}`` or a non-2xx ``{schema_version: 1,
error: {code}}``. The codes asserted here are the ones it branches on.

``max_tokens=1024`` with thinking off is asserted because a reasoning
model given a small budget spends it all on reasoning and returns an
empty body, which would be a steady 502 rather than a title.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from omicsclaw.entry.desktop.title import MAX_TITLE_CHARS, generate_title
from omicsclaw.provider.base import Completion
from omicsclaw.schema import Message, Role

RID = "0123456789abcdef0123456789abcdef"


class Titler:
    def __init__(self, text: str = "Spatial DE in mouse brain", *, error=None, delay=0.0):
        self.text, self.error, self.delay = text, error, delay
        self.bound: list[dict] = []
        self.seen: list = []

    @property
    def name(self) -> str:
        return "titler"

    def bind(self, **overrides):
        self.bound.append(overrides)
        return self

    async def generate(self, messages, tools=None):
        self.seen.append((tuple(messages), tools))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return Completion(message=Message(role=Role.ASSISTANT, content=self.text))


def title(provider, document=None, **kwargs):
    app = SimpleNamespace(provider=provider)
    body = {"schema_version": 1, "source_request_id": RID, "user_text": "hello there"}
    if document is not None:
        body = document
    return asyncio.run(generate_title(app, body, **kwargs))


def test_a_title_is_generated_from_the_running_provider():
    provider = Titler()
    status, payload = title(provider)
    assert (status, payload) == (200, {"schema_version": 1, "title": "Spatial DE in mouse brain"})
    assert provider.bound == [{"max_tokens": 1024, "thinking_budget_tokens": 0}]
    messages, tools = provider.seen[0]
    assert tools is None
    assert [m.role for m in messages] == [Role.SYSTEM, Role.USER]
    assert messages[1].content == "hello there"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Quoted title"', "Quoted title"),
        ("\n\n  “中文标题”  \nsecond line", "中文标题"),
        ("'single'", "single"),
    ],
)
def test_the_first_line_is_taken_without_quotes(raw, expected):
    assert title(Titler(raw))[1]["title"] == expected


def test_a_long_title_is_cut():
    status, payload = title(Titler("x" * 500))
    assert status == 200 and len(payload["title"]) == MAX_TITLE_CHARS == 80


@pytest.mark.parametrize("raw", ["", "   \n  ", '""'])
def test_an_empty_answer_is_output_invalid(raw):
    assert title(Titler(raw)) == (
        502,
        {"schema_version": 1, "error": {"code": "TITLE_OUTPUT_INVALID"}},
    )


def test_a_slow_provider_is_a_timeout():
    assert title(Titler(delay=5), timeout_s=0.05) == (
        504,
        {"schema_version": 1, "error": {"code": "TITLE_TIMEOUT"}},
    )


def test_a_failing_provider_is_provider_failed():
    assert title(Titler(error=RuntimeError("boom"))) == (
        502,
        {"schema_version": 1, "error": {"code": "TITLE_PROVIDER_FAILED"}},
    )


@pytest.mark.parametrize(
    "document",
    [
        {"source_request_id": RID, "user_text": "hi"},
        {"schema_version": 2, "source_request_id": RID, "user_text": "hi"},
        {"schema_version": True, "source_request_id": RID, "user_text": "hi"},
        {"schema_version": 1, "source_request_id": "ABC", "user_text": "hi"},
        {"schema_version": 1, "source_request_id": RID.upper(), "user_text": "hi"},
        {"schema_version": 1, "source_request_id": RID, "user_text": "   "},
        {"schema_version": 1, "source_request_id": RID, "user_text": 3},
        {"schema_version": 1, "source_request_id": RID, "user_text": "x" * 4097},
    ],
)
def test_a_malformed_request_is_request_invalid(document):
    provider = Titler()
    assert title(provider, document) == (
        422,
        {"schema_version": 1, "error": {"code": "TITLE_REQUEST_INVALID"}},
    )
    assert provider.seen == []
