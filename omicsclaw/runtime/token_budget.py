from __future__ import annotations

import re
import time
from dataclasses import dataclass

TOKEN_BUDGET_COMPLETION_THRESHOLD = 0.9
TOKEN_BUDGET_DIMINISHING_THRESHOLD = 500

_TOKEN_BUDGET_RE = re.compile(
    r"^\+?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[kKmMbB]?)\s*$"
)


@dataclass(slots=True)
class TokenBudgetTracker:
    budget_tokens: int
    continuation_count: int = 0
    total_completion_tokens: int = 0
    last_delta_tokens: int = 0
    last_checked_tokens: int = 0
    started_at: float = 0.0


@dataclass(frozen=True, slots=True)
class TokenBudgetContinueDecision:
    action: str
    nudge_message: str
    continuation_count: int
    pct: int
    turn_tokens: int
    budget: int


@dataclass(frozen=True, slots=True)
class TokenBudgetStopDecision:
    action: str
    completion_event: dict[str, int | float | bool] | None


def normalize_token_budget(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None

    text = str(value).strip()
    if not text:
        return None

    match = _TOKEN_BUDGET_RE.match(text)
    if not match:
        return None

    number = float(match.group("value"))
    unit = match.group("unit").lower()
    multiplier = {
        "": 1,
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
    }[unit]
    budget = int(number * multiplier)
    return budget if budget > 0 else None


def create_token_budget_tracker(budget_tokens: int | str | None) -> TokenBudgetTracker | None:
    normalized = normalize_token_budget(budget_tokens)
    if normalized is None:
        return None
    return TokenBudgetTracker(
        budget_tokens=normalized,
        started_at=time.time(),
    )


def record_completion_tokens(
    tracker: TokenBudgetTracker | None,
    completion_tokens: int,
) -> None:
    if tracker is None or completion_tokens <= 0:
        return
    tracker.total_completion_tokens += completion_tokens


def build_budget_continuation_message(
    *,
    pct: int,
    turn_tokens: int,
    budget: int,
) -> str:
    return (
        "Continue working on the same request. "
        f"The current turn has used about {turn_tokens}/{budget} output tokens ({pct}%). "
        "Do not restart from the top or restate completed work. "
        "Continue from the next unfinished step and stop only when the task is actually complete "
        "or progress has clearly plateaued."
    )


def check_token_budget(
    tracker: TokenBudgetTracker | None,
) -> TokenBudgetContinueDecision | TokenBudgetStopDecision:
    if tracker is None or tracker.budget_tokens <= 0:
        return TokenBudgetStopDecision(action="stop", completion_event=None)

    turn_tokens = tracker.total_completion_tokens
    pct = int(round((turn_tokens / tracker.budget_tokens) * 100))
    delta_since_last_check = turn_tokens - tracker.last_checked_tokens

    is_diminishing = (
        tracker.continuation_count >= 3
        and delta_since_last_check < TOKEN_BUDGET_DIMINISHING_THRESHOLD
        and tracker.last_delta_tokens < TOKEN_BUDGET_DIMINISHING_THRESHOLD
    )

    if not is_diminishing and turn_tokens < tracker.budget_tokens * TOKEN_BUDGET_COMPLETION_THRESHOLD:
        tracker.continuation_count += 1
        tracker.last_delta_tokens = delta_since_last_check
        tracker.last_checked_tokens = turn_tokens
        return TokenBudgetContinueDecision(
            action="continue",
            nudge_message=build_budget_continuation_message(
                pct=pct,
                turn_tokens=turn_tokens,
                budget=tracker.budget_tokens,
            ),
            continuation_count=tracker.continuation_count,
            pct=pct,
            turn_tokens=turn_tokens,
            budget=tracker.budget_tokens,
        )

    if is_diminishing or tracker.continuation_count > 0:
        return TokenBudgetStopDecision(
            action="stop",
            completion_event={
                "continuation_count": tracker.continuation_count,
                "pct": pct,
                "turn_tokens": turn_tokens,
                "budget": tracker.budget_tokens,
                "diminishing_returns": is_diminishing,
                "duration_ms": int((time.time() - tracker.started_at) * 1000),
            },
        )

    return TokenBudgetStopDecision(action="stop", completion_event=None)
