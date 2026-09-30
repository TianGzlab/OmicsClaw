"""Prompt contracts, the leak check and the two model interactions.

The model sees the whole SKILL.md (its default of 7 included: the default is
what the baseline uses, so showing it is conservative for the claim), the
full stability table and compact markers for every K, not only the stable
peaks, so that it can pick any K of the grid. What must never reach it is a
count we injected: the leak check covers the tissue string, the data summary,
the templates and the free-orchestration task, and refuses before any request.
The skill documentation and trial outputs are not ours to censor and are not
checked.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from omicsclaw.ensemble.tuning.ledger import Ledger
from omicsclaw.ensemble.tuning.llm import (
    CassetteChatModel,
    CassetteMiss,
    LLMSettings,
    ScriptedChatModel,
    decide_k,
    propose,
)
from omicsclaw.ensemble.tuning.prompts import (
    LeakError,
    check_leak,
    load_template,
    parse_json_reply,
    render_k_decision,
    render_propose,
    template_sha256,
)
from tests.ensemble.tuning import fixtures

GOLDEN = Path(__file__).resolve().parent / "golden"
SETTINGS = LLMSettings(model="m", provider="p", temperature=0.3)


def _run(coro):
    return asyncio.run(coro)


def _golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("OMICSCLAW_WRITE_GOLDEN") == "1":
        path.write_text(text, encoding="utf-8")
    assert text == path.read_text(encoding="utf-8")


# ---- the leak check --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["k_decision.txt", "propose.txt", "free_task.txt"])
def test_templates_raise_no_false_alarm(name):
    check_leak({"template": load_template(name)})


@pytest.mark.parametrize(
    "tissue",
    [
        "human dorsolateral prefrontal cortex",
        "human liver",
        "mouse hippocampus, coronal section",
        "人类背外侧前额叶皮层",
        "mouse brain, 10 um section, stained with DAPI",
    ],
)
def test_ordinary_tissue_strings_pass(tissue):
    check_leak({"tissue": tissue})


@pytest.mark.parametrize(
    "tissue",
    [
        "cortex with 6 layers",
        "six-layer cortex",
        "liver, 3 zones",
        "tumour with five niches",
        "tissue of 7 domains",
        "12 regions",
        "two areas",
        "皮层6层",
        "肝脏三个区域",
        "五个分区",
    ],
)
def test_each_count_phrase_is_refused_before_any_request(tmp_path, tissue):
    model = ScriptedChatModel({"k_decision": [fixtures.decision()]})
    with pytest.raises(LeakError):
        _run(decide_k(model, fixtures.k_input(tissue=tissue), settings=SETTINGS, ledger=Ledger(tmp_path),
                      fetch_markers=None))
    assert model.calls == []


def test_the_word_boundary_keeps_ordinary_numbers_apart():
    check_leak({"data summary": "observations: 3639; genes: 33538; 2 batches; layer3 ok"})
    with pytest.raises(LeakError):
        check_leak({"data summary": "7 layers"})


def test_the_skill_documentation_and_trial_outputs_are_not_checked(tmp_path):
    """The fixture SKILL.md says "7 layers" and a marker block could say anything;
    both reach the prompt without a LeakError."""
    text = render_k_decision(fixtures.k_input())
    assert "typical cortex sections show 7 layers" in text


def test_the_data_summary_is_built_without_obs_columns():
    from dataclasses import fields

    from omicsclaw.ensemble.tuning.prompts import DataSummary

    names = {f.name for f in fields(DataSummary)}
    assert not any("obs_col" in name or "label" in name for name in names)


# ---- rendering ---------------------------------------------------------------------------------


def test_the_k_prompt_carries_the_skill_every_k_and_the_stable_peaks_in_full():
    text = render_k_decision(fixtures.k_input())
    assert fixtures.SKILL_MD.strip() in text and fixtures.PARAMETERS_MD.strip() in text
    for k in fixtures.GRID:
        assert f"\nK={k} (spagcn" in text
    assert "### K=4" in text and "### K=6" in text and "### K=7" not in text
    assert "human dorsolateral prefrontal cortex" in text
    assert "should" not in text.split("## Stability curves")[1].split("## Markers")[0].lower()
    _golden("k_decision.rendered.txt", text)


def test_the_proposal_prompt(tmp_path):
    text = render_propose(fixtures.propose_input())
    assert "K=7" in text and "spagcn_p=0.1" in text and "Propose exactly 3" in text
    assert fixtures.SKILL_MD.strip() in text
    _golden("propose.rendered.txt", text)


def test_the_template_hashes_are_those_of_the_files():
    import hashlib

    hashes = template_sha256()
    assert set(hashes) == {"k_decision.txt", "propose.txt", "free_task.txt"}
    for name, digest in hashes.items():
        path = Path(__file__).resolve().parents[3] / "omicsclaw/ensemble/tuning/templates" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_replies_in_code_fences_are_read():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Here it is: {"a": 1} done') == {"a": 1}


# ---- the K decision ----------------------------------------------------------------------------------


def _fetch(requested):
    async def fetch(ks):
        requested.append(list(ks))
        return fixtures.markers_document(full=(4, 6, *ks))
    return fetch


def test_a_direct_decision(tmp_path):
    model = ScriptedChatModel({"k_decision": [fixtures.decision(9)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.decision.chosen_k == 9 and outcome.retries == 0
    assert (tmp_path / "llm" / "0001.json").is_file()
    call = Ledger(tmp_path).events("llm_call")[0]
    assert call["model"] == "m" and call["validation"] == "ok" and call["template_sha256"]


def test_the_model_may_pick_a_k_that_is_not_a_peak(tmp_path):
    model = ScriptedChatModel({"k_decision": [fixtures.decision(13)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.decision.chosen_k == 13


def test_a_valid_marker_request_then_a_decision(tmp_path):
    requested = []
    body = json.loads(fixtures.decision(9))
    body["evidence"].append({"k": 9, "kind": "markers", "domain": "2", "genes": ["G9_2_4"], "reading": "full"})
    model = ScriptedChatModel({"k_decision": ['{"request_markers": [9, 12]}', json.dumps(body)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch(requested)))
    assert requested == [[9, 12]] and outcome.requested == [9, 12]
    assert outcome.decision.chosen_k == 9 and outcome.retries == 0
    second = model.calls[1][1][-1].content
    assert "### K=9" in second and "### K=12" in second


@pytest.mark.parametrize(
    "request_text",
    ['{"request_markers": [4]}', '{"request_markers": [2]}', '{"request_markers": [7, 8, 9]}',
     '{"request_markers": []}', '{"request_markers": [7, 7]}'],
)
def test_an_illegal_request_costs_a_retry(tmp_path, request_text):
    model = ScriptedChatModel({"k_decision": [request_text, fixtures.decision(7)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.retries == 1 and outcome.decision.chosen_k == 7
    assert "not stable peaks" in model.calls[1][1][-1].content or "one or two" in model.calls[1][1][-1].content


def test_a_second_request_is_invalid(tmp_path):
    model = ScriptedChatModel({"k_decision": ['{"request_markers": [7]}', '{"request_markers": [8]}',
                                              fixtures.decision(7)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.retries == 1 and outcome.decision.chosen_k == 7


def test_the_retry_budget_spans_both_steps(tmp_path):
    """Two invalid replies around a request exhaust the budget: the third
    invalid reply falls back even though each step saw fewer than three."""
    model = ScriptedChatModel({"k_decision": ["not json", '{"request_markers": [7]}', '{"chosen_k": 99}',
                                              '{"chosen_k": 7}', fixtures.decision(7)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.decision is None and outcome.retries == 3
    assert model.count("k_decision") == 4


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"chosen_k": 2}, "chosen_k"),
        ({"chosen_k": "7"}, "chosen_k"),
        ({"evidence": []}, "between 1 and 10"),
        ({"evidence": [{"k": 7, "kind": "markers", "domain": "99", "genes": ["X"], "reading": ""}]}, "no domain"),
        ({"evidence": [{"k": 7, "kind": "markers", "domain": "1", "genes": ["NOPE"], "reading": ""}]}, "genes must"),
        ({"evidence": [{"k": 7, "kind": "skill_md", "quote": "made up text", "reading": ""}]}, "copied exactly"),
        ({"evidence": [{"k": 30, "kind": "curve", "curve": "f", "reading": ""}]}, "from the grid"),
        ({"rationale": " "}, "rationale"),
        ({"confidence": "total"}, "confidence"),
    ],
)
def test_invalid_decisions_are_retried_with_the_reason(tmp_path, overrides, fragment):
    model = ScriptedChatModel({"k_decision": [fixtures.decision(7, **overrides), fixtures.decision(8)]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.decision.chosen_k == 8 and outcome.retries == 1
    assert fragment in model.calls[1][1][-1].content


def test_a_provider_error_ends_the_decision(tmp_path):
    model = ScriptedChatModel({"k_decision": [RuntimeError("503")]})
    outcome = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                            fetch_markers=_fetch([])))
    assert outcome.decision is None and "503" in outcome.failure


# ---- proposals ---------------------------------------------------------------------------------------


def _accept(params):
    if not isinstance(params, dict):
        return None, "not an object"
    if params.get("spagcn_p", 0.5) > 0.9:
        return None, "spagcn_p out of range"
    return dict(params), ""


def test_three_proposals_are_accepted(tmp_path):
    reply = json.dumps({"proposals": [{"params": {"spagcn_p": 0.3}, "why": "a"},
                                      {"params": {"spagcn_p": 0.7, "epochs": 200}, "why": "b"},
                                      {"params": {"epochs": 60}, "why": "c"}]})
    model = ScriptedChatModel({"propose:*": [reply]})
    outcome = _run(propose(model, fixtures.propose_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                           accept=_accept))
    assert len(outcome.accepted) == 3 and outcome.retries == 0


def test_bad_items_are_dropped_without_a_retry(tmp_path):
    reply = json.dumps({"proposals": [{"params": {"spagcn_p": 1.5}, "why": "a"}, "junk",
                                      {"params": {"epochs": 60}, "why": "c"}, {"params": {"epochs": 70}}]})
    model = ScriptedChatModel({"propose:*": [reply]})
    outcome = _run(propose(model, fixtures.propose_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                           accept=_accept))
    assert len(outcome.accepted) == 1 and len(outcome.dropped) == 3
    assert outcome.retries == 0 and model.count("propose:*") == 1


def test_an_unreadable_batch_is_retried_then_given_up(tmp_path):
    model = ScriptedChatModel({"propose:*": ["nope", "{}", "[]"]})
    outcome = _run(propose(model, fixtures.propose_input(), settings=SETTINGS, ledger=Ledger(tmp_path),
                           accept=_accept))
    assert outcome.accepted == [] and outcome.failure and outcome.retries == 3


# ---- replay --------------------------------------------------------------------------------------------


def test_a_cassette_replays_a_recorded_decision(tmp_path):
    model = ScriptedChatModel({"k_decision": ['{"request_markers": [9]}', fixtures.decision(9)]})
    first = _run(decide_k(model, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path / "a"),
                          fetch_markers=_fetch([])))
    cassette = CassetteChatModel.from_ledger(tmp_path / "a")
    again = _run(decide_k(cassette, fixtures.k_input(), settings=SETTINGS, ledger=Ledger(tmp_path / "b"),
                          fetch_markers=_fetch([])))
    assert again.decision.chosen_k == first.decision.chosen_k == 9
    with pytest.raises(CassetteMiss):
        _run(decide_k(cassette, fixtures.k_input(tissue="human liver"), settings=SETTINGS,
                      ledger=Ledger(tmp_path / "c"), fetch_markers=_fetch([])))


@pytest.mark.parametrize("text", ["L2regions", "L2 regions", "someone area", "CD8 region-specific" , "layer2 marker", "area51", "12regions", "the region2 cluster",
                                  "HOXA10-AS", "7-AAD staining"])
def test_numbers_glued_to_words_are_not_counts(text):
    check_leak({"tissue": text})
