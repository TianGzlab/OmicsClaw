"""Tests for transcript and tool-result storage boundaries."""

from omicsclaw.runtime.tool_result_store import ToolResultStore
from omicsclaw.runtime.tool_spec import (
    RESULT_POLICY_KNOWLEDGE_REFERENCE,
    ToolSpec,
)
from omicsclaw.runtime.transcript_store import (
    AdvisoryEventRef,
    CompactedToolResultRef,
    PlanReference,
    TranscriptReplaySummary,
    TranscriptStore,
    build_selective_replay_context,
    build_selective_replay_summary,
    build_transcript_summary,
    extract_compacted_tool_result_refs,
    sanitize_tool_history,
)


def test_transcript_store_prepares_history_and_drops_incomplete_tool_bundle():
    store = TranscriptStore(max_history=10, max_conversations=10, sanitizer=sanitize_tool_history)
    chat_id = "chat-1"

    store.append_user_message(chat_id, "do two things")
    store.append_assistant_message(
        chat_id,
        content="",
        tool_calls=[
            {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
            {"id": "call_2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
        ],
    )
    store.append_tool_message(chat_id, tool_call_id="call_1", content="result 1")
    store.append_assistant_message(chat_id, content="next turn")

    history = store.prepare_history(chat_id)

    assert history == [
        {"role": "user", "content": "do two things"},
        {"role": "assistant", "content": "next turn"},
    ]


def test_transcript_store_evicts_lru_conversations():
    store = TranscriptStore(max_history=10, max_conversations=2, sanitizer=sanitize_tool_history)
    store.append_user_message("chat-1", "hi")
    store.append_user_message("chat-2", "hi")
    store.append_user_message("chat-3", "hi")
    store.touch("chat-1", at=1.0)
    store.touch("chat-2", at=2.0)
    store.touch("chat-3", at=3.0)

    evicted = store.evict_lru_conversations()

    assert evicted == ["chat-1"]
    assert "chat-1" not in store.messages_by_chat
    assert set(store.messages_by_chat) == {"chat-2", "chat-3"}


def test_tool_result_store_records_and_clears_results(tmp_path):
    store = ToolResultStore(storage_dir=tmp_path / "tool_results")

    record = store.record(
        chat_id="chat-1",
        tool_call_id="call-1",
        tool_name="inspect_data",
        output={"status": "ok"},
        success=True,
    )

    assert record.chat_id == "chat-1"
    assert record.tool_call_id == "call-1"
    assert record.tool_name == "inspect_data"
    assert record.content == "{'status': 'ok'}"
    assert record.success is True
    assert record.output_bytes > 0
    assert record.is_compacted is False
    assert store.get_records("chat-1") == [record]

    store.clear("chat-1")
    assert store.get_records("chat-1") == []


def test_tool_result_store_compacts_large_results_to_disk(tmp_path):
    store = ToolResultStore(
        storage_dir=tmp_path / "tool_results",
        inline_bytes=64,
        preview_chars=16,
    )
    output = "X" * 200

    record = store.record(
        chat_id="chat-1",
        tool_call_id="call-1",
        tool_name="inspect_data",
        output=output,
        success=True,
    )

    assert record.is_compacted is True
    assert "[tool result compacted]" in record.content
    assert "full_result_path:" in record.content
    assert record.storage_path != ""
    assert store.load_full_content(record) == output

    store.clear("chat-1")
    assert not (tmp_path / "tool_results" / "chat-1").exists()


def test_tool_result_store_uses_policy_specific_compaction_and_head_tail_preview(tmp_path):
    store = ToolResultStore(
        storage_dir=tmp_path / "tool_results",
        inline_bytes=6000,
        preview_chars=400,
    )
    spec = ToolSpec(
        name="consult_knowledge",
        description="knowledge",
        parameters={"type": "object", "properties": {}},
        result_policy=RESULT_POLICY_KNOWLEDGE_REFERENCE,
    )
    output = ("HEADER\n" + ("A" * 2600) + "\nTAIL\n" + ("Z" * 1200))

    record = store.record(
        chat_id="chat-2",
        tool_call_id="call-knowledge",
        tool_name="consult_knowledge",
        output=output,
        success=True,
        spec=spec,
    )

    assert record.result_policy == RESULT_POLICY_KNOWLEDGE_REFERENCE
    assert record.is_compacted is True
    assert "policy: knowledge_reference" in record.content
    assert "HEADER" in record.content
    assert "TAIL" in record.content
    assert "\n...\n" in record.content
    assert store.load_full_content(record) == output


def test_extract_compacted_tool_result_refs_parses_runtime_references():
    refs = extract_compacted_tool_result_refs(
        [
            {"role": "user", "content": "hello"},
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": (
                    "[tool result compacted]\n"
                    "tool: inspect_data\n"
                    "bytes: 5120\n"
                    "full_result_path: /tmp/tool_results/chat-1/result.txt\n"
                    "preview:\n"
                    "first lines"
                ),
            },
            {"role": "tool", "tool_call_id": "call-2", "content": "small output"},
        ]
    )

    assert refs == [
        CompactedToolResultRef(
            tool_call_id="call-1",
            tool_name="inspect_data",
            storage_path="/tmp/tool_results/chat-1/result.txt",
            output_bytes=5120,
        )
    ]


