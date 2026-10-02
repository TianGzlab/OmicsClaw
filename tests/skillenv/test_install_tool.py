"""``install_skill_deps`` as a tool: schema, policy, whitelist, the card and the result (plan 0061 case 21).

These tests replace the two moving parts the tool is built on — the
inventory of the ``python`` ``bash`` runs and the overlay builder — with
fakes, so they pin the tool's own decisions:

* ``packages`` is required and names only what is under the skill's
  ``## Dependencies`` (Q3 = b, Q8); a registry entry installs ``[key, *also]``
  and its ``install`` string is never parsed. Git-only and R names never
  reach pip, and a call with nothing installable asks nobody.
* Before the card nothing but the inventory runs: no pip subcommand, no
  directory. A refusal leaves the overlay root untouched.
* The card (§4.5 step 6, version 7.2) says packages come from this
  machine's pip configuration and that OmicsClaw does not check where that
  points; it lists no sources and says nothing about hashes (Q24). It warns
  that a dependency named by direct URL may have its build script run while
  resolving (Q33 = a).
* The installation runs with the engine's per-tool timeout paused; the
  result names every wheel, where it came from and whether that was plain
  text, and gives the command to run the skill with the overlay.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import contextmanager

import pytest

from omicsclaw.skillenv.overlay import Artifact, FillPlan, Kept, OverlayResult
from omicsclaw.skillenv.registry import read_registry
from omicsclaw.skillenv.tool import (
    INSTALL_SKILL_DEPS_POLICY,
    INSTALL_SKILL_DEPS_SCHEMA,
    INSTALL_SKILL_DEPS_TOOL_NAME,
    install_skill_deps_tool,
)
from omicsclaw.tools.base import ApprovalMode, RiskLevel
from omicsclaw.tools.context import (
    ApprovalDecision,
    ApprovalDenied,
    use_timeout_pause,
    use_tool_context,
)
from omicsclaw.tools.function_tool import ToolArgumentError

from .installing import SKILL, make_skills


def _inventory_json(*, missing=(), prefix=None, base_prefix=None, pip="25.3"):
    prefix = prefix or sys.prefix
    return json.dumps({
        "executable": "/base/bin/python", "real_executable": "/base/bin/python3.11", "version": "3.11.15",
        "prefix": prefix, "base_prefix": base_prefix or prefix, "mtime_ns": 1, "platform": "linux",
        "machine": "x86_64", "pip_version": pip, "missing": list(missing),
        "records": [["numpy", "2.0.2", "numpy-2.0.2.dist-info"]], "top_level": {"numpy": "package"},
    })


class _Inventory:
    location = "local"

    def __init__(self, **kwargs):
        self.output = _inventory_json(**kwargs)
        self.calls = []

    async def run(self, command, *, cwd, timeout, env=None):
        self.calls.append((command, env))
        return 0, self.output


class _Builder:
    """Stands in for OverlayBuilder; records whether the timeout pause was in force."""

    def __init__(self, tmp_path, result=None, finished=False):
        self.root = tmp_path / "envs"
        self.result = result
        self.done = finished
        self.builds = []
        self.paused_during_build = None
        self.pause_state = None

    def python(self, key):
        return self.root / key / ".venv" / "bin" / "python"

    def finished(self, key):
        return self.done

    async def build(self, request, inventory, base, key, *, progress=None):
        self.builds.append((request, key))
        self.paused_during_build = self.pause_state["on"] if self.pause_state else None
        return self.result or OverlayResult("installed", key, self.python(key))


def _tool(tmp_path, *, inventory=None, builder=None, declared=None, registry=None, pyproject=None,
          second=None, step_runner=None):
    kwargs = {} if declared is None else {"declared": declared}
    skills = make_skills(tmp_path / "skills", registry=registry, **kwargs)
    if second is not None:
        name, packages = second
        folder = tmp_path / "skills" / "demo" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: A second fixture skill.\n---\n\n# {name}\n\n## Dependencies\n\n"
            + ", ".join(f"`{p}`" for p in packages) + "\n"
        )
        from omicsclaw.skills import load_skills

        skills = load_skills(tmp_path / "skills")
    inventory = inventory or _Inventory(missing=("oc_leaf", "oc_multi"))
    builder = builder or _Builder(tmp_path)
    tool = install_skill_deps_tool(
        skills,
        registry=read_registry(tmp_path / "skills" / "_sdk" / "deps.py"),
        probe_runner=inventory,
        workspace=str(tmp_path),
        builder=builder,
        pyproject=pyproject,
        step_runner=step_runner,
    )
    return tool, inventory, builder


def _names(skill):
    return [skill] if isinstance(skill, str) else list(skill)


def _call(tool, packages, *, approve=True, skill=SKILL, pause=None):
    asked = []

    def channel(request):
        asked.append(request)
        return ApprovalDecision(approved=approve, reason="" if approve else "no")

    async def main():
        with use_tool_context(approval=channel):
            if pause is None:
                return await tool.execute(json.dumps({"skills": _names(skill), "packages": packages}))
            with use_timeout_pause(pause):
                return await tool.execute(json.dumps({"skills": _names(skill), "packages": packages}))

    return asyncio.run(main()), asked


# ---- schema and policy ----------------------------------------------------------------------


def test_the_schema_requires_skills_first_and_at_least_one_of_each():
    assert INSTALL_SKILL_DEPS_SCHEMA["required"] == ["skills", "packages"]
    assert INSTALL_SKILL_DEPS_SCHEMA["properties"]["skills"]["type"] == "array"
    assert INSTALL_SKILL_DEPS_SCHEMA["properties"]["skills"]["minItems"] == 1
    assert INSTALL_SKILL_DEPS_SCHEMA["properties"]["packages"]["minItems"] == 1
    assert INSTALL_SKILL_DEPS_SCHEMA["additionalProperties"] is False


def test_the_policy_is_declared_field_by_field():
    policy = INSTALL_SKILL_DEPS_POLICY
    assert policy.risk_level is RiskLevel.HIGH and policy.approval_mode is ApprovalMode.ASK
    assert policy.prompts_for_itself and policy.touches_network
    assert not policy.read_only and not policy.concurrency_safe and not policy.allowed_in_background
    assert not policy.writes_workspace and not policy.writes_config
    assert policy.tags == frozenset({"skills", "environment", "network"})


def test_the_tool_is_named_and_described(tmp_path):
    tool, _, _ = _tool(tmp_path)
    assert tool.name == INSTALL_SKILL_DEPS_TOOL_NAME
    assert "only" in tool.definition().description and "method" in tool.definition().description


# ---- what may be asked for ------------------------------------------------------------------


def test_an_unknown_skill_is_an_argument_error(tmp_path):
    tool, _, _ = _tool(tmp_path)
    with pytest.raises(ToolArgumentError, match="not in the skill index"):
        _call(tool, ["oc-leaf"], skill="no-such-skill")


def test_an_empty_package_list_is_an_argument_error(tmp_path):
    tool, inventory, _ = _tool(tmp_path)
    with pytest.raises(ToolArgumentError):
        _call(tool, [])
    assert inventory.calls == []


def test_a_package_not_under_dependencies_is_refused(tmp_path):
    tool, inventory, builder = _tool(tmp_path)
    with pytest.raises(ToolArgumentError, match='torch not under the "## Dependencies" of oc-skill'):
        _call(tool, ["oc-leaf", "torch"])
    assert inventory.calls == [] and builder.builds == []


def test_names_match_in_their_normalised_form(tmp_path):
    tool, _, builder = _tool(tmp_path)
    _call(tool, ["OC_Leaf"])
    assert builder.builds[0][0].names == ("oc-leaf",)


def test_a_registry_entry_expands_to_its_key_and_also(tmp_path):
    """The entry's ``install`` string is ``Rscript …`` on purpose: only ``[key, *also]`` is used."""
    tool, _, builder = _tool(tmp_path)
    output, asked = _call(tool, ["oc-multi"])
    (request, _) = builder.builds[0]
    assert request.specs == ("oc-multi", "oc-extra")
    assert "  oc-multi\n  oc-extra\n" in asked[0].reason


