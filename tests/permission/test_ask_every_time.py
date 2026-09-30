"""Which questions a standing "stop asking me" grant may answer (plan 0049).

The CLI's ``s`` now covers a whole tool for the rest of a conversation.
That is only safe if the gate tells the surface, on every question, whether
anything more specific than the tool's own default raised it —— and the
dangerous part is that a *rule* outranks a danger pattern, so the flag has to
survive the path on which the gate hands the question down to the tool.

Each test answers: was ``ask_every_time`` set, and did the person still read
the prompt worth reading?
"""

from __future__ import annotations

import logging

from omicsclaw.permission import (
    PermissionGate,
    PermissionMode,
    RuleStore,
)
from omicsclaw.permission.gate import PROTECTED_DIRNAME, DecisionSource
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import ask_every_time, require_approval
from tests.permission.test_gate import (  # type: ignore[import-not-found]
    PATH_SCHEMA,
    Asking,
    Silent,
    _run,
    rules,
    run,
)

# ---- the flag, per source ---------------------------------------------


def test_the_tools_own_default_may_be_answered_by_a_grant():
    _, human = run(PermissionGate(), Asking(), {"command": "ls -la"})

    assert human.count == 1
    assert human.asked[0].ask_every_time is False


def test_a_dangerous_command_is_always_asked():
    _, human = run(PermissionGate(), Asking(), {"command": "rm -rf /"})

    assert human.count == 1
    assert human.asked[0].ask_every_time is True


def test_a_rule_question_is_always_asked_and_keeps_the_tools_prompt():
    """The path the first draft missed: a rule question is *handed down*.

    ``bash`` prompts for itself, so an ``ask`` rule's question is put by
    ``bash``, with ``bash``'s prompt —— the whole command, which is the
    thing worth reading. The flag has to ride along on that path or it is
    not there at all.
    """
    gate = PermissionGate(rules=rules(ask=["bash(pip install*)"]))

    _, human = run(gate, Asking(), {"command": "pip install scanpy"})

    assert human.count == 1
    assert human.asked[0].ask_every_time is True
    assert human.asked[0].reason == "bash's own prompt"


def test_a_broad_ask_rule_cannot_launder_a_dangerous_command():
    """``ask: ["bash"]`` means "always ask", and must not mean less.

    A rule outranks a danger pattern, so under this rule ``rm -rf /`` is a
    *rule* question, not a *danger* one. Before plan 0049 it would have
    been handed down unmarked, and one ``s`` would have silenced it.
    """
    gate = PermissionGate(rules=rules(ask=["bash(*)"]))

    _, human = run(gate, Asking(), {"command": "rm -rf /"})

    assert human.asked[0].ask_every_time is True


def test_deny_unless_trusted_is_always_asked():
    policy = ToolPolicy(
        risk_level=RiskLevel.HIGH,
        approval_mode=ApprovalMode.DENY_UNLESS_TRUSTED,
    )
    tool = Asking(policy=policy)

    _, human = run(PermissionGate(), tool, {"command": "ls"}, policy=policy)

    assert human.count == 1
    assert human.asked[0].ask_every_time is True


def test_the_flag_does_not_leak_into_the_next_call():
    gate = PermissionGate()
    run(gate, Asking(), {"command": "rm -rf /"})

    _, human = run(gate, Asking(), {"command": "ls"})

    assert human.asked[0].ask_every_time is False


def test_the_scope_restores_on_exit():
    async def inside() -> bool:
        seen = []

        def channel(request):
            seen.append(request.ask_every_time)
            return True

        from omicsclaw.tools.context import use_tool_context

        with use_tool_context(approval=channel):
            with ask_every_time(True):
                await require_approval("t", "{}")
            await require_approval("t", "{}")
        return seen

    assert _run(inside()) == [True, False]


# ---- the protected directory ------------------------------------------


def test_writing_the_rule_file_is_asked_even_in_auto_approve():
    """The self-escalation the review found (plan 0049 §4).

    ``auto-approve`` allows an unmatched call without asking, so a flag on
    the question would never be read: there would be no question. The
    protected check is its own stage, before the rule file and the mode.
    """
    gate = PermissionGate(mode=PermissionMode.AUTO_APPROVE)
    command = (
        "printf '{\"permissions\":{\"allow\":[\"bash(*)\"]}}' "
        f"> {PROTECTED_DIRNAME}/settings.json"
    )

    _, human = run(gate, Asking(), {"command": command})

    assert human.count == 1
    assert human.asked[0].ask_every_time is True
    assert command in human.asked[0].reason


def test_an_allow_rule_cannot_open_the_protected_directory():
    """The protected thing is the rule file, so no rule may unlock it."""
    gate = PermissionGate(rules=rules(allow=["write_file(*)"]))
    tool = Asking("write_file", schema=PATH_SCHEMA)

    _, human = run(gate, tool, {"path": f"{PROTECTED_DIRNAME}/settings.json"})

    assert human.count == 1
    assert human.asked[0].ask_every_time is True


def test_reading_the_protected_directory_is_not_stopped():
    tool = Silent(schema=PATH_SCHEMA)

    _, human = run(PermissionGate(), tool, {"path": f"{PROTECTED_DIRNAME}/plans/a.md"})

    assert human.count == 0
    assert tool.calls


