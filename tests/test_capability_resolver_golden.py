"""Golden routing snapshot for ``capability_resolver`` (OMI-12 P2.9).

The resolver's scoring weights and decision thresholds (now lifted to
module-level constants in ``omicsclaw.core.capability_resolver``) drive
which skill a natural-language query gets routed to. Adjusting any of
those weights — even reasonably — risks silently re-ranking real queries.
Without a fixed corpus to diff against, weight tuning becomes a guessing
game (see OMI-12 evaluation, P2.9).

This test pins **the current** ``chosen_skill`` / ``coverage`` /
``domain`` for ~20 representative queries spanning every domain plus the
no-skill / partial-skill / skill-creation decision boundaries.

The corpus deliberately includes a handful of *known* mis-routes
(``Run scRNA-seq preprocessing`` lands on ``spatial-preprocess``, WGCNA
lands on ``bulkrna-ppi-network``, XCMS lands on ``spatial-preprocess``).
Those are not aspirational — they pin the live behaviour so a future
weight change that silently shifts them shows up in the diff.

### Regenerating the snapshot

When you intentionally change routing behaviour, regenerate the snapshot:

    python -m scripts.update_golden_routing  # or:
    python -c "from tests.test_capability_resolver_golden import regenerate; regenerate()"

Then review the diff before committing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omicsclaw.core.capability_resolver import resolve_capability


GOLDEN_PATH = Path(__file__).parent / "fixtures" / "golden_routing" / "snapshot.json"


def _load_snapshot() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _entry_id(entry: dict) -> str:
    """Short pytest id so failure output names the query, not just an index."""
    label = entry["query"][:50].rstrip()
    if entry.get("file_path"):
        label = f"{label}::{Path(entry['file_path']).name}"
    return label


@pytest.fixture(scope="module")
def snapshot() -> dict:
    return _load_snapshot()


@pytest.mark.parametrize("entry", _load_snapshot()["queries"], ids=_entry_id)
def test_golden_routing_query_matches_snapshot(entry: dict) -> None:
    decision = resolve_capability(entry["query"], file_path=entry.get("file_path") or "")

    expected_skill = entry["chosen_skill"]
    expected_coverage = entry["coverage"]
    expected_domain = entry["domain"]
    expected_search_web = entry["should_search_web"]
    expected_create_skill = entry["should_create_skill"]

    # Top-level routing decision — this is what downstream consumers act on.
    assert decision.chosen_skill == expected_skill, (
        f"chosen_skill drifted for {entry['query']!r}: "
        f"expected {expected_skill!r}, got {decision.chosen_skill!r}. "
        f"If the new choice is intentional, regenerate "
        f"tests/fixtures/golden_routing/snapshot.json."
    )
    assert decision.coverage == expected_coverage, (
        f"coverage drifted for {entry['query']!r}: "
        f"expected {expected_coverage!r}, got {decision.coverage!r}."
    )
    assert decision.domain == expected_domain, (
        f"domain drifted for {entry['query']!r}: "
        f"expected {expected_domain!r}, got {decision.domain!r}."
    )
    assert decision.should_search_web is expected_search_web, (
        f"should_search_web drifted for {entry['query']!r}: "
        f"expected {expected_search_web!r}, got {decision.should_search_web!r}."
    )
    assert decision.should_create_skill is expected_create_skill, (
        f"should_create_skill drifted for {entry['query']!r}: "
        f"expected {expected_create_skill!r}, got {decision.should_create_skill!r}."
    )


def test_golden_snapshot_corpus_has_minimum_breadth() -> None:
    """The snapshot must cover enough of the decision space to be useful.

    A regression in a single query is informative; a snapshot of two
    queries isn't. This sanity-check pins a minimum corpus size and
    enforces basic coverage of each coverage bucket.
    """
    snapshot = _load_snapshot()
    queries = snapshot["queries"]
    assert len(queries) >= 18, (
        f"golden corpus shrank to {len(queries)} queries; "
        f"keep it ≥18 so weight changes have somewhere to surface."
    )

    coverages = {entry["coverage"] for entry in queries}
    assert {"exact_skill", "no_skill", "partial_skill"} <= coverages, (
        f"golden corpus must cover exact_skill / partial_skill / no_skill — "
        f"got only {coverages}"
    )


def regenerate() -> None:
    """Rebuild ``snapshot.json`` from the live resolver.

    Intended for developer use after an intentional weight change — never
    called by pytest. Invokes resolve_capability for every query already
    in the snapshot and rewrites the file with the new outputs.
    """
    snapshot = _load_snapshot()
    refreshed = {"queries": []}
    for entry in snapshot["queries"]:
        decision = resolve_capability(
            entry["query"], file_path=entry.get("file_path") or ""
        )
        refreshed["queries"].append(
            {
                "query": entry["query"],
                "file_path": entry.get("file_path"),
                "chosen_skill": decision.chosen_skill,
                "coverage": decision.coverage,
                "domain": decision.domain,
                "should_search_web": decision.should_search_web,
                "should_create_skill": decision.should_create_skill,
                "top_3_candidates": [
                    {"skill": c.skill, "score": c.score}
                    for c in decision.skill_candidates[:3]
                ],
            }
        )
    GOLDEN_PATH.write_text(
        json.dumps(refreshed, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
