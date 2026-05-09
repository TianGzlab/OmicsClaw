"""Pure-Python tests for the audit-log helper used by sanity probes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.audit_log_sanity import (
    AuditTurn,
    _read_audit_log,
    pick_top_audit_tools,
)


def _write_minimal_log(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_read_audit_log_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert _read_audit_log(tmp_path / "missing.jsonl") == ()


def test_read_audit_log_parses_tool_call_rows(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    _write_minimal_log(
        log,
        [
            {"ts": "2026-01-01T00:00:00Z", "event": "tool_call", "chat_id": "c1", "tool": "list_directory"},
            {"ts": "2026-01-01T00:01:00Z", "event": "tool_call", "chat_id": "c2", "tool": "omicsclaw"},
            {"ts": "2026-01-01T00:02:00Z", "event": "session_start", "chat_id": "c3"},
        ],
    )
    turns = _read_audit_log(log)
    assert len(turns) == 2
    assert all(isinstance(t, AuditTurn) for t in turns)
    assert {t.tool for t in turns} == {"list_directory", "omicsclaw"}


def test_read_audit_log_skips_malformed_lines(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    log.write_text(
        '{"event": "tool_call", "tool": "list_directory", "chat_id": "c1", "ts": "t1"}\n'
        "this line is not json\n"
        '{"event": "tool_call", "tool": "omicsclaw", "chat_id": "c2", "ts": "t2"}\n',
        encoding="utf-8",
    )
    turns = _read_audit_log(log)
    assert len(turns) == 2


def test_read_audit_log_skips_tool_call_without_name(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    _write_minimal_log(
        log,
        [
            {"event": "tool_call", "chat_id": "c1"},  # missing 'tool'
            {"event": "tool_call", "tool": "", "chat_id": "c2"},  # empty 'tool'
            {"event": "tool_call", "tool": "omicsclaw", "chat_id": "c3"},
        ],
    )
    turns = _read_audit_log(log)
    assert [t.tool for t in turns] == ["omicsclaw"]


def test_pick_top_audit_tools_orders_by_frequency(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    _write_minimal_log(
        log,
        [
            {"event": "tool_call", "tool": "omicsclaw", "chat_id": "c", "ts": "t"},
            {"event": "tool_call", "tool": "omicsclaw", "chat_id": "c", "ts": "t"},
            {"event": "tool_call", "tool": "omicsclaw", "chat_id": "c", "ts": "t"},
            {"event": "tool_call", "tool": "list_directory", "chat_id": "c", "ts": "t"},
            {"event": "tool_call", "tool": "list_directory", "chat_id": "c", "ts": "t"},
            {"event": "tool_call", "tool": "consult_knowledge", "chat_id": "c", "ts": "t"},
        ],
    )
    top3 = pick_top_audit_tools(n=3, audit_path=log)
    assert top3 == ("omicsclaw", "list_directory", "consult_knowledge")


def test_pick_top_audit_tools_returns_empty_on_missing_log(tmp_path: Path) -> None:
    assert pick_top_audit_tools(n=3, audit_path=tmp_path / "missing.jsonl") == ()
