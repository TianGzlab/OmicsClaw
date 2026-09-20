"""The rule file: what one line means, and what it must not be able to mean.

The tests that matter most here are the ones about ``allow``. A ``deny``
that matches too much costs somebody a prompt; an ``allow`` that matches too
much runs a command nobody read. Both of the reference's convenience
behaviours — substring matching and per-word matching — are holes in that
direction, so each has a test asserting it is *absent*.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from omicsclaw.permission.rules import (
    CONFIG_KEY,
    PermissionConfigError,
    Rule,
    RuleStore,
    Rules,
    Verdict,
    literal_pattern,
    load_rules,
    principal_argument,
    principal_key,
    save_rules,
)

BASH_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "timeout": {"type": "number"},
    },
    "required": ["command"],
}

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
}


def rules(**sections: list[str]) -> Rules:
    return Rules.from_config({CONFIG_KEY: sections})


# ---- pattern syntax ------------------------------------------------------


def test_a_bare_tool_name_matches_any_arguments():
    rule = Rule(Verdict.ALLOW, "read_file")

    assert rule.tool == "read_file"
    assert rule.glob == ""
    assert rule.matches("read_file", "anything at all")
    assert not rule.matches("write_file", "anything at all")


def test_empty_parentheses_also_match_any_arguments():
    """The reference's ``pGlob == ""`` case, kept so a ported file still works."""
    assert Rule(Verdict.DENY, "bash()").matches("bash", "whatever")


def test_a_pattern_missing_its_closing_paren_is_refused():
    """``rules.go:80`` trims the suffix, so ``bash(rm`` silently becomes ``rm``.

    Left as written it is a rule naming a tool called ``bash(rm``, which
    exists nowhere — a line in a security file that reads as in force and
    matches nothing.
    """
    with pytest.raises(PermissionConfigError, match="closing"):
        Rule(Verdict.DENY, "bash(rm -rf *")


@pytest.mark.parametrize("pattern", ["", "   ", "(bash)"])
def test_a_pattern_that_names_no_tool_is_refused(pattern: str):
    with pytest.raises(PermissionConfigError):
        Rule(Verdict.ALLOW, pattern)


def test_a_paren_inside_the_glob_survives():
    rule = Rule(Verdict.ASK, "bash(echo (1)*)")

    assert rule.glob == "echo (1)*"
    assert rule.matches("bash", "echo (1) > out")


# ---- matching semantics --------------------------------------------------


def test_a_wildcard_free_pattern_must_match_exactly():
    rule = Rule(Verdict.ALLOW, "bash(git status)")

    assert rule.matches("bash", "git status")
    assert not rule.matches("bash", "git status --short")


def test_no_substring_fallback_so_an_allow_cannot_be_smuggled_past():
    """``rules.go:90``'s ``strings.Contains`` would allow this chained command.

    The hole in one line: allow ``ls``, and ``rm -rf /; ls`` contains ``ls``.
    """
    rule = Rule(Verdict.ALLOW, "bash(ls)")

    assert not rule.matches("bash", "rm -rf /; ls")
    assert not rule.matches("bash", "ls -la")
    assert rule.matches("bash", "ls")


def test_no_per_word_pass_either():
    """``rules.go:111`` matches the glob against each word of the command.

    So ``allow: ["bash(ls*)"]`` there allows any command containing a word
    starting with ``ls`` — the same hole reached from the other direction.
    """
    rule = Rule(Verdict.ALLOW, "bash(ls*)")

    assert rule.matches("bash", "ls -la")
    assert not rule.matches("bash", "rm -rf / && ls -la")


def test_a_star_crosses_a_path_separator():
    """Go's ``filepath.Match`` refuses to, which is why it needs fast paths."""
    rule = Rule(Verdict.ALLOW, "bash(git *)")

    assert rule.matches("bash", "git log -- deep/nested/path.py")


def test_matching_is_case_sensitive():
    """The registry keys tools exactly, and a lenient ``allow`` grants more."""
    rule = Rule(Verdict.ALLOW, "bash(git status)")

    assert not rule.matches("BASH", "git status")
    assert not rule.matches("bash", "GIT STATUS")


