from omicsclaw.runtime.context_budget import (
    estimate_message_size,
    trim_history_to_budget,
)


def test_estimate_message_size_accounts_for_text_and_tool_call_fields():
    size = estimate_message_size(
        {
            "role": "assistant",
            "content": "hello",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "inspect_data", "arguments": '{"path":"a.h5ad"}'},
                }
            ],
        }
    )

    assert size >= len("assistanthello")
    assert size >= len("call-1")
    assert size >= len("inspect_data")


def test_trim_history_to_budget_keeps_newest_contiguous_suffix():
    trimmed = trim_history_to_budget(
        [
            {"role": "user", "content": "old user"},
            {"role": "assistant", "content": "old assistant"},
            {"role": "user", "content": "latest user"},
            {"role": "assistant", "content": "latest assistant"},
        ],
        max_messages=2,
    )

    assert trimmed == [
        {"role": "user", "content": "latest user"},
        {"role": "assistant", "content": "latest assistant"},
    ]


def test_trim_history_to_budget_treats_tool_bundle_as_single_suffix_block():
    history = [
        {"role": "user", "content": "older context"},
        {"role": "assistant", "content": "older answer"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "inspect_data", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "tool output"},
        {"role": "assistant", "content": "final answer"},
    ]

    trimmed = trim_history_to_budget(history, max_messages=3)

    assert trimmed == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "inspect_data", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "tool output"},
        {"role": "assistant", "content": "final answer"},
    ]


def test_trim_history_to_budget_still_keeps_latest_block_when_char_budget_is_tiny():
    trimmed = trim_history_to_budget(
        [
            {"role": "user", "content": "older context"},
            {"role": "assistant", "content": "this response is very long and should dominate the budget"},
        ],
        max_messages=10,
        max_chars=5,
    )

    assert trimmed == [
        {
            "role": "assistant",
            "content": "this response is very long and should dominate the budget",
        }
    ]