def test_pyproject_constraints_are_applied(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "omicsclaw"\n[project.optional-dependencies]\n'
                         'x = ["oc-leaf >= 1.0, <2", "omicsclaw[x]"]\n')
    tool, _, builder = _tool(tmp_path, pyproject=pyproject)
    _call(tool, ["oc-leaf"])
    assert builder.builds[0][0].specs == ("oc-leaf>=1.0,<2",)


def test_git_and_r_names_never_reach_pip_and_ask_nobody(tmp_path):
    tool, inventory, builder = _tool(tmp_path)
    output, asked = _call(tool, ["pybanksy", "xcms"])
    assert asked == [] and builder.builds == [] and inventory.calls == []
    assert "git-only" in output and "Banksy_py.git" in output and "omicsclaw_banksy" in output
    assert "R package" in output


def test_packages_the_base_already_imports_ask_nobody(tmp_path):
    tool, _, builder = _tool(tmp_path, inventory=_Inventory(missing=()))
    output, asked = _call(tool, ["oc-leaf"])
    assert asked == [] and builder.builds == []
    assert "Nothing to install" in output and "oc-leaf" in output


def test_an_existing_overlay_is_reused_without_asking(tmp_path):
    builder = _Builder(tmp_path, finished=True)
    tool, _, _ = _tool(tmp_path, builder=builder)
    output, asked = _call(tool, ["oc-leaf"])
    assert asked == [] and builder.builds == []
    assert "already exists" in output and "PYTHONNOUSERSITE=1" in output