@pytest.mark.parametrize(
    ("glob", "argument", "expected"),
    [
        ("pip install*", "pip install scanpy", True),
        ("pip install*", "python -m pip install scanpy", False),
        ("*--force*", "git push --force", True),
        ("rm -rf ?", "rm -rf x", True),
        ("rm -rf ?", "rm -rf xy", False),
    ],
)
def test_glob_shapes(glob: str, argument: str, expected: bool):
    assert Rule(Verdict.ASK, f"bash({glob})").matches("bash", argument) is expected


# ---- ordering ------------------------------------------------------------


def test_deny_is_evaluated_before_allow_whatever_the_file_order():
    """Both keys match; the answer must not depend on JSON key order."""
    for section in (
        {"allow": ["bash(rm -rf /)"], "deny": ["bash(rm -rf /)"]},
        {"deny": ["bash(rm -rf /)"], "allow": ["bash(rm -rf /)"]},
    ):
        decided = Rules.from_config({CONFIG_KEY: section}).evaluate(
            "bash", "rm -rf /"
        )
        assert decided is not None
        assert decided.verdict is Verdict.DENY


def test_the_first_matching_rule_wins_within_one_action():
    ruleset = rules(allow=["bash(git status)", "bash(git *)"])
    decided = ruleset.evaluate("bash", "git status")

    assert decided is not None
    assert decided.pattern == "bash(git status)"


def test_an_unmatched_call_returns_none_and_not_ask():
    """The structural change to ``rules.go:66``, and why the pipeline works.

    Conflating "no rule spoke about this" with "ask a human" is what makes a
    harness9 process with no rule file prompt for every tool call, and what
    makes its own dangerous-command patterns unreachable.
    """
    assert rules(allow=["read_file"]).evaluate("bash", "ls") is None
    assert Rules().evaluate("bash", "ls") is None


def test_evaluate_reports_which_rule_decided():
    decided = rules(deny=["bash(rm -rf *)"]).evaluate("bash", "rm -rf /data")

    assert decided is not None
    assert decided.pattern == "bash(rm -rf *)"


# ---- the principal argument ---------------------------------------------


def test_the_principal_argument_is_the_first_required_string():
    assert principal_key(BASH_SCHEMA) == "command"
    assert principal_key(WRITE_SCHEMA) == "path"
    assert principal_key(None) is None
    assert principal_key({"properties": {}}) is None


def test_write_file_matches_on_its_destination_not_its_content():
    """The reason a schema-derived principal beats matching the raw payload.

    ``write_file(*/tmp/*)`` is a statement about *where*, and a person who
    wrote it did not also mean "or anywhere, if the text being written
    happens to mention /tmp/".
    """
    payload = json.dumps({"path": "results/out.csv", "content": "see /tmp/x"})

    assert principal_argument(payload, WRITE_SCHEMA) == "results/out.csv"
    assert not Rule(Verdict.ALLOW, "write_file(*/tmp/*)").matches(
        "write_file", principal_argument(payload, WRITE_SCHEMA)
    )


def test_a_bash_command_is_matched_unescaped():
    """Why the reference special-cases ``bash``: the raw JSON escapes quotes."""
    payload = json.dumps({"command": 'grep "x" a.txt'})

    assert principal_argument(payload, BASH_SCHEMA) == 'grep "x" a.txt'
    assert '\\"' in payload


@pytest.mark.parametrize(
    "payload", ["{", "[]", '"text"', "{}", '{"command": ""}', '{"command": 7}']
)
def test_an_unreadable_payload_falls_back_to_the_raw_text(payload: str):
    """Never raises: the rules are how a truncated ``bash`` call gets stopped."""
    assert principal_argument(payload, BASH_SCHEMA) == payload


# ---- always allow -------------------------------------------------------


