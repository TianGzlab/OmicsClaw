"""Tests for the AnalysisMemory display label derivation.

The desktop memory tree shows ``edge.name`` as the entry label. For
``analysis://*`` URIs, ``edge.name`` is a UUID hex chosen for write-
collision avoidance (analysis is overwrite-mode, every run needs a
unique URI). Users see entries like ``3c7a182ee7ab498ea4454a2f8465063c``
and cannot tell which dataset, when, or whether the run succeeded.

``_analysis_content_to_title`` derives a human label from the JSON
content of an AnalysisMemory row:

    <dataset_basename> · <hh:mm or yyyy-mm-dd hh:mm> · <status>

Decided in ``docs/adr/0002-derived-display-label-for-analysis-memory.md``:
- Server-local timezone for the time component
- Today → ``HH:MM``; older → ``YYYY-MM-DD HH:MM``
- Silent fallback to ``None`` on parse failure or missing fields so the
  caller can keep the existing ``edge.name`` and never render blanks
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

# Pin the test process to UTC so the function's ``astimezone()`` call —
# which uses libc's local TZ — produces deterministic strings regardless
# of the developer's or CI runner's locale. The function itself
# intentionally renders in server-local TZ in production; tests just
# fix what "local" means.
os.environ["TZ"] = "UTC"
time.tzset()

from omicsclaw.memory.compat import _analysis_content_to_title  # noqa: E402


def _analysis_payload(**overrides):
    """Build a JSON-encoded AnalysisMemory content. Tests override
    individual fields via kwargs."""
    base = {
        "memory_id": "01e28fff4cee429987c4cce68f02b6e2",
        "memory_type": "analysis",
        "created_at": "2026-05-05T04:43:47.942398Z",
        "source_dataset_id": "b16e3d05b64d49eaa6537f1891c961c1",
        "parent_analysis_id": None,
        "skill": "sc-preprocessing",
        "method": "default",
        "parameters": {
            "input": "/data/beifen/zhouwg_data/omicsclaw-workspace/data/pbmc3k_raw.h5ad",
        },
        "output_path": "",
        "status": "failed",
        "executed_at": "2026-05-05T04:43:47.942410Z",
        "duration_seconds": 0.0,
    }
    base.update(overrides)
    return json.dumps(base)


# ----------------------------------------------------------------------
# Happy path: dataset basename · time · status
# ----------------------------------------------------------------------


def test_happy_path_uses_basename_time_status():
    """Full AnalysisMemory content with today's timestamp produces the
    canonical ``<basename> · HH:MM · <status>`` label."""
    today = datetime(2026, 5, 5, 12, 43, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        executed_at="2026-05-05T12:43:00Z",
        status="completed",
    )

    title = _analysis_content_to_title(content, now=today)

    assert title == "pbmc3k_raw.h5ad · 12:43 · completed", (
        f"got {title!r}"
    )


def test_older_date_includes_full_date_in_label():
    """When executed_at is on a previous day relative to ``now``, the
    label includes the date so the user can tell apart runs from
    different days at the same clock-time."""
    now = datetime(2026, 5, 10, 9, 0, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        executed_at="2026-05-05T12:43:00Z",
        status="failed",
    )

    title = _analysis_content_to_title(content, now=now)

    assert title == "pbmc3k_raw.h5ad · 2026-05-05 12:43 · failed", (
        f"got {title!r}"
    )


@pytest.mark.parametrize("status", ["completed", "failed", "interrupted"])
def test_each_status_value_renders_verbatim(status):
    """All three valid AnalysisMemory.status enum values appear in the
    label as-is."""
    today = datetime(2026, 5, 5, 12, 43, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        executed_at="2026-05-05T12:43:00Z",
        status=status,
    )

    title = _analysis_content_to_title(content, now=today)

    assert title is not None
    assert title.endswith(f" · {status}"), f"got {title!r}"


# ----------------------------------------------------------------------
# Dataset basename extraction
# ----------------------------------------------------------------------


def test_parameters_input_full_path_extracts_basename():
    """``parameters.input`` carrying a POSIX-style absolute path is
    reduced to its basename so the label stays short."""
    today = datetime(2026, 5, 5, 12, 43, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        parameters={"input": "/some/very/long/path/to/dataset.h5ad"},
        executed_at="2026-05-05T12:43:00Z",
        status="completed",
    )

    title = _analysis_content_to_title(content, now=today)

    assert title is not None
    assert title.startswith("dataset.h5ad · "), f"got {title!r}"


def test_parameters_input_already_a_filename_is_unchanged():
    """When ``parameters.input`` is already a bare filename (no slashes),
    the basename helper is a no-op."""
    today = datetime(2026, 5, 5, 12, 43, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        parameters={"input": "pbmc3k_raw.h5ad"},
        executed_at="2026-05-05T12:43:00Z",
        status="completed",
    )

    title = _analysis_content_to_title(content, now=today)

    assert title is not None
    assert title.startswith("pbmc3k_raw.h5ad · "), f"got {title!r}"


def test_missing_parameters_input_falls_back_to_unknown_dataset():
    """When ``parameters`` exists but lacks ``input`` (e.g., a skill
    that doesn't take an input file), the time + status portion is
    still useful — render with an ``<unknown dataset>`` placeholder
    instead of returning None."""
    today = datetime(2026, 5, 5, 12, 43, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        parameters={"foo": "bar"},
        executed_at="2026-05-05T12:43:00Z",
        status="completed",
    )

    title = _analysis_content_to_title(content, now=today)

    assert title == "<unknown dataset> · 12:43 · completed", (
        f"got {title!r}"
    )


def test_missing_parameters_dict_entirely_still_renders_with_placeholder():
    """``parameters`` key absent — still produce time+status with the
    unknown-dataset placeholder."""
    today = datetime(2026, 5, 5, 12, 43, 0, tzinfo=timezone.utc)
    content = _analysis_payload(
        parameters={},  # empty dict
        executed_at="2026-05-05T12:43:00Z",
        status="failed",
    )

    title = _analysis_content_to_title(content, now=today)

    assert title is not None
    assert "<unknown dataset>" in title


# ----------------------------------------------------------------------
# Fallback: silent None on bad input
# ----------------------------------------------------------------------


def test_non_json_content_returns_none():
    """Plain-text content (e.g., a session record decoded as text)
    is not derivable. Return None so the caller falls back to
    edge.name."""
    title = _analysis_content_to_title("not json at all")
    assert title is None


def test_empty_content_returns_none():
    title = _analysis_content_to_title("")
    assert title is None


def test_json_without_executed_at_returns_none():
    """A JSON object that lacks the load-bearing ``executed_at`` field
    is treated as not-an-analysis and falls back."""
    content = json.dumps({"skill": "sc-preprocessing", "status": "completed"})
    title = _analysis_content_to_title(content)
    assert title is None


def test_executed_at_with_invalid_format_returns_none():
    """Malformed timestamp (not ISO-8601) is unparseable; refuse to
    guess and fall back."""
    content = _analysis_payload(executed_at="not-a-timestamp")
    title = _analysis_content_to_title(content)
    assert title is None


# ----------------------------------------------------------------------
# Today-vs-older boundary
# ----------------------------------------------------------------------


def test_yesterday_renders_as_dated_label():
    """Edge of the today/older cutoff: events on the local-day before
    ``now`` get the full date format."""
    now = datetime(2026, 5, 10, 0, 30, 0, tzinfo=timezone.utc)
    yesterday = now - timedelta(days=1)
    content = _analysis_payload(
        executed_at=yesterday.isoformat().replace("+00:00", "Z"),
        status="completed",
    )

    title = _analysis_content_to_title(content, now=now)

    assert title is not None
    assert title.startswith("pbmc3k_raw.h5ad · 2026-05-09 "), f"got {title!r}"