def test_a_virtual_environment_as_base_is_refused(tmp_path):
    tool, _, builder = _tool(tmp_path, inventory=_Inventory(missing=("oc_leaf",), prefix="/v", base_prefix="/b"))
    output, asked = _call(tool, ["oc-leaf"])
    assert asked == [] and builder.builds == []
    assert "virtual environment" in output and "refused" in output


def test_an_old_pip_is_refused(tmp_path):
    tool, _, builder = _tool(tmp_path, inventory=_Inventory(missing=("oc_leaf",), pip="21.3"))
    output, asked = _call(tool, ["oc-leaf"])
    assert asked == [] and builder.builds == [] and "22.2" in output


def test_a_direct_url_in_the_registry_fails_before_anything_runs(tmp_path):
    registry = {"oc-leaf": {"module": "oc_leaf", "kind": "pip", "install": "pip install oc-leaf",
                            "description": "d", "also": ["oc-far @ http://127.0.0.1:9/oc_far-1.0.tar.gz"]}}
    tool, inventory, builder = _tool(tmp_path, registry=registry)
    output, asked = _call(tool, ["oc-leaf"])
    assert inventory.calls == [] and asked == [] and builder.builds == []
    assert "skills/_sdk/deps.py: entry 'oc-leaf' field also" in output
    assert "Nothing was run" in output


def test_a_package_may_come_from_any_listed_skill(tmp_path):
    tool, _, builder = _tool(tmp_path, second=("oc-other", ["oc-multi"]))
    _call(tool, ["oc-leaf", "oc-multi"], skill=[SKILL, "oc-other"])
    request = builder.builds[0][0]
    assert request.skills == (SKILL, "oc-other")
    assert set(request.names) == {"oc-leaf", "oc-multi"}


def test_a_package_under_none_of_the_skills_names_what_each_declares(tmp_path):
    tool, inventory, _ = _tool(tmp_path, declared=["oc-leaf"], second=("oc-other", ["oc-multi"]))
    with pytest.raises(ToolArgumentError) as caught:
        _call(tool, ["torch"], skill=[SKILL, "oc-other"])
    message = str(caught.value)
    assert f"{SKILL} declares: oc-leaf" in message and "oc-other declares: oc-multi" in message
    assert inventory.calls == []


def test_the_card_names_every_skill(tmp_path):
    tool, _, _ = _tool(tmp_path, second=("oc-other", ["oc-multi"]))
    _, asked = _call(tool, ["oc-leaf"], skill=[SKILL, "oc-other"])
    assert f"for skills {SKILL}, oc-other, wheels only" in asked[0].reason


def test_the_result_says_how_to_run_a_module_with_the_overlay(tmp_path):
    runner = str(tmp_path / "skills" / "_sdk" / "notebook" / "run.py")
    tool, _, builder = _tool(tmp_path, step_runner=runner)
    output, _ = _call(tool, ["oc-leaf"])
    python = builder.python(builder.builds[0][1])
    assert f"PYTHONNOUSERSITE=1 {python} {runner} run analysis/<NN_slug>" in output
    assert "or run a skill's CLI with it:" in output


# ---- the card ----------------------------------------------------------------------------------


def test_the_card_text(tmp_path):
    tool, _, builder = _tool(tmp_path)
    _, asked = _call(tool, ["oc-leaf"])
    (request,) = asked
    card = request.reason
    assert request.tool_name == "install_skill_deps" and not request.reason_shows_call
    assert json.loads(request.arguments) == {"skills": [SKILL], "packages": ["oc-leaf"]}
    assert card.startswith("install into an isolated overlay environment (the base environment is not changed):")
    assert "  oc-leaf\n" in card and f"for skill {SKILL}, wheels only" in card
    assert "packages come from this machine's pip configuration" in card
    assert "OmicsClaw does not check where that points" in card
    assert "pip may run that dependency's build script while" in card
    assert "overlay: " in card and "/base/bin/python 3.11.15" in card
    assert "hash" not in card.lower()
    for word in ("index-url", "http://", "https://", "[PLAINTEXT]", "trusted"):
        assert word not in card


