"""Building and running seed cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omicsclaw.evals import Assertion, Case, NoWriteOutside, Result, run_case


def seed(case_id: str, prompt: str, provider: Any, *assertions: Assertion, **fields: Any) -> Case:
    """A :class:`~omicsclaw.evals.Case` whose category is its id prefix.

    ``NoWriteOutside()`` is added unless the case states its own
    ``NoWriteOutside``.
    """
    checks = tuple(assertions)
    if not any(isinstance(check, NoWriteOutside) for check in checks):
        checks += (NoWriteOutside(),)
    return Case(
        id=case_id,
        category=case_id.split("/", 1)[0],
        prompt=prompt,
        provider=provider,
        assertions=checks,
        **fields,
    )


def check(case: Case, tmp_path: Path, results: list[Result], *, timeout_s: float | None = None) -> Result:
    """Run *case*, hand its result to the report, and fail on any hard failure.

    :param timeout_s: The case's time limit; ``None`` keeps the Runner's default.
    """
    result = run_case(case, tmp_path) if timeout_s is None else run_case(case, tmp_path, timeout_s=timeout_s)
    results.append(result)
    if not result.passed:
        pytest.fail(
            f"{case.id}:\n" + "\n".join(f"  {failure}" for failure in result.failures),
            pytrace=False,
        )
    return result
