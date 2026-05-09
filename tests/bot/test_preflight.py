"""Unit tests for ``bot.preflight`` — the question-loop state machine.

Pure-Python state machine: parses a user's free-form reply against the
pending-fields contract from a Skill's preflight payload, applies
resolved answers back to the original tool args, and renders the next
message. No I/O, no LLM client.

These tests pin the resolution semantics of ``_parse_preflight_reply``
(equals form, alias matching, choice-keyword matching, positional
fallback) and the apply / confirmation / remember behaviour. Drives
each helper through stand-in dict shapes that match what the production
preflight payloads carry.
"""

from __future__ import annotations


# --- _coerce_preflight_value -------------------------------------------------


def test_coerce_value_strips_list_marker_prefix():
    """User-typed answers often arrive with a markdown bullet/number prefix
    ('1. 0.05', '- yes'). Coercion must strip that before parsing."""
    from bot.preflight import _coerce_preflight_value

    assert _coerce_preflight_value("1. 0.05", "number") == 0.05
    assert _coerce_preflight_value("- 7", "integer") == 7
    assert _coerce_preflight_value("* yes", "boolean") is True


def test_coerce_value_boolean_accepts_yes_no_synonyms():
    from bot.preflight import _coerce_preflight_value

    for affirmative in ["yes", "y", "true", "1", "ok", "okay", "accept"]:
        assert _coerce_preflight_value(affirmative, "boolean") is True
    for negative in ["no", "n", "false", "0", "reject"]:
        assert _coerce_preflight_value(negative, "boolean") is False


def test_coerce_value_string_passthrough_when_unrecognised():
    """For non-numeric / non-boolean fields, return the cleaned string."""
    from bot.preflight import _coerce_preflight_value

    assert _coerce_preflight_value("wilcoxon", "string") == "wilcoxon"


# --- _set_or_replace_extra_arg ----------------------------------------------


def test_set_or_replace_extra_arg_replaces_existing_separated_form():
    """When ``--padj 0.05`` already exists, replacing must drop both tokens."""
    from bot.preflight import _set_or_replace_extra_arg

    extras = ["--padj", "0.05", "--top-n", "30"]
    out = _set_or_replace_extra_arg(extras, "--padj", 0.01)

    assert out == ["--top-n", "30", "--padj", "0.01"]


def test_set_or_replace_extra_arg_replaces_existing_equals_form():
    """When ``--padj=0.05`` (single token) already exists, replace as well."""
    from bot.preflight import _set_or_replace_extra_arg

    out = _set_or_replace_extra_arg(["--padj=0.05", "--method", "wilcoxon"], "--padj", 0.01)

    assert out == ["--method", "wilcoxon", "--padj", "0.01"]


def test_set_or_replace_extra_arg_boolean_true_is_bare_flag():
    """A boolean True becomes a bare flag (no value token); False omits it."""
    from bot.preflight import _set_or_replace_extra_arg

    on = _set_or_replace_extra_arg([], "--strict", True)
    off = _set_or_replace_extra_arg([], "--strict", False)

    assert on == ["--strict"]
    assert off == []


# --- _parse_preflight_reply --------------------------------------------------


_PADJ_FIELD = {
    "key": "padj_threshold",
    "aliases": ["padj", "p_adj", "fdr"],
    "value_type": "number",
    "flag": "--padj",
}

_METHOD_FIELD = {
    "key": "method",
    "aliases": ["method", "test"],
    "value_type": "string",
    "choices": ["wilcoxon", "t-test", "deseq2_r"],
    "flag": "--method",
}


def test_parse_reply_resolves_via_alias_equals_form():
    from bot.preflight import _parse_preflight_reply

    state = {"pending_fields": [_PADJ_FIELD, _METHOD_FIELD], "answers": {}}
    answers, remaining = _parse_preflight_reply(state, "padj=0.01, method=wilcoxon")

    assert answers["padj_threshold"] == 0.01
    assert answers["method"] == "wilcoxon"
    assert remaining == []


def test_parse_reply_resolves_via_choice_keyword():
    """When user types a bare choice keyword (e.g. ``wilcoxon``) without
    naming the field, it still resolves to the first field whose
    ``choices`` contains it."""
    from bot.preflight import _parse_preflight_reply

    state = {"pending_fields": [_METHOD_FIELD], "answers": {}}
    answers, remaining = _parse_preflight_reply(state, "use wilcoxon please")

    assert answers["method"] == "wilcoxon"
    assert remaining == []


