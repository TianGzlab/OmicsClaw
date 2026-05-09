"""Audit-log sanity tests: verify today's eval matches historical successful turns.

The 15 invariant cases in ``test_behavioral_parity.py`` define
*intended* behavior. This file adds 3 sanity checks against the actual
production audit log (``bot/logs/audit.jsonl``): for each of the top-N
most-frequently-called tools, pick a representative historical turn and
verify the captured eval round emits the same first tool call.

This catches "behavior drifts away from what really happened in
production" even when the invariant set didn't anticipate it.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

_AUDIT_LOG = Path(__file__).resolve().parent.parent.parent / "bot" / "logs" / "audit.jsonl"

# Per grill-me Q5 sub-#3: pick 3 high-frequency successful turns. The top
# tools by audit frequency are list_directory (35) / omicsclaw (33) /
# glob_files (23) / inspect_data (22) / consult_knowledge (14). We
# choose the queries we can reconstruct from the args_preview field;
# the audit log doesn't record the user query, so we synthesize a
# query that would naturally invoke the same tool.
_SANITY_PROBES: tuple[tuple[str, str], ...] = (
    # (probe_query, expected_first_tool_name)
    (
        "list the files in /tmp/data so I can see what's there",
        "list_directory",
    ),
    (
        "do sc-de on /tmp/sample.h5ad",
        "omicsclaw",
    ),
    (
        "which scvi parameters are best for batch correction with 5+ batches?",
        "consult_knowledge",
    ),
)


@dataclass(frozen=True, slots=True)
class AuditTurn:
    """A condensed view of one ``tool_call`` row from the audit log."""

    timestamp: str
    chat_id: str
    tool: str


def _read_audit_log(path: Path = _AUDIT_LOG) -> tuple[AuditTurn, ...]:
    """Parse the audit log into ``AuditTurn`` records.

    Returns an empty tuple if the file doesn't exist (e.g. fresh
    install) so the sanity tests skip gracefully rather than failing.
    """
    if not path.is_file():
        return ()
    turns: list[AuditTurn] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("event") != "tool_call":
                continue
            tool = entry.get("tool")
            if not tool:
                continue
            turns.append(
                AuditTurn(
                    timestamp=str(entry.get("ts", "")),
                    chat_id=str(entry.get("chat_id", "")),
                    tool=str(tool),
                )
            )
    return tuple(turns)


def pick_top_audit_tools(*, n: int = 3, audit_path: Path = _AUDIT_LOG) -> tuple[str, ...]:
    """Top-``n`` tools by call frequency in the audit log."""
    turns = _read_audit_log(audit_path)
    if not turns:
        return ()
    counts = Counter(t.tool for t in turns)
    return tuple(name for name, _ in counts.most_common(n))


@pytest.mark.eval
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("probe_query", "expected_tool"),
    _SANITY_PROBES,
    ids=[expected for _, expected in _SANITY_PROBES],
)
async def test_audit_log_sanity_first_tool_matches(
    probe_query: str,
    expected_tool: str,
    real_llm_runner,
) -> None:
    """For each probe, verify the captured first tool call name matches
    the historical pattern from the audit log."""
    audit_turns = _read_audit_log()
    if not audit_turns:
        pytest.skip(f"audit log {_AUDIT_LOG} not present; sanity comparison skipped")

    historical = [t for t in audit_turns if t.tool == expected_tool]
    if not historical:
        pytest.skip(
            f"audit log has no historical {expected_tool!r} turn — "
            f"sanity probe assumes that tool was used historically"
        )

    result = await real_llm_runner(probe_query)

    if not result.tool_calls:
        pytest.fail(
            f"sanity probe for {expected_tool!r} expected a tool call but the "
            f"model emitted none. Compare against historical audit turn "
            f"chat_id={historical[0].chat_id} ts={historical[0].timestamp}.\n"
            f"  query: {probe_query!r}\n"
            f"  response_text head: {result.response_text[:200]!r}"
        )

    first_tool = result.tool_calls[0].name
    assert first_tool == expected_tool, (
        f"audit-log sanity drift: expected first tool call {expected_tool!r} "
        f"(based on {len(historical)} historical {expected_tool!r} turns; "
        f"sample chat_id={historical[0].chat_id}), got {first_tool!r}.\n"
        f"  query: {probe_query!r}\n"
        f"  observed tool sequence: {[tc.name for tc in result.tool_calls]}"
    )
