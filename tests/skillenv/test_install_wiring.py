"""How a deployment turns on ``install_skill_deps`` (plan 0061 cases 23 and 6b, §4.10 mount matrix, Q4, Q6).

``skill_env=install`` is the only way to get the tool, and it must be set by
the deployment. It mounts the tool when ``bash`` runs on this machine —
the sandbox off, or requested but degraded (Q4 iii, "mount and treat as
local") — and never while a sandbox runs, with or without a network (Q4 i,
ii): an overlay on the host is not usable in the container. The tool is
appended after the last foundation tool, so it comes after ``run_skill`` when
that is mounted and before every MCP tool and ``task``; the system prompt
and every other definition stay byte-identical to the ablation golden files.

Since version 7.2 (D8) no package-source setting exists: ``install`` starts
with none. One refusal remains: an unreadable dependency registry (Q23 —
without ``kind`` git packages cannot be told apart and ``also`` cannot be
expanded), which refuses start-up rather than quietly running without the
tool. ``oc desktop`` accepts ``install``: its approval cards are answered
through ``/chat/permission``.

The last tests are the environment note: with the tool mounted it says so,
and on this machine it names an existing overlay that covers a missing
package — but only one built on this very base (path, version, prefix,
modification time and distributions digest).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig, AppConfigError, SandboxMode, SkillEnvMode, resolve_app_config
from omicsclaw.entry.sandbox import SandboxBinding
from omicsclaw.entry.skill_env import build_skill_env
from omicsclaw.skillenv.overlay import FINGERPRINT, META, base_distributions
from omicsclaw.skillenv.probe import LocalProbeRunner, run_inventory
from omicsclaw.tools.builtin.bash import CommandOutcome
from tests.entry.test_ensemble_golden import (
    PROMPT_FILE,
    TOOLS_FILE,
    _FakeMCP,
    _runner,
    dump_tools,
    golden_config,
    normalised_prompt,
    serialised_tools,
)

from .conftest import FIXTURE_SKILLS


@pytest.fixture
def offline(monkeypatch):
    from tests.entry.test_ensemble_golden import _Offline

    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def _close(app) -> None:
    if app.memory is not None:
        app.memory.close()


# ---- configuration ----------------------------------------------------------------------------


def test_install_parses_from_the_flag_and_the_environment(tmp_path):
    assert resolve_app_config(["--skill-env", "install"], {}, workspace=tmp_path).skill_env is SkillEnvMode.INSTALL
    assert resolve_app_config([], {"OMICSCLAW_SKILL_ENV": "INSTALL"}, workspace=tmp_path).skill_env is SkillEnvMode.INSTALL


def test_a_relative_overlay_directory_is_made_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = resolve_app_config(["--skill-env-dir", "rel/envs"], {}, workspace=tmp_path)
    assert config.skill_env_dir == tmp_path / "rel" / "envs"
    from_env = resolve_app_config([], {"OMICSCLAW_SKILL_ENV_DIR": "~/envs"}, workspace=tmp_path)
    assert from_env.skill_env_dir.is_absolute() and "~" not in str(from_env.skill_env_dir)


def test_the_overlay_directory_and_install_limit_are_options(tmp_path):
    config = resolve_app_config(
        ["--skill-env-dir", str(tmp_path / "envs"), "--skill-env-install-timeout", "90"], {}, workspace=tmp_path
    )
    assert config.skill_env_dir == tmp_path / "envs" and config.skill_env_install_timeout_s == 90.0
    from_env = resolve_app_config(
        [], {"OMICSCLAW_SKILL_ENV_DIR": str(tmp_path / "e"), "OMICSCLAW_SKILL_ENV_INSTALL_TIMEOUT_S": "60"},
        workspace=tmp_path,
    )
    assert from_env.skill_env_dir == tmp_path / "e" and from_env.skill_env_install_timeout_s == 60.0
    defaults = AppConfig(workspace=tmp_path)
    assert defaults.skill_env_dir is None and defaults.skill_env_install_timeout_s == 1800.0


@pytest.mark.parametrize("raw", ["0", "-5", "soon"])
def test_the_install_limit_must_be_a_positive_number(tmp_path, raw):
    with pytest.raises(AppConfigError):
        resolve_app_config(["--skill-env-install-timeout", raw], {}, workspace=tmp_path)


def test_a_non_positive_limit_is_refused_however_it_arrives(tmp_path):
    with pytest.raises(AppConfigError):
        resolve_app_config([], {}, workspace=tmp_path, skill_env_install_timeout_s=0.0)
    with pytest.raises(AppConfigError):
        AppConfig(workspace=tmp_path, skill_env_install_timeout_s=-1.0)


# ---- the mount matrix and the tool's position ---------------------------------------------------


def _names(app):
    return [definition.name for definition in app.registry.available_tools()]


def _golden_install(tmp_path, **overrides):
    """The golden deployment on a copy of its skills tree that also has a registry, with ``install`` on."""
    import shutil

    from tests.entry.test_ensemble_golden import FAKE_SKILLS

    workspace = tmp_path / "ws"
    workspace.mkdir()
    skills = tmp_path / "skills"
    shutil.copytree(FAKE_SKILLS, skills)
    (skills / "_sdk").mkdir()
    (skills / "_sdk" / "deps.py").write_text((FIXTURE_SKILLS / "_sdk" / "deps.py").read_text())
    config = golden_config(workspace, skill_env=SkillEnvMode.INSTALL, skill_env_dir=tmp_path / "envs", **overrides)
    return workspace, AppConfig(**{**{f: getattr(config, f) for f in config.__dataclass_fields__}, "skills_dir": skills})


def test_install_inserts_the_tool_before_task_and_changes_nothing_else(tmp_path, offline):
    workspace, config = _golden_install(tmp_path, ensemble=False)
    app = assembly.build_app(config)
    try:
        assert normalised_prompt(app, workspace) == PROMPT_FILE.read_text(encoding="utf-8")
        tools = serialised_tools(app.registry.available_tools())
        names = [tool["name"] for tool in tools]
        position = names.index("install_skill_deps")
        assert names[position - 1] == "memory_write" and names[position + 1] == "task"
        assert dump_tools(tools[:position] + tools[position + 1:]) == TOOLS_FILE.read_text(encoding="utf-8")
        assert app.skill_env is not None and app.skill_env.tool is not None
    finally:
        _close(app)


def test_with_run_skill_the_tool_comes_after_it(tmp_path, offline):
    _, config = _golden_install(tmp_path, ensemble=True)
    app = assembly.build_app(config, ensemble=_runner(config))
    try:
        names = _names(app)
        # The ensemble mounts run_skill, then its other tools (optimize_params last).
        assert names.index("run_skill") < names.index("install_skill_deps")
        assert names[-3:] == ["optimize_params", "install_skill_deps", "task"]
    finally:
        _close(app)


def test_the_tool_comes_before_every_mcp_tool(tmp_path, offline):
    _, config = _golden_install(tmp_path, ensemble=False)
    app = assembly.build_app(config, mcp=_FakeMCP())
    try:
        assert _names(app)[-4:] == ["memory_write", "install_skill_deps", "mcp__demo__echo", "task"]
    finally:
        _close(app)


class _Container:
    def __init__(self):
        self.calls = []

    async def run_bash(self, command, cwd, timeout):
        self.calls.append(command)
        return CommandOutcome(output="{}", exit_code=0)


def _skills(config):
    return assembly.build_skill_index(config)


def _install_config(tmp_path, **overrides):
    values = {"workspace": tmp_path, "skills_dir": FIXTURE_SKILLS, "ensemble": False,
              "skill_env": SkillEnvMode.INSTALL, "skill_env_dir": tmp_path / "envs", **overrides}
    return AppConfig(**values)


def test_a_running_sandbox_gets_no_tool_with_or_without_network(tmp_path):
    config = _install_config(tmp_path)
    bound = build_skill_env(config, _skills(config), SandboxBinding(environment=_Container()))
    assert bound is not None and bound.location == "sandbox" and bound.tool is None
    assert bound.annotate is not None


def test_a_degraded_sandbox_is_treated_as_this_machine(tmp_path):
    config = _install_config(tmp_path, sandbox=SandboxMode.DOCKER, sandbox_image="img")
    binding = SandboxBinding(mode=SandboxMode.DOCKER)
    assert binding.degraded
    bound = build_skill_env(config, _skills(config), binding)
    assert bound.location == "local" and bound.tool is not None


def test_probe_and_off_mount_no_tool(tmp_path):
    for mode in (SkillEnvMode.PROBE, SkillEnvMode.OFF):
        config = _install_config(tmp_path, skill_env=mode)
        bound = build_skill_env(config, _skills(config), SandboxBinding())
        assert bound is None or bound.tool is None


def test_install_starts_without_any_package_source_setting(tmp_path, offline):
    app = assembly.build_app(_install_config(tmp_path))
    try:
        assert "install_skill_deps" in _names(app)
    finally:
        _close(app)


def test_the_overlay_root_defaults_to_the_user_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    config = _install_config(tmp_path, skill_env_dir=None)
    bound = build_skill_env(config, _skills(config), SandboxBinding())
    assert bound.overlay_root == tmp_path / "cache" / "omicsclaw" / "envs"
    configured = _install_config(tmp_path)
    assert build_skill_env(configured, _skills(configured), SandboxBinding()).overlay_root == tmp_path / "envs"


def test_the_tool_sees_the_process_environment_without_the_control_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "bearer")
    monkeypatch.setenv("OC_WIRING_SENTINEL", "yes")
    config = _install_config(tmp_path)
    bound = build_skill_env(config, _skills(config), SandboxBinding())
    environment = bound.environment()
    assert environment.get("OC_WIRING_SENTINEL") == "yes" and "OMICSCLAW_REMOTE_AUTH_TOKEN" not in environment


# ---- refusals ---------------------------------------------------------------------------------------


def _tree_without_registry(tmp_path):
    root = tmp_path / "skills"
    target = root / "demo" / "demo-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text((FIXTURE_SKILLS / "demo" / "demo-skill" / "SKILL.md").read_text())
    return root


def test_install_refuses_to_start_without_a_readable_registry(tmp_path, offline):
    config = _install_config(tmp_path, skills_dir=_tree_without_registry(tmp_path))
    with pytest.raises(AppConfigError, match="skill_env=install needs the dependency registry"):
        build_skill_env(config, _skills(config), SandboxBinding())
    with pytest.raises(AppConfigError):
        assembly.build_app(config)


def test_probe_still_starts_without_a_readable_registry(tmp_path):
    config = _install_config(tmp_path, skills_dir=_tree_without_registry(tmp_path), skill_env=SkillEnvMode.PROBE)
    assert build_skill_env(config, _skills(config), SandboxBinding()).registry_error


@pytest.mark.parametrize("mode", ["install", "probe"])
def test_the_desktop_reaches_its_dependency_check_with_either_mode(mode, capsys, monkeypatch):
    """Web server made unimportable, so the command stops at its dependency
    check instead of serving, whichever interpreter runs the test."""
    import sys

    from omicsclaw.launch import main
    from omicsclaw.launch._surfaces import EXIT_REFUSED

    monkeypatch.setitem(sys.modules, "fastapi", None)
    monkeypatch.setitem(sys.modules, "uvicorn", None)
    code = main(["desktop", "--skill-env", mode], {})
    err = capsys.readouterr().err
    assert code == EXIT_REFUSED
    assert "uvicorn and fastapi" in err
    assert "skill_env=install" not in err


# ---- the note -------------------------------------------------------------------------------------


def _note(bound, skills):
    return asyncio.run(bound.annotate(skills.get("demo-skill"), skills.get_full_content("demo-skill")))


def test_the_note_says_the_tool_is_mounted(tmp_path):
    config = _install_config(tmp_path)
    skills = _skills(config)
    note = _note(build_skill_env(config, skills, SandboxBinding()), skills)
    assert "install_skill_deps can add the ones your method needs to an isolated overlay" in note
    probe_config = _install_config(tmp_path, skill_env=SkillEnvMode.PROBE)
    assert "install_skill_deps can add" not in _note(build_skill_env(probe_config, skills, SandboxBinding()), skills)


def _fake_overlay(root: Path, key: str, inventory, *, digest: str, packages=("oc-missing-pkg",)) -> Path:
    venv = root / key / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / FINGERPRINT).write_text(key)
    meta = {"key": key, "skill": "demo-skill", "packages": list(packages), "base_executable": inventory.real_executable,
            "base_version": inventory.version, "base_prefix": inventory.prefix, "base_mtime_ns": inventory.mtime_ns,
            "base_dists_sha256": digest}
    (root / key / META).write_text(json.dumps(meta))
    return venv / "bin" / "python"


def test_the_note_names_an_overlay_built_on_this_base(tmp_path):
    config = _install_config(tmp_path, skill_env=SkillEnvMode.PROBE)
    skills = _skills(config)
    inventory = asyncio.run(run_inventory(LocalProbeRunner(), (), "", cwd=str(tmp_path),
                                          env={"PYTHONNOUSERSITE": "1"}))
    digest = base_distributions(inventory.records).digest
    good = _fake_overlay(tmp_path / "envs", "0000000000000001", inventory, digest=digest)
    stale = _fake_overlay(tmp_path / "envs", "0000000000000002", inventory, digest="0" * 64)
    other = _fake_overlay(tmp_path / "envs", "0000000000000003", inventory, digest=digest, packages=("unrelated",))
    note = _note(build_skill_env(config, skills, SandboxBinding()), skills)
    assert f"An existing overlay covers some of these: {good}" in note
    assert str(stale) not in note and str(other) not in note


def test_no_overlay_is_named_without_one(tmp_path):
    config = _install_config(tmp_path, skill_env=SkillEnvMode.PROBE)
    skills = _skills(config)
    assert "existing overlay" not in _note(build_skill_env(config, skills, SandboxBinding()), skills)


class _SandboxSeesThisPython:
    """A sandbox whose ``python`` happens to report this machine's interpreter, as a mount could make it."""

    def __init__(self, probe_output: str, inventory_output: str):
        self.outputs = (probe_output, inventory_output)
        self.calls = []

    async def run_bash(self, command, cwd, timeout):
        self.calls.append(command)
        output = self.outputs[1] if "records" in command else self.outputs[0]
        return CommandOutcome(output=output, exit_code=0)