def test_parse_reply_positional_fallback_for_single_field():
    """If the user just types a value (no key=value, no choice keyword)
    and there's exactly one unresolved field, take the last line as the
    answer for that field."""
    from bot.preflight import _parse_preflight_reply

    state = {"pending_fields": [_PADJ_FIELD], "answers": {}}
    answers, remaining = _parse_preflight_reply(state, "0.005")

    assert answers["padj_threshold"] == 0.005
    assert remaining == []


def test_parse_reply_partial_resolution_leaves_other_field_pending():
    """When the user answers one of two pending fields via alias and the
    other has no positional / choice match, the unanswered field stays in
    ``remaining`` so the question loop continues. Note: when exactly one
    field is unresolved AND the reply contains free-form lines, the
    parser's positional fallback IS aggressive — that's the existing
    contract; this test pins partial resolution under multiple pending
    fields where the fallback can't fire."""
    from bot.preflight import _parse_preflight_reply

    state = {"pending_fields": [_PADJ_FIELD, _METHOD_FIELD], "answers": {}}
    # Single equals-form line — answers padj only; method stays pending.
    answers, remaining = _parse_preflight_reply(state, "padj=0.01")

    assert answers == {"padj_threshold": 0.01}
    assert len(remaining) == 1
    assert remaining[0]["key"] == "method"


# --- _apply_preflight_answers ------------------------------------------------


def test_apply_answers_routes_top_level_keys_directly():
    """Keys in ``_PREFLIGHT_TOP_LEVEL_ARGS`` (skill / mode / method / ...)
    go onto the args dict directly, not into ``extra_args``."""
    from bot.preflight import _apply_preflight_answers

    pending_fields = [{"key": "method", "flag": "--method"}]
    out = _apply_preflight_answers({"skill": "sc-de"}, pending_fields, {"method": "wilcoxon"})

    assert out["method"] == "wilcoxon"
    assert "extra_args" not in out  # method was top-level, no flag push


def test_apply_answers_pushes_other_keys_through_extra_args():
    """Non-top-level keys with a configured flag get pushed into
    ``extra_args`` via ``_set_or_replace_extra_arg``."""
    from bot.preflight import _apply_preflight_answers

    pending_fields = [{"key": "padj_threshold", "flag": "--padj"}]
    out = _apply_preflight_answers(
        {"skill": "sc-de", "extra_args": ["--keep", "true"]},
        pending_fields,
        {"padj_threshold": 0.01},
    )

    assert out["extra_args"] == ["--keep", "true", "--padj", "0.01"]


def test_apply_answers_skips_allow_prefixed_keys():
    """``allow_*`` keys are confirmations, not flag values — skip them."""
    from bot.preflight import _apply_preflight_answers

    pending_fields = [{"key": "allow_overwrite", "flag": "--force"}]
    out = _apply_preflight_answers({"skill": "sc-de"}, pending_fields, {"allow_overwrite": True})

    assert "extra_args" not in out


# --- _is_affirmative_preflight_confirmation ---------------------------------


def test_affirmative_confirmation_detects_yes_variants_in_english_and_chinese():
    from bot.preflight import _is_affirmative_preflight_confirmation

    for phrase in ["yes", "ok please continue", "确认", "可以", "用默认就行", "go ahead"]:
        assert _is_affirmative_preflight_confirmation(phrase), phrase


def test_affirmative_confirmation_negative_markers_short_circuit():
    """Even if an affirmative keyword appears, a negative marker wins
    (e.g. 'no, do not continue' → False)."""
    from bot.preflight import _is_affirmative_preflight_confirmation

    for phrase in ["no", "do not continue", "cancel", "不要继续", "取消"]:
        assert not _is_affirmative_preflight_confirmation(phrase), phrase


# --- _remember_pending_preflight_request ------------------------------------


def test_remember_pending_request_stores_into_bot_core_dict(monkeypatch):
    """``_remember_pending_preflight_request`` must mutate
    ``bot.core.pending_preflight_requests`` since multiple modules read
    it from there."""
    import bot.core

    monkeypatch.setattr(bot.core, "pending_preflight_requests", {}, raising=False)

    from bot.preflight import _remember_pending_preflight_request

    _remember_pending_preflight_request(
        "chat-42",
        args={"skill": "sc-de", "mode": "path"},
        payload={"pending_fields": [{"key": "padj_threshold"}], "kind": "preflight"},
    )

    stored = bot.core.pending_preflight_requests["chat-42"]
    assert stored["tool_name"] == "omicsclaw"
    assert stored["original_args"] == {"skill": "sc-de", "mode": "path"}
    assert stored["pending_fields"] == [{"key": "padj_threshold"}]
    assert stored["answers"] == {}
