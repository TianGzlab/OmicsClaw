from omicsclaw.runtime.context_compaction import (
    STAGE_AUTO_COMPACT,
    STAGE_CONTEXT_COLLAPSE,
    STAGE_MICRO_COMPACT,
    STAGE_SNIP_COMPACT,
    ContextCompactionConfig,
    prepare_model_messages,
)
from omicsclaw.runtime.tool_result_store import ToolResultStore


def test_prepare_model_messages_applies_snip_and_micro_before_heavy_stages(tmp_path):
    result_store = ToolResultStore(
        storage_dir=tmp_path / "tool_results",
        inline_bytes=64,
        preview_chars=1200,
    )
    record = result_store.record(
        chat_id="chat-light",
        tool_call_id="call-1",
        tool_name="inspect_data",
        output="X" * 1200,
        success=True,
    )

    prepared = prepare_model_messages(
        system_prompt="SYSTEM",
        history=[
            {"role": "user", "content": "older user " + ("A" * 1200)},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "inspect_data",
                            "arguments": '{"payload":"' + ("B" * 1200) + '"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": record.content},
            {"role": "user", "content": "latest request"},
        ],
        chat_id="chat-light",
        tool_result_store=result_store,
        config=ContextCompactionConfig(
            max_prompt_chars=50_000,
            snip_message_chars=240,
            snip_tool_argument_chars=180,
            protected_tail_messages=1,
            micro_keep_recent_tool_messages=0,
            collapse_trigger_ratio=0.95,
            auto_compact_trigger_ratio=0.99,
        ),
    )

    assert prepared.applied_stages == (STAGE_SNIP_COMPACT, STAGE_MICRO_COMPACT)
    assert "## Context Collapse" not in prepared.system_prompt
    assert "snip compacted older message" in prepared.messages[0]["content"]
    assert "snip compacted older tool arguments" in prepared.messages[1]["tool_calls"][0]["function"]["arguments"]
    assert "[tool result micro-compacted]" in prepared.messages[2]["content"]


def test_prepare_model_messages_runs_context_collapse_before_auto_compact(tmp_path):
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    history = []
    for index in range(8):
        history.append({"role": "user", "content": f"user step {index} " + ("A" * 180)})
        history.append({"role": "assistant", "content": f"assistant step {index} " + ("B" * 180)})

    prepared = prepare_model_messages(
        system_prompt="SYSTEM",
        history=history,
        chat_id="chat-collapse",
        tool_result_store=result_store,
        config=ContextCompactionConfig(
            max_prompt_chars=4_000,
            snip_message_chars=4_000,
            protected_tail_messages=2,
            collapse_trigger_ratio=0.45,
            auto_compact_trigger_ratio=0.75,
            collapse_preserve_messages=4,
            collapse_preserve_chars=600,
            auto_compact_preserve_messages=2,
            auto_compact_preserve_chars=240,
        ),
    )

    assert STAGE_CONTEXT_COLLAPSE in prepared.applied_stages
    assert STAGE_AUTO_COMPACT not in prepared.applied_stages
    assert "## Context Collapse" in prepared.system_prompt
    assert len(prepared.messages) <= 4


def test_prepare_model_messages_runs_auto_compact_when_collapse_is_not_enough(tmp_path):
    result_store = ToolResultStore(storage_dir=tmp_path / "tool_results")
    history = []
    for index in range(10):
        history.append({"role": "user", "content": f"user step {index} " + ("A" * 260)})
        history.append({"role": "assistant", "content": f"assistant step {index} " + ("B" * 260)})

    prepared = prepare_model_messages(
        system_prompt="SYSTEM",
        history=history,
        chat_id="chat-auto",
        tool_result_store=result_store,
        config=ContextCompactionConfig(
            max_prompt_chars=2_200,
            snip_message_chars=4_000,
            protected_tail_messages=2,
            collapse_trigger_ratio=0.35,
            auto_compact_trigger_ratio=0.55,
            collapse_preserve_messages=8,
            collapse_preserve_chars=1_200,
            auto_compact_preserve_messages=2,
            auto_compact_preserve_chars=220,
        ),
    )

    assert STAGE_CONTEXT_COLLAPSE in prepared.applied_stages
    assert STAGE_AUTO_COMPACT in prepared.applied_stages
    assert "## Auto Compacted Context" in prepared.system_prompt
    assert len(prepared.messages) <= 2
