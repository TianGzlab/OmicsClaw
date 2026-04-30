"""Tests for omicsclaw.core.llm_patches — runtime helpers."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from omicsclaw.core.llm_patches import (
    apply_deepseek_reasoning_passback,
    discover_ollama_models,
    discover_ollama_models_async,
)


# ---------------------------------------------------------------------------
# DeepSeek passback
# ---------------------------------------------------------------------------


class TestDeepseekPassback:
    def test_injects_empty_string_when_assistant_lacks_reasoning_content(self):
        messages = [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "again"},
        ]
        out = apply_deepseek_reasoning_passback(messages)
        assert out[0]["role"] == "system"
        assert "reasoning_content" not in out[0]
        assert out[1]["role"] == "user"
        assert "reasoning_content" not in out[1]
        assert out[2]["role"] == "assistant"
        assert out[2]["reasoning_content"] == ""
        assert out[3]["role"] == "user"
        assert "reasoning_content" not in out[3]

    def test_preserves_existing_reasoning_content(self):
        messages = [
            {
                "role": "assistant",
                "content": "result",
                "reasoning_content": "I thought about it",
            }
        ]
        out = apply_deepseek_reasoning_passback(messages)
        assert out[0]["reasoning_content"] == "I thought about it"

    def test_skips_user_and_system_roles(self):
        messages = [
            {"role": "system", "content": "hi"},
            {"role": "user", "content": "ping"},
        ]
        out = apply_deepseek_reasoning_passback(messages)
        for m in out:
            assert "reasoning_content" not in m

    def test_idempotent(self):
        messages = [{"role": "assistant", "content": "x"}]
        first = apply_deepseek_reasoning_passback(messages)
        second = apply_deepseek_reasoning_passback(first)
        assert second == first

    def test_returns_new_list_does_not_mutate_caller_dicts(self):
        messages = [{"role": "assistant", "content": "x"}]
        out = apply_deepseek_reasoning_passback(messages)
        assert out is not messages
        # Original dict should not be mutated
        assert "reasoning_content" not in messages[0]

    def test_handles_empty_list(self):
        assert apply_deepseek_reasoning_passback([]) == []

    def test_handles_non_dict_items_passthrough(self):
        # Unknown items survive untouched
        weird = ["not-a-dict", {"role": "assistant", "content": "ok"}]
        out = apply_deepseek_reasoning_passback(weird)  # type: ignore[arg-type]
        assert out[0] == "not-a-dict"
        assert out[1]["reasoning_content"] == ""


# ---------------------------------------------------------------------------
# Ollama discovery (sync)
# ---------------------------------------------------------------------------


class TestDiscoverOllamaModelsSync:
    def test_returns_models_on_200(self, monkeypatch):
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "models": [{"name": "qwen2.5:7b"}, {"name": "llama3.3:70b"}]
        }
        with patch("httpx.get", return_value=fake_resp):
            assert discover_ollama_models("http://127.0.0.1:11434") == [
                "qwen2.5:7b",
                "llama3.3:70b",
            ]

    def test_returns_empty_on_404(self):
        fake_resp = MagicMock(status_code=404)
        with patch("httpx.get", return_value=fake_resp):
            assert discover_ollama_models("http://127.0.0.1:11434") == []

    def test_returns_empty_on_connection_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("nope")):
            assert discover_ollama_models("http://127.0.0.1:11434") == []

    def test_returns_empty_on_malformed_json(self):
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.side_effect = ValueError("bad json")
        with patch("httpx.get", return_value=fake_resp):
            assert discover_ollama_models("http://127.0.0.1:11434") == []

    def test_no_url_returns_empty(self):
        assert discover_ollama_models("") == []
        assert discover_ollama_models(None) == []  # type: ignore[arg-type]

    def test_strips_trailing_slash(self):
        captured = {}

        def fake_get(url, *args, **kwargs):
            captured["url"] = url
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"models": []}
            return resp

        with patch("httpx.get", side_effect=fake_get):
            discover_ollama_models("http://127.0.0.1:11434/")
        assert captured["url"] == "http://127.0.0.1:11434/api/tags"


# ---------------------------------------------------------------------------
# Ollama discovery (async)
# ---------------------------------------------------------------------------


class TestDiscoverOllamaModelsAsync:
    def test_no_url_returns_empty(self):
        assert asyncio.run(discover_ollama_models_async("")) == []

    def test_returns_empty_on_exception(self):
        async def fake_get(*args, **kwargs):
            raise httpx.ConnectError("nope")

        client = MagicMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.get = fake_get

        with patch("httpx.AsyncClient", return_value=client):
            result = asyncio.run(
                discover_ollama_models_async("http://127.0.0.1:11434")
            )
        assert result == []
