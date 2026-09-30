"""compaction: offloading a large result at WARN, summarizing the head at FULL.

Both cases size the window with a ``Headroom``. The ``trigger_tokens``
values are the growth the token estimator reports for these scripts,
rounded down a little so the trigger call lands inside the target tier
and no compaction writes back before the trigger call. If the estimator
changes, the compaction records' ``pressure`` shows which way the tier
moved, and the Runner's ``headroom_missed`` names a compaction that came
too early.

``summary_replaces_head`` reaches ``FULL`` by reading two tables in one
turn after three small reads. The first call's baseline is about 10k
tokens (the full skill index), so ``FULL`` needs more than a third of
that in growth; one table (about 2k tokens) is not enough.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from omicsclaw.context import COMPACTION_MARKER, OFFLOAD_MARKER, Pressure, offload_key
from omicsclaw.evals import Headroom, NoError, ScriptedProvider, ScriptedTurn, ToolCalled, tool_call
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.builtin.read import read_tool

from ._checks import CountIs, SentContains
from ._harness import check, seed


def _table(tag: str, rows: int = 400) -> str:
    header = "gene\t" + "\t".join(f"sample_{j}" for j in range(1, 8))
    body = [
        f"{tag}{i:04d}\t" + "\t".join(f"{(i * 7 + j * 13 + len(tag)) % 1000 / 10:.1f}" for j in range(1, 8))
        for i in range(rows)
    ]
    return "\n".join([header, *body]) + "\n"


BIG_TABLE = _table("GENE")
SMALL_NOTE = "".join(f"note {k}: clustering at resolution 1.0 kept 12 clusters.\n" for k in range(12))


def _offload_reference(path: str, content: str, call_id: str) -> str:
    """Where the offloader will keep *call_id*'s ``read_file`` result for *path*."""
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / path
        target.parent.mkdir(parents=True)
        target.write_text(content, encoding="utf-8")
        output = asyncio.run(read_tool(Workspace(Path(scratch))).execute(json.dumps({"path": path})))
    return f".omicsclaw/tool_results/eval/{offload_key(call_id, output)}.txt"


OFFLOADED = _offload_reference("data/big_table.tsv", BIG_TABLE, "call_1")

SUMMARY = (
    "### User Intent\nReview two expression tables.\n\n"
    "### Execution Progress\nRead small.txt three times, then data/a.tsv and data/b.tsv.\n\n"
    "### Next Steps\nCompare the two tables.\n\n"
    "## Summary\nThe user asked for a review of two tables; both were read (SUMMARY-SEVEN)."
)


def _large_result_offloaded():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "data/big_table.tsv"}),)),
        *(ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "small.txt"}),)) for _ in range(3)),
        ScriptedTurn(tool_calls=(tool_call("read_file", {"path": OFFLOADED}),)),
        ScriptedTurn(text="The table has 400 genes."),
    )


def _summary_replaces_head():
    return ScriptedProvider(
        *(ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "small.txt"}),)) for _ in range(3)),
        ScriptedTurn(
            tool_calls=(
                tool_call("read_file", {"path": "data/a.tsv"}),
                tool_call("read_file", {"path": "data/b.tsv"}),
            )
        ),
        ScriptedTurn(text="Both tables reviewed."),
        side_replies=(SUMMARY,),
    )


def _at(pressure: Pressure, *, written_back: bool = True):
    return lambda r: sum(
        1 for record in r.compactions if record.pressure is pressure and record.written_back is written_back
    )


def _offloaded(result) -> int:
    """Written-back compactions that offloaded something.

    A record's ``pressure`` is the tier measured after offloading, so a
    compaction that only offloads records ``NONE`` even though ``WARN``
    triggered it.
    """
    return sum(1 for record in result.compactions if record.written_back and record.offloaded)


def _table_reads(result) -> int:
    """``read_file`` results carrying table rows: the first read and the retrieval."""
    return sum(1 for item in result.tool_results if "GENE0050\t" in item.output)


CASES = [
    seed(
        "compaction/large_result_offloaded",
        "Read data/big_table.tsv and the notes.",
        _large_result_offloaded,
        SentContains(OFFLOAD_MARKER, call=4),
        SentContains(OFFLOADED, call=4),
        CountIs("offloading compactions written back", _offloaded, 1, at_least=True),
        CountIs("placeholders before call 4", lambda r: sum(
            OFFLOAD_MARKER in m.content for c in r.provider_calls[:4] for m in c.messages), 0),
        ToolCalled("read_file", min_times=5),
        CountIs("read_file results showing the table", _table_reads, 2),
        NoError(),
        compaction=True,
        headroom=Headroom(target=Pressure.WARN, trigger_call=4, trigger_tokens=2600),
        files={"data/big_table.tsv": BIG_TABLE, "small.txt": SMALL_NOTE},
        config={"memory": False},
    ),
    seed(
        "compaction/summary_replaces_head",
        "Review data/a.tsv and data/b.tsv.",
        _summary_replaces_head,
        SentContains((COMPACTION_MARKER, "## Summary", "SUMMARY-SEVEN"), call=4),
        CountIs("system message first on call 4", lambda r: int(r.provider_calls[4].messages[0].role == "system"), 1),
        CountIs("FULL compactions written back", _at(Pressure.FULL), 1),
        CountIs("summarizer calls", lambda r: len(r.side_calls), 1),
        NoError(),
        compaction=True,
        headroom=Headroom(target=Pressure.FULL, trigger_call=4, trigger_tokens=4700),
        files={"data/a.tsv": _table("ALPHA"), "data/b.tsv": _table("BETA"), "small.txt": SMALL_NOTE},
        config={"memory": False},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
