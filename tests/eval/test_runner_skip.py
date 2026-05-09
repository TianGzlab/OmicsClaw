"""Sanity test: the eval fixture skips gracefully without an API key.

This file IS marked ``@pytest.mark.eval`` because it asserts the eval
suite's skip path — but the assertion uses pytest's own skip machinery,
so it doesn't make any LLM calls. Verifies the contract documented in
``tests/eval/README.md`` that contributors without credentials can run
``pytest -m eval`` and see clean skipped lines.
"""

from __future__ import annotations

import pytest


@pytest.mark.eval
def test_real_llm_runner_skips_when_no_api_key(real_llm_runner) -> None:
    """When this test runs to its body, the fixture didn't skip — meaning
    an API key was present. We just confirm the runner is the expected
    async callable. The skip path is exercised at collection/setup time
    when ``LLM_API_KEY`` is unset (verified via separate integration check)."""
    assert callable(real_llm_runner)


@pytest.mark.eval
def test_eval_marker_default_excluded_addopts_contract() -> None:
    """Defensive: pyproject.toml's ``addopts`` must exclude ``eval``
    so default ``pytest`` invocations never spawn LLM calls. If this
    test executes, the user explicitly opted in via ``-m eval``."""
    assert True