def test_literal_pattern_remembers_exactly_the_approved_call():
    pattern = literal_pattern("bash", "git status")
    rule = Rule(Verdict.ALLOW, pattern)

    assert rule.matches("bash", "git status")
    assert not rule.matches("bash", "git status; rm -rf /")


def test_literal_pattern_neutralises_wildcards_in_the_command():
    """Otherwise approving ``ls *.csv`` once would allow every ``ls`` of every file."""
    rule = Rule(Verdict.ALLOW, literal_pattern("bash", "ls *.csv"))

    assert rule.matches("bash", "ls *.csv")
    assert not rule.matches("bash", "ls secret.csv")


def test_literal_pattern_handles_brackets_and_question_marks():
    for command in ["grep [ab] f", "ls a?b", "echo [*]"]:
        rule = Rule(Verdict.ALLOW, literal_pattern("bash", command))
        assert rule.matches("bash", command), command


def test_literal_pattern_of_nothing_is_just_the_tool_name():
    assert literal_pattern("read_file", "") == "read_file"


# ---- the file -----------------------------------------------------------


def test_a_missing_file_is_an_empty_rule_set(tmp_path):
    """The ordinary case: nobody has refined anything yet."""
    assert len(load_rules(tmp_path / "nothing.json")) == 0


def test_an_empty_file_is_an_empty_rule_set(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("   \n", encoding="utf-8")

    assert len(load_rules(path)) == 0


def test_a_file_without_a_permissions_key_is_an_empty_rule_set(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"other": {"x": 1}}), encoding="utf-8")

    assert len(load_rules(path)) == 0


def test_malformed_json_is_refused_loudly(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PermissionConfigError, match="not valid JSON"):
        load_rules(path)


def test_a_misspelled_action_key_is_refused(tmp_path):
    """The worst silent failure available: every ``deny`` dropped.

    The reference ignores unknown keys, so ``"denied"`` there is a file that
    reads as a blocklist and is not one.
    """
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({CONFIG_KEY: {"denied": ["bash(rm -rf *)"]}}), encoding="utf-8"
    )

    with pytest.raises(PermissionConfigError, match="unknown key"):
        load_rules(path)


@pytest.mark.parametrize(
    "section",
    [
        {"allow": "read_file"},
        {"allow": [7]},
        {"allow": {"read_file": True}},
    ],
)
def test_a_scalar_where_a_list_belongs_is_refused(tmp_path, section: dict):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({CONFIG_KEY: section}), encoding="utf-8")

    with pytest.raises(PermissionConfigError):
        load_rules(path)


