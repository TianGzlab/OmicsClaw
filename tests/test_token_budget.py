from omicsclaw.runtime.token_budget import (
    check_token_budget,
    create_token_budget_tracker,
    normalize_token_budget,
    record_completion_tokens,
)


def test_normalize_token_budget_supports_plus_and_suffix_units():
    assert normalize_token_budget("+500k") == 500_000
    assert normalize_token_budget("1.5m") == 1_500_000
    assert normalize_token_budget(2048) == 2048
    assert normalize_token_budget("0") is None


def test_check_token_budget_requests_continuation_before_completion_threshold():
    tracker = create_token_budget_tracker("1000")

    record_completion_tokens(tracker, 300)
    decision = check_token_budget(tracker)

    assert decision.action == "continue"
    assert decision.turn_tokens == 300
    assert "Continue working on the same request." in decision.nudge_message


def test_check_token_budget_stops_after_continuations_when_budget_is_met():
    tracker = create_token_budget_tracker("1000")

    record_completion_tokens(tracker, 200)
    first = check_token_budget(tracker)
    assert first.action == "continue"

    record_completion_tokens(tracker, 800)
    second = check_token_budget(tracker)

    assert second.action == "stop"
    assert second.completion_event is not None
    assert second.completion_event["turn_tokens"] == 1000