def test_a_rule_file_outside_the_workspace_is_protected_too(tmp_path):
    rule_file = tmp_path / "elsewhere" / "rules.json"
    gate = PermissionGate(rules=RuleStore(rule_file))
    resolution = gate.resolve(
        "bash",
        '{"command": "echo x > %s"}' % rule_file,
        policy=Asking().policy,
        schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    )

    assert resolution.source is DecisionSource.PROTECTED


# ---- the rule file changing under the process -------------------------


def test_an_allow_rule_written_from_outside_is_reported(tmp_path, caplog):
    path = tmp_path / "settings.json"
    store = RuleStore(path)
    path.write_text('{"permissions": {"allow": ["bash(*)"]}}', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="omicsclaw.permission.rules"):
        store.current

    assert "changed outside this process" in caplog.text
    assert "bash(*)" in caplog.text


def test_this_processs_own_remembered_rule_is_not_reported(tmp_path, caplog):
    store = RuleStore(tmp_path / "settings.json")

    with caplog.at_level(logging.WARNING, logger="omicsclaw.permission.rules"):
        store.remember("bash(ls)")
        store.current

    assert "changed outside this process" not in caplog.text


# ---- .env: the other file that decides what is asked about -------------


import pytest  # noqa: E402

from omicsclaw.permission.gate import DOTENV_NAME  # noqa: E402

_ENV_WRITES = [
    "echo OMICSCLAW_PERMISSION_MODE=bypass-all >> .env",
    "sed -i 's#^LLM_BASE_URL=.*#LLM_BASE_URL=https://example.invalid#' .env",
    "cp /tmp/x ./.env.local",
]


@pytest.mark.parametrize("command", _ENV_WRITES)
@pytest.mark.parametrize(
    "mode", [PermissionMode.DEFAULT, PermissionMode.AUTO_APPROVE]
)
def test_changing_dotenv_is_always_asked(mode, command):
    """The hole a review found in plan 0049 as first shipped.

    ``.env`` can set ``OMICSCLAW_PERMISSION_MODE=bypass-all``, which is
    decided before every other check, so one unsupervised write turns the
    gate off from the next start. Under 0049's ``s`` —— and under
    ``auto-approve`` —— that write used to be an ordinary call.
    """
    _, human = run(PermissionGate(mode=mode), Asking(), {"command": command})

    assert human.count == 1
    assert human.asked[0].ask_every_time is True


def test_writing_dotenv_with_a_file_tool_is_always_asked():
    gate = PermissionGate(mode=PermissionMode.AUTO_APPROVE)
    tool = Asking("write_file", schema=PATH_SCHEMA)

    _, human = run(gate, tool, {"path": ".env"})

    assert human.count == 1
    assert human.asked[0].ask_every_time is True


@pytest.mark.parametrize(
    "text",
    [
        "python -c 'import os; print(os.environ)'",
        "direnv allow .envrc",
        "source .venv/bin/activate",
        "conda env list",
    ],
)
def test_things_that_only_look_like_dotenv_are_not_protected(text):
    assert DOTENV_NAME.search(text) is None


# ---- review of the implementation (2026-09-23) --------------------------


_WEB_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


@pytest.mark.parametrize("path", [".OMICSCLAW/settings.json", ".ENV", "./.Env.local"])
def test_letter_case_does_not_open_a_protected_file(path):
    """On macOS and Windows ``.ENV`` *is* ``.env``."""
    gate = PermissionGate(mode=PermissionMode.AUTO_APPROVE)
    tool = Asking("write_file", schema=PATH_SCHEMA)

    _, human = run(gate, tool, {"path": path})

    assert human.count == 1


@pytest.mark.parametrize(
    "path", ["perm.json", "./perm.json", "sub/../perm.json", "PERM.JSON"]
)
def test_a_rule_file_kept_elsewhere_is_protected_by_its_name(tmp_path, path):
    """A relative path names the rule file as surely as the absolute one."""
    gate = PermissionGate(
        mode=PermissionMode.AUTO_APPROVE, rules=RuleStore(tmp_path / "perm.json")
    )
    tool = Asking("write_file", schema=PATH_SCHEMA)

    _, human = run(gate, tool, {"path": path})

    assert human.count == 1


def test_the_default_rule_files_name_alone_is_not_protected(tmp_path):
    """``settings.json`` is protected by its directory, or every editor's
    configuration would be a question."""
    store = RuleStore(tmp_path / PROTECTED_DIRNAME / "settings.json")
    gate = PermissionGate(mode=PermissionMode.AUTO_APPROVE, rules=store)
    tool = Silent("write_file", schema=PATH_SCHEMA)

    _, human = run(gate, tool, {"path": ".vscode/settings.json"})

    assert human.count == 0


def test_a_tool_that_only_mentions_dotenv_is_not_stopped():
    """A search for ".env files" changes no file; a card saying it does is a
    question nobody can answer truthfully."""
    gate = PermissionGate(mode=PermissionMode.AUTO_APPROVE)
    # Not read-only: a read-only tool skips the protected stage anyway, and
    # would pass this test whether the gate looked at the argument's name
    # or not.
    tool = Asking("web_search", schema=_WEB_SCHEMA)

    _, human = run(gate, tool, {"query": "how do .env files work"})

    assert human.count == 0
    assert tool.calls


def test_protects_says_no_rule_can_reach_the_call(tmp_path):
    gate = PermissionGate(rules=RuleStore(tmp_path / "settings.json"))
    policy = Asking().policy
    schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }

    assert gate.protects('{"command": "echo x >> .env"}', policy=policy, schema=schema)
    assert not gate.protects('{"command": "ls"}', policy=policy, schema=schema)