def test_a_top_level_list_is_refused(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(PermissionConfigError, match="top level"):
        load_rules(path)


def test_a_round_trip_preserves_every_rule(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    original = rules(
        deny=["bash(rm -rf *)"],
        allow=["read_file", "bash(git *)"],
        ask=["web_fetch"],
    )

    save_rules(path, original)

    assert load_rules(path) == original


def test_saving_writes_an_owner_only_file_in_an_owner_only_directory(tmp_path):
    path = tmp_path / "private" / "settings.json"

    save_rules(path, rules(allow=["read_file"]))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_every_directory_created_is_owner_only_not_just_the_last(tmp_path):
    """``mkdir(parents=True, mode=…)`` applies the mode to the leaf only.

    One level deep — which is the default ``<workspace>/.omicsclaw/`` — hides
    this completely, so the single-level test above passes either way. A
    ``--permission-rules`` pointing at a path that does not exist yet is the
    case that matters: every intermediate directory was ``0o755``, leaving
    the tree holding the rule file traversable by any account on the machine
    while the file itself looked correct.
    """
    path = tmp_path / "deep" / "deeper" / "deepest" / "settings.json"

    save_rules(path, rules(deny=["bash"]))

    created = (
        tmp_path / "deep",
        tmp_path / "deep" / "deeper",
        tmp_path / "deep" / "deeper" / "deepest",
    )
    wrong = {
        str(d.relative_to(tmp_path)): oct(stat.S_IMODE(d.stat().st_mode))
        for d in created
        if stat.S_IMODE(d.stat().st_mode) != 0o700
    }

    assert not wrong, wrong
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_saving_into_an_existing_directory_does_not_retighten_it(tmp_path):
    """This function creates; it does not reconfigure somebody else's tree."""
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)

    save_rules(shared / "settings.json", rules(allow=["read_file"]))

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert stat.S_IMODE((shared / "settings.json").stat().st_mode) == 0o600


def test_saving_leaves_no_temporary_file_behind(tmp_path):
    path = tmp_path / "settings.json"

    save_rules(path, rules(allow=["read_file"]))

    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_saving_replaces_rather_than_truncating(tmp_path, monkeypatch):
    """A half-written rule file is a rule file whose deny list got cut short.

    Step 4.5's ``edit_file`` lesson, where the content is a security control:
    a direct ``open(path, "w")`` empties the file before the first byte of the
    replacement is written, so a failure partway through loses the old rules
    as well as the new ones.
    """
    path = tmp_path / "settings.json"
    save_rules(path, rules(deny=["bash(rm -rf *)"]))

    def explode(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(OSError):
        save_rules(path, rules(allow=["read_file"]))

    assert load_rules(path) == rules(deny=["bash(rm -rf *)"])
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_to_config_drops_a_repeated_pattern():
    """Approving "always allow" for one command twice must not grow the file."""
    twice = rules(allow=["bash(git status)", "bash(git status)"])

    assert twice.to_config()[CONFIG_KEY]["allow"] == ["bash(git status)"]


# ---- the store ----------------------------------------------------------


def test_the_store_is_loud_at_construction(tmp_path):
    """A typo in a security file should stop a deployment, not a tool call."""
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PermissionConfigError):
        RuleStore(path)


def test_the_store_rereads_the_file_on_every_question(tmp_path):
    """What makes "always allow" take effect on the next call, not the next run."""
    path = tmp_path / "settings.json"
    store = RuleStore(path)

    assert len(store.current) == 0

    save_rules(path, rules(allow=["bash(git status)"]))

    assert len(store.current) == 1
    assert store.current.evaluate("bash", "git status") is not None


def test_the_store_keeps_the_last_good_rules_when_the_file_breaks(tmp_path, caplog):
    """A file being edited in another window must not kill a running analysis."""
    path = tmp_path / "settings.json"
    save_rules(path, rules(deny=["bash(rm -rf *)"]))
    store = RuleStore(path)
    assert len(store.current) == 1

    path.write_text("{broken", encoding="utf-8")

    with caplog.at_level("WARNING"):
        surviving = store.current

    assert len(surviving) == 1
    assert surviving.evaluate("bash", "rm -rf /data") is not None
    assert "unreadable" in caplog.text


def test_remember_appends_an_allow_and_persists_it(tmp_path):
    path = tmp_path / "settings.json"
    store = RuleStore(path)

    store.remember(literal_pattern("bash", "git status"))

    assert RuleStore(path).current.evaluate("bash", "git status") is not None
    assert store.current.evaluate("bash", "git status") is not None


def test_remember_refuses_a_pattern_that_would_never_fire(tmp_path):
    """Validation lives on :class:`Rule`, so every route in is checked once."""
    store = RuleStore(tmp_path / "settings.json")

    with pytest.raises(PermissionConfigError):
        store.remember("bash(oops")

    assert len(store.current) == 0


def test_remember_keeps_what_was_already_in_the_file(tmp_path):
    path = tmp_path / "settings.json"
    save_rules(path, rules(deny=["bash(rm -rf *)"]))
    store = RuleStore(path)

    store.remember("bash(git status)")

    reloaded = RuleStore(path).current
    assert len(reloaded) == 2
    decided = reloaded.evaluate("bash", "rm -rf /")
    assert decided is not None and decided.verdict is Verdict.DENY


def test_rules_are_immutable_so_a_live_gate_cannot_be_edited_underneath():
    original = rules(allow=["read_file"])
    extended = original.with_rule(Verdict.DENY, "bash")

    assert len(original) == 1
    assert len(extended) == 2
    assert original != extended
