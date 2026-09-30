"""``install_skill_deps`` behind the permission gate (plan 0061 case 22, §4.5 surface table, Q5 = a).

The approval posture is the same as ``bash``'s: the default mode asks (with
the tool's own card, since it declares ``prompts_for_itself``), auto-approve
and bypass-all do not, read-only refuses. That is exactly why the tool is not
mounted unless a deployment sets ``skill_env=install`` (Q7). An explicit
``ask`` rule makes every call ask and the question may not be answered by a
standing session grant; "always allow" writes ``install_skill_deps(<skill>)``,
because ``skill`` is the schema's first required string. A rule about
``bash(pip install*)`` says nothing about this tool — rules match tool names —
which is documented in AGENTS.md and pinned here so nobody reads it the
other way.

With ``install`` configured the mounted list is the default one with this
tool before ``task``, and it is gated like every other tool.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig, SkillEnvMode
from omicsclaw.permission import CONFIG_KEY, GatedTool, PermissionGate, PermissionMode, Rules, RuleStore, gate_tools
from omicsclaw.schema import ToolCall
from omicsclaw.skillenv.registry import read_registry
from omicsclaw.skillenv.tool import install_skill_deps_tool
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools.context import ApprovalDecision, use_tool_context
from tests.entry.test_permission_wiring import MOUNTED

from .conftest import FIXTURE_SKILLS
from .installing import SKILL, make_skills
from .test_install_tool import _Builder, _Inventory

ARGS = json.dumps({"skill": SKILL, "packages": ["oc-leaf"]})


def _tool(tmp_path):
    skills = make_skills(tmp_path / "skills")
    builder = _Builder(tmp_path)
    tool = install_skill_deps_tool(
        skills,
        registry=read_registry(tmp_path / "skills" / "_sdk" / "deps.py"),
        probe_runner=_Inventory(missing=("oc_leaf",)),
        workspace=str(tmp_path),
        builder=builder,
    )
    return tool, builder


def _run(tool, gate, *, approve=True):
    asked = []

    def channel(request):
        asked.append(request)
        return ApprovalDecision(approved=approve, reason="" if approve else "no")

    async def main():
        registry = ToolRegistry(gate_tools([tool], gate))
        with use_tool_context(approval=channel):
            return await registry.execute(ToolCall(id="1", name=tool.name, arguments=ARGS))

    return asyncio.run(main()), asked


def _gate(mode, **sections):
    return PermissionGate(mode=mode, rules=Rules.from_config({CONFIG_KEY: sections}))


def test_the_default_mode_asks_with_the_tools_card(tmp_path):
    tool, builder = _tool(tmp_path)
    result, asked = _run(tool, _gate(PermissionMode.DEFAULT))
    assert not result.is_error and len(asked) == 1
    assert asked[0].reason.startswith("install into an isolated overlay environment")
    assert len(builder.builds) == 1


@pytest.mark.parametrize("mode", [PermissionMode.AUTO_APPROVE, PermissionMode.BYPASS_ALL])
def test_auto_approve_and_bypass_do_not_ask(tmp_path, mode):
    tool, builder = _tool(tmp_path)
    result, asked = _run(tool, _gate(mode))
    assert not result.is_error and asked == [] and len(builder.builds) == 1


def test_read_only_refuses(tmp_path):
    tool, builder = _tool(tmp_path)
    result, asked = _run(tool, _gate(PermissionMode.READ_ONLY))
    assert result.is_error and "read-only" in result.output
    assert asked == [] and builder.builds == []


def test_an_ask_rule_asks_even_under_auto_approve_and_no_standing_grant_answers_it(tmp_path):
    tool, builder = _tool(tmp_path)
    result, asked = _run(tool, _gate(PermissionMode.AUTO_APPROVE, ask=["install_skill_deps"]))
    assert len(asked) == 1 and asked[0].ask_every_time
    assert len(builder.builds) == 1


def test_always_allow_writes_a_rule_for_the_skill(tmp_path):
    tool, builder = _tool(tmp_path)
    store = RuleStore(tmp_path / ".omicsclaw" / "settings.json")
    gate = PermissionGate(mode=PermissionMode.DEFAULT, rules=store)
    pattern = gate.remember("install_skill_deps", ARGS, schema=tool.definition().input_schema)
    assert pattern == f"install_skill_deps({SKILL})"
    result, asked = _run(tool, gate)
    assert asked == [] and len(builder.builds) == 1


def test_a_bash_pip_install_rule_does_not_reach_this_tool(tmp_path):
    tool, builder = _tool(tmp_path)
    result, asked = _run(tool, _gate(PermissionMode.DEFAULT, deny=["bash(pip install*)"]))
    assert not result.is_error and len(asked) == 1 and len(builder.builds) == 1


def test_a_refusal_through_the_gate_builds_nothing(tmp_path):
    tool, builder = _tool(tmp_path)
    result, asked = _run(tool, _gate(PermissionMode.DEFAULT), approve=False)
    assert result.is_error and len(asked) == 1 and builder.builds == []


@pytest.fixture
def offline(monkeypatch):
    from tests.entry.test_ensemble_golden import _Offline

    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def test_with_install_the_mounted_list_gains_one_gated_tool(tmp_path, offline):
    config = AppConfig(workspace=tmp_path, skills_dir=FIXTURE_SKILLS, ensemble=False,
                       skill_env=SkillEnvMode.INSTALL, skill_env_dir=tmp_path / "envs")
    app = assembly.build_app(config)
    try:
        names = tuple(app.registry.names())
        assert names == (*MOUNTED[:-1], "install_skill_deps", "task")
        assert isinstance(app.registry.get("install_skill_deps"), GatedTool)
    finally:
        if app.memory is not None:
            app.memory.close()
