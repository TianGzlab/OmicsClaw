"""Tests for omicsclaw.autoagent.llm_client — shared LLM utilities."""

from __future__ import annotations

import pytest

from omicsclaw.autoagent.llm_client import parse_json_from_llm, _is_retryable


# ---------------------------------------------------------------------------
# parse_json_from_llm
# ---------------------------------------------------------------------------


class TestParseJsonFromLlm:
    """Tests for the shared JSON extraction logic."""

    def test_plain_json(self):
        text = '{"params": {"theta": 1.5}, "reasoning": "ok"}'
        result = parse_json_from_llm(text)
        assert result == {"params": {"theta": 1.5}, "reasoning": "ok"}

    def test_markdown_fenced_json(self):
        text = 'Here is my suggestion:\n```json\n{"alpha": 2.0}\n```\n'
        result = parse_json_from_llm(text)
        assert result == {"alpha": 2.0}

    def test_markdown_fenced_no_language(self):
        text = '```\n{"beta": 3}\n```'
        result = parse_json_from_llm(text)
        assert result == {"beta": 3}

    def test_json_with_prose_prefix(self):
        text = 'Based on analysis, I suggest:\n{"converged": true, "reasoning": "done"}'
        result = parse_json_from_llm(text)
        assert result == {"converged": True, "reasoning": "done"}

    def test_json_with_prose_suffix(self):
        text = '{"params": {"k": 10}}\nThis should improve results.'
        result = parse_json_from_llm(text)
        assert result == {"params": {"k": 10}}

    def test_nested_json(self):
        text = '{"diffs": [{"file": "a.py", "hunks": [{"old": "x", "new": "y"}]}]}'
        result = parse_json_from_llm(text)
        assert result is not None
        assert result["diffs"][0]["file"] == "a.py"

    def test_invalid_json_returns_none(self):
        text = "This is not JSON at all."
        result = parse_json_from_llm(text)
        assert result is None

    def test_truncated_json_returns_none(self):
        text = '{"alpha": 2.0, "beta":'
        result = parse_json_from_llm(text)
        assert result is None

    def test_empty_string(self):
        assert parse_json_from_llm("") is None

    def test_whitespace_only(self):
        assert parse_json_from_llm("   \n\t  ") is None

    def test_escaped_quotes_in_json(self):
        text = '{"code": "print(\\"hello\\")"}'
        result = parse_json_from_llm(text)
        assert result is not None
        assert result["code"] == 'print("hello")'


# ---------------------------------------------------------------------------
# _is_retryable
# ---------------------------------------------------------------------------


class TestIsRetryable:
    """Tests for retry eligibility logic."""

    def test_connection_error_is_retryable(self):
        assert _is_retryable(ConnectionError("reset")) is True

    def test_timeout_error_is_retryable(self):
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_value_error_not_retryable(self):
        assert _is_retryable(ValueError("bad value")) is False

    def test_runtime_error_not_retryable(self):
        assert _is_retryable(RuntimeError("fatal")) is False

    def test_rate_limit_error_by_name(self):
        # Simulate OpenAI RateLimitError without importing openai
        exc = type("RateLimitError", (Exception,), {})("rate limited")
        assert _is_retryable(exc) is True

    def test_api_timeout_error_by_name(self):
        exc = type("APITimeoutError", (Exception,), {})("timeout")
        assert _is_retryable(exc) is True

    def test_api_connection_error_by_name(self):
        exc = type("APIConnectionError", (Exception,), {})("conn")
        assert _is_retryable(exc) is True

    def test_api_status_error_500_retryable(self):
        exc = type("APIStatusError", (Exception,), {"status_code": 502})("bad gw")
        assert _is_retryable(exc) is True

    def test_api_status_error_400_not_retryable(self):
        exc = type("APIStatusError", (Exception,), {"status_code": 400})("bad req")
        assert _is_retryable(exc) is False