def test_the_sandbox_note_never_names_a_host_overlay(tmp_path):
    """Even when everything on the host would match, an overlay on the host is not usable in the container."""
    config = _install_config(tmp_path, skill_env=SkillEnvMode.PROBE)
    skills = _skills(config)
    inventory = asyncio.run(run_inventory(LocalProbeRunner(), (), "", cwd=str(tmp_path),
                                          env={"PYTHONNOUSERSITE": "1"}))
    digest = base_distributions(inventory.records).digest
    host = _fake_overlay(tmp_path / "envs", "0000000000000001", inventory, digest=digest)
    probe = json.dumps({"executable": inventory.executable, "version": inventory.version, "prefix": inventory.prefix,
                        "base_prefix": inventory.base_prefix, "user_site_enabled": False,
                        "missing": ["oc_missing_pkg"], "from_user_site": [], "versions": {}})
    listed = json.dumps({**{f: getattr(inventory, f) for f in ("executable", "real_executable", "version", "prefix",
                                                                "base_prefix", "mtime_ns", "platform", "machine",
                                                                "pip_version", "missing")},
                         "records": [list(r) for r in inventory.records], "top_level": {}})
    container = _SandboxSeesThisPython(probe, listed)
    note = _note(build_skill_env(config, skills, SandboxBinding(environment=container)), skills)
    assert "oc-missing-pkg" in note and str(host) not in note and "existing overlay" not in note
    assert len(container.calls) == 1 and "records" not in container.calls[0], "the sandbox note looked for overlays"