def test_build_transcript_summary_collects_compacted_plan_and_advisory_refs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan_path = workspace / "plan.md"
    plan_path.write_text("# plan\n", encoding="utf-8")

    summary = build_transcript_summary(
        [
            {"role": "user", "content": "hello"},
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": (
                    "[tool result compacted]\n"
                    "tool: inspect_data\n"
                    "bytes: 5120\n"
                    "full_result_path: /tmp/tool_results/chat-1/result.txt\n"
                    "preview:\n"
                    "first lines"
                ),
            },
            {"role": "assistant", "content": "💡 Advice:\nUse QC thresholds from the protocol."},
        ],
        metadata={"pipeline_workspace": str(workspace)},
    )

    assert summary.compacted_tool_results == (
        CompactedToolResultRef(
            tool_call_id="call-1",
            tool_name="inspect_data",
            storage_path="/tmp/tool_results/chat-1/result.txt",
            output_bytes=5120,
        ),
    )
    assert summary.plan_references == (
        PlanReference(
            path=str(plan_path.resolve()),
            workspace=str(workspace.resolve()),
            exists=True,
        ),
    )
    assert summary.advisory_events == (
        AdvisoryEventRef(
            message="💡 Advice:\nUse QC thresholds from the protocol.",
            role="assistant",
            index=2,
            kind="advisory",
        ),
    )


def test_transcript_store_prepare_history_uses_budget_aware_suffix():
    store = TranscriptStore(
        max_history=3,
        max_conversations=10,
        sanitizer=sanitize_tool_history,
    )
    chat_id = "chat-budget"

    store.messages_by_chat[chat_id] = [
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

    history = store.prepare_history(chat_id)

    assert history == [
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


def test_transcript_store_prepare_history_preserves_full_sanitized_transcript():
    store = TranscriptStore(
        max_history=2,
        max_conversations=10,
        sanitizer=sanitize_tool_history,
    )
    chat_id = "chat-preserve"
    store.messages_by_chat[chat_id] = [
        {"role": "user", "content": "older user"},
        {"role": "assistant", "content": "older answer"},
        {"role": "user", "content": "latest user"},
        {"role": "assistant", "content": "latest answer"},
    ]

    history = store.prepare_history(chat_id)

    assert history == [
        {"role": "user", "content": "latest user"},
        {"role": "assistant", "content": "latest answer"},
    ]
    assert store.get_history(chat_id) == [
        {"role": "user", "content": "older user"},
        {"role": "assistant", "content": "older answer"},
        {"role": "user", "content": "latest user"},
        {"role": "assistant", "content": "latest answer"},
    ]


def test_build_selective_replay_summary_captures_omitted_structured_refs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "plan.md").write_text("# plan\n", encoding="utf-8")

    history = [
        {"role": "user", "content": "older request"},
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
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": (
                "[tool result compacted]\n"
                "tool: inspect_data\n"
                "bytes: 5120\n"
                f"full_result_path: {tmp_path / 'tool_results' / 'chat-1' / 'result.txt'}\n"
                "preview:\n"
                "first lines"
            ),
        },
        {"role": "assistant", "content": "💡 Advice:\nUse QC thresholds from the protocol."},
        {"role": "user", "content": "latest question"},
        {"role": "assistant", "content": "latest answer"},
    ]

    replay = build_selective_replay_summary(
        history,
        metadata={"pipeline_workspace": str(workspace)},
        max_messages=2,
        sanitizer=sanitize_tool_history,
    )

    assert replay == TranscriptReplaySummary(
        omitted_message_count=4,
        compacted_tool_results=(
            CompactedToolResultRef(
                tool_call_id="call-1",
                tool_name="inspect_data",
                storage_path=str(tmp_path / "tool_results" / "chat-1" / "result.txt"),
                output_bytes=5120,
            ),
        ),
        plan_references=(
            PlanReference(
                path=str((workspace / "plan.md").resolve()),
                workspace=str(workspace.resolve()),
                exists=True,
            ),
        ),
        advisory_events=(
            AdvisoryEventRef(
                message="💡 Advice:\nUse QC thresholds from the protocol.",
                role="assistant",
                index=3,
                kind="advisory",
            ),
        ),
    )

    context = build_selective_replay_context(
        history,
        metadata={"pipeline_workspace": str(workspace)},
        max_messages=2,
        sanitizer=sanitize_tool_history,
    )
    assert "## Selective Transcript Replay" in context
    assert "4 older message(s)" in context
    assert "inspect_data" in context
    assert "Use QC thresholds from the protocol." in context