def test_a_refusal_changes_nothing_and_runs_no_pip(tmp_path):
    tool, inventory, builder = _tool(tmp_path)
    with pytest.raises(ApprovalDenied):
        _call(tool, ["oc-leaf"], approve=False)
    assert builder.builds == [] and not builder.root.exists()
    assert len(inventory.calls) == 1 and "pip" not in inventory.calls[0][0].split("-c")[0]


def test_the_inventory_runs_without_the_user_site(tmp_path):
    """The overlay's commands run with ``PYTHONNOUSERSITE=1``, so the base is judged the same way."""
    tool, inventory, _ = _tool(tmp_path)
    _call(tool, ["oc-leaf"])
    ((_, env),) = inventory.calls
    assert env == {"PYTHONNOUSERSITE": "1"}


# ---- running and reporting ------------------------------------------------------------------


def test_the_installation_runs_with_the_tool_timeout_paused(tmp_path):
    state = {"on": False}

    @contextmanager
    def pause():
        state["on"] = True
        try:
            yield
        finally:
            state["on"] = False

    builder = _Builder(tmp_path)
    builder.pause_state = state
    tool, _, _ = _tool(tmp_path, builder=builder)
    _call(tool, ["oc-leaf"], pause=pause)
    assert builder.paused_during_build is True


def _artifact(name, version, url_source, transport):
    return Artifact(name, version, f"{name}-{version}-py3-none-any.whl", url_source, transport, True)


def test_the_result_lists_wheels_sources_and_plaintext(tmp_path):
    builder = _Builder(tmp_path)
    builder.result = OverlayResult(
        "installed", "0123456789abcdef", builder.root / "0123456789abcdef" / ".venv" / "bin" / "python",
        installed=(
            _artifact("oc_leaf", "1.0", "http://10.20.16.126:8081", "http"),
            _artifact("oc_dep", "1.0", "https://files.pythonhosted.org", "https"),
        ),
        kept_from_base=(Kept("llvmlite", ("0.43.0", "0.47.0"), "0.43.0"),),
        namespaces=("docs",),
        pth_files=("oc_hook.pth",),
        imports={"oc_leaf": "", "banksy": "ModuleNotFoundError: No module named 'banksy'"},
    )
    tool, _, _ = _tool(tmp_path, builder=builder)
    output, _ = _call(tool, ["oc-leaf", "pybanksy"])
    assert "- oc_leaf==1.0  oc_leaf-1.0-py3-none-any.whl  from http://10.20.16.126:8081 (plaintext)" in output
    assert "- oc_dep==1.0  oc_dep-1.0-py3-none-any.whl  from https://files.pythonhosted.org\n" in output
    assert "llvmlite — the index wanted 0.43.0; the base records 0.43.0, 0.47.0 (ambiguous metadata)" in output
    assert "pip check: no new problems." in output
    assert "docs" in output and "oc_hook.pth" in output
    assert "Imports in the overlay: oc_leaf ok\n" in output
    assert "Other modules of the skill that do not import here (not requested): banksy" in output
    assert "Not installed (git-only): pybanksy" in output
    assert f"PYTHONNOUSERSITE=1 {builder.root}/0123456789abcdef/.venv/bin/python " in output
    assert "oc_skill.py" in output


def test_a_failure_after_the_dry_run_carries_the_plan(tmp_path):
    builder = _Builder(tmp_path)
    plan = FillPlan(install=(_artifact("oc_leaf", "1.0", "file:/tmp/wh", "file"),),
                    kept_from_base=(Kept("packaging", ("24.1",), "0.9"),), foreign=())
    builder.result = OverlayResult(
        "failed", "0123456789abcdef", builder.root / "x", reason="the installation breaks declared requirements",
        violations=("oc-needs-old 1.0 has requirement packaging<1, but you have packaging 24.1.",), plan=plan,
        log_tail="Looking in indexes: http://***@idx.example/simple",
    )
    tool, _, _ = _tool(tmp_path, builder=builder)
    output, _ = _call(tool, ["oc-leaf"])
    assert output.startswith("install_skill_deps failed: the installation breaks declared requirements")
    assert "oc-needs-old 1.0 has requirement packaging<1" in output
    assert "oc_leaf==1.0  oc_leaf-1.0-py3-none-any.whl  from file:/tmp/wh" in output
    assert "report this rather than switching to another method" in output
    assert "Nothing was changed" in output
