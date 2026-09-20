"""The sandbox as a deployment uses it: configured, started, degraded, wired.

Driven through ``tests/sandbox/fake_docker.py`` via ``sandbox_runtime``, so
``open_app`` really spawns a CLI, and ``exec`` really runs the command.

The approval tests pin **effect**, not just resolution, and pin it in the
tightening direction: a relaxed ``bash`` must run with no approval channel
bound, and every case that must stay guarded must be *refused* with no
channel bound — a policy that resolves correctly and is never read is the
failure the tool-registry step already paid for once.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import sys
from pathlib import Path

import pytest

from omicsclaw.engine import AgentEngine
from omicsclaw.entry import SandboxMode, assembly, open_app, resolve_app_config
from omicsclaw.entry.assembly import build_app
from omicsclaw.entry.config import AppConfig, AppConfigError, SkillsIndex
from omicsclaw.entry.sandbox import (
    SandboxBinding,
    bash_policy,
    open_sandbox,
    sandbox_section,
    unstarted_sandbox,
)
from omicsclaw.entry.turn import run_turn
from omicsclaw.sandbox import SandboxConfigError, SandboxError
from omicsclaw.schema import Message, Role, ToolCall
from omicsclaw.tools import ApprovalMode, BashTool, ToolPolicy, Workspace
from tests.entry.test_turn import _Scripted  # type: ignore[import-not-found]
from tests.sandbox._support import FakeDocker

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX processes")


@pytest.fixture
def docker(tmp_path: Path) -> FakeDocker:
    return FakeDocker.install(tmp_path / "fake")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path.resolve()


@pytest.fixture(autouse=True)
def scripted_provider(monkeypatch):
    provider = _Scripted()
    monkeypatch.setattr(assembly, "provider_from_env", lambda p, m: provider)
    return provider


def _config(
    workspace: Path, docker: FakeDocker | None = None, **overrides
) -> AppConfig:
    values: dict = {"workspace": workspace, "skills_index": SkillsIndex.OFF}
    if docker is not None:
        values.update(
            sandbox=SandboxMode.DOCKER,
            sandbox_image="omicsclaw/test:1",
            sandbox_runtime=docker.binary,
        )
    values.update(overrides)
    return AppConfig(**values)


def _run(coro, timeout: float = 60.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


def _bash_call(command: str = "echo hi") -> ToolCall:
    return ToolCall(id="b1", name="bash", arguments=json.dumps({"command": command}))


# ---- configuration -------------------------------------------------------


def test_the_sandbox_is_off_unless_asked_for(workspace):
    config = _config(workspace)

    assert config.sandbox is SandboxMode.OFF
    assert config.sandbox_config() is None
    assert not config.sandbox_required and not config.sandbox_auto_approve


def test_every_sandbox_setting_reaches_the_sandbox_config(workspace):
    config = resolve_app_config(
        argv=[
            "--workspace", str(workspace),
            "--sandbox", "docker",
            "--sandbox-image", "omics:2",
            "--sandbox-network", "omics-net",
            "--sandbox-memory", "64g",
            "--sandbox-cpus", "16",
            "--sandbox-gpus", "all",
            "--sandbox-user", "0:0",
            "--sandbox-mount", "/ref/hg38",
            "--sandbox-mount", "/ref/mm10",
            "--sandbox-bootstrap", "conda activate omics",
            "--sandbox-bootstrap-timeout", "900",
            "--sandbox-runtime", "podman",
            "--sandbox-required", "true",
            "--sandbox-auto-approve", "yes",
        ],
        env={},
    )  # fmt: skip

    sandbox = config.sandbox_config()

    assert sandbox is not None
    assert (sandbox.image, sandbox.network) == ("omics:2", "omics-net")
    assert (sandbox.memory, sandbox.cpus, sandbox.gpus) == ("64g", "16", "all")
    assert sandbox.user == "0:0"
    assert sandbox.read_only_mounts == (Path("/ref/hg38"), Path("/ref/mm10"))
    assert sandbox.bootstrap == "conda activate omics"
    assert sandbox.bootstrap_timeout_s == 900.0
    assert sandbox.runtime == "podman"
    assert config.sandbox_required and config.sandbox_auto_approve


def test_the_environment_spells_them_too(workspace):
    config = resolve_app_config(
        argv=["--workspace", str(workspace)],
        env={
            "OMICSCLAW_SANDBOX": "DOCKER",
            "OMICSCLAW_SANDBOX_IMAGE": "omics:3",
            "OMICSCLAW_SANDBOX_MOUNTS": "/a:/b",
            "OMICSCLAW_SANDBOX_REQUIRED": "0",
            "OMICSCLAW_SANDBOX_AUTO_APPROVE": "on",
        },
    )

    assert config.sandbox is SandboxMode.DOCKER
    assert config.sandbox_mounts == (Path("/a"), Path("/b"))
    assert not config.sandbox_required
    assert config.sandbox_auto_approve


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("OMICSCLAW_SANDBOX", "bwrap"),
        ("OMICSCLAW_SANDBOX_REQUIRED", "maybe"),
        ("OMICSCLAW_SANDBOX_AUTO_APPROVE", "2"),
        ("OMICSCLAW_SANDBOX_BOOTSTRAP_TIMEOUT_S", "ten minutes"),
    ],
)
def test_an_unreadable_setting_is_refused_rather_than_defaulted(
    workspace, variable, value
):
    """A typo in ``AUTO_APPROVE`` that silently read as ``false`` would be
    harmless; one in ``REQUIRED`` that read as ``false`` would quietly drop
    the fail-closed guarantee somebody asked for."""
    with pytest.raises(AppConfigError, match=variable):
        resolve_app_config(argv=["--workspace", str(workspace)], env={variable: value})


def test_the_default_container_user_is_this_process(workspace):
    import os

    config = _config(workspace, sandbox=SandboxMode.DOCKER, sandbox_image="x")

    assert config.sandbox_config().user == f"{os.getuid()}:{os.getgid()}"


def test_docker_without_an_image_is_a_configuration_error(workspace):
    config = _config(workspace, sandbox=SandboxMode.DOCKER)

    with pytest.raises(SandboxConfigError, match="image"):
        config.sandbox_config()
    with pytest.raises(SandboxConfigError):
        _run(open_sandbox(config))


# ---- starting it ---------------------------------------------------------


def test_open_sandbox_starts_one_container_over_the_workspace(docker, workspace):
    async def main():
        binding = await open_sandbox(_config(workspace, docker))
        try:
            return binding, binding.manager.list_all()
        finally:
            await binding.aclose()

    binding, listed = _run(main())

    assert binding.active and not binding.degraded
    assert binding.isolates_network
    assert len(listed) == 1 and listed[0].workspace == workspace
    commands = [call[0] for call in docker.calls()]
    assert commands.index("ps") < commands.index("run"), "orphans are reaped first"
    assert docker.containers() == []


def test_a_sandbox_that_cannot_start_degrades_loudly(docker, workspace, caplog):
    docker.set_flag("daemon_down")

    with caplog.at_level(logging.WARNING, logger="omicsclaw.entry"):
        binding = _run(open_sandbox(_config(workspace, docker)))

    assert binding.degraded and not binding.active
    assert "daemon" in binding.unavailable
    assert binding.manager is None
    assert any("without isolation" in record.message for record in caplog.records)


def test_a_required_sandbox_that_cannot_start_refuses_to_run(docker, workspace):
    docker.set_flag("fail_run")

    with pytest.raises(SandboxError, match="sandbox_required"):
        _run(open_sandbox(_config(workspace, docker, sandbox_required=True)))

    assert docker.containers() == []


def test_off_is_an_inactive_binding_with_no_prompt_section(workspace):
    binding = _run(open_sandbox(_config(workspace)))

    assert binding == SandboxBinding()
    assert sandbox_section(binding) is None


# ---- build_app without open_app ------------------------------------------


def test_build_app_off_leaves_bash_and_the_prompt_as_they_were(workspace):
    app = build_app(_config(workspace))

    assert app.sandbox is not None and app.sandbox.mode is SandboxMode.OFF
    assert "Execution sandbox" not in app.prompt.render().system_prompt


def test_build_app_cannot_start_a_sandbox_and_says_so(docker, workspace):
    """``build_app`` is synchronous and starts nothing. A deployment that
    asked for a sandbox and got ``build_app`` must not believe it has one."""
    app = build_app(_config(workspace, docker))
    rendered = app.prompt.render().system_prompt

    assert app.sandbox.degraded
    assert "requested but is not running" in rendered
    assert "use open_app" in rendered
    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.ASK


def test_build_app_refuses_when_the_sandbox_is_required(docker, workspace):
    with pytest.raises(SandboxError, match="sandbox_required"):
        build_app(_config(workspace, docker, sandbox_required=True))


# ---- the approval policy: resolution -------------------------------------


_ASK = ToolPolicy(approval_mode=ApprovalMode.ASK)


def _active(network_isolated: bool = True) -> SandboxBinding:
    from omicsclaw.sandbox import SandboxConfig

    return SandboxBinding(
        mode=SandboxMode.DOCKER,
        environment=object(),  # type: ignore[arg-type]
        config=SandboxConfig(
            image="x", network="none" if network_isolated else "bridge"
        ),
    )


@pytest.mark.parametrize(
    ("binding", "auto", "expected"),
    [
        (_active(), True, ApprovalMode.AUTO),
        (_active(), False, ApprovalMode.ASK),
        (_active(network_isolated=False), True, ApprovalMode.ASK),
        (
            SandboxBinding(mode=SandboxMode.DOCKER, unavailable="daemon down"),
            True,
            ApprovalMode.ASK,
        ),
        (SandboxBinding(), True, ApprovalMode.ASK),
    ],
    ids=["running+none+auto", "not-asked", "open-network", "degraded", "off"],
)
def test_bash_is_relaxed_only_in_a_running_offline_sandbox(binding, auto, expected):
    assert bash_policy(binding, _ASK, auto_approve=auto).approval_mode is expected


# ---- the approval policy: effect -----------------------------------------


async def _open(config: AppConfig):
    app = await open_app(config)
    return app


def test_an_auto_approved_bash_runs_in_the_sandbox_with_no_one_asked(
    docker, workspace
):
    """The acceptance criterion the sandbox step was given: isolation good
    enough that ``bash`` no longer needs a person per command."""

    async def main():
        app = await _open(_config(workspace, docker, sandbox_auto_approve=True))
        try:
            return app, await app.registry.execute(_bash_call("echo from-inside"))
        finally:
            await app.aclose()

    app, result = _run(main())

    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.AUTO
    assert result.output == "from-inside\n" and not result.is_error
    assert any(call[0] == "exec" for call in docker.calls())
    assert docker.containers() == [], "aclose removes the container"


@pytest.mark.parametrize(
    "overrides",
    [
        {"sandbox_auto_approve": False},
        {"sandbox_auto_approve": True, "sandbox_network": "bridge"},
    ],
    ids=["not-asked", "open-network"],
)
def test_a_guarded_bash_is_refused_with_no_approval_channel(
    docker, workspace, overrides
):
    async def main():
        app = await _open(_config(workspace, docker, **overrides))
        try:
            return app, await app.registry.execute(_bash_call())
        finally:
            await app.aclose()

    app, result = _run(main())

    assert app.sandbox.active
    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.ASK
    assert result.is_error
    assert not any(call[0] == "exec" for call in docker.calls())


def test_a_degraded_sandbox_never_relaxes_bash(docker, workspace):
    docker.set_flag("daemon_down")

    async def main():
        app = await _open(_config(workspace, docker, sandbox_auto_approve=True))
        try:
            return app, await app.registry.execute(_bash_call())
        finally:
            await app.aclose()

    app, result = _run(main())

    assert app.sandbox.degraded
    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.ASK
    assert result.is_error


def test_a_bash_passed_in_by_the_caller_is_never_relaxed(docker, workspace):
    """Only the ``bash`` the assembly built over the sandbox is known to run
    in it; a caller's own tool may run anywhere."""
    own = BashTool(Workspace(workspace))

    async def main():
        app = await open_app(
            _config(workspace, docker, sandbox_auto_approve=True), tools=[own]
        )
        await app.aclose()
        return app

    app = _run(main())

    assert app.registry.policy_for("bash").approval_mode is ApprovalMode.ASK


# ---- through the main loop -----------------------------------------------


def test_the_react_loop_runs_bash_inside_the_sandbox(docker, workspace, monkeypatch):
    """Model → Action (bash) → sandbox → Observation → answer. The engine
    and the tool layer are unchanged; this is the proof they did not need
    to be."""
    provider = _Scripted(
        Message(role=Role.ASSISTANT, tool_calls=(_bash_call("uname -n; exit 3"),)),
        Message(role=Role.ASSISTANT, content="ran it"),
    )
    monkeypatch.setattr(assembly, "provider_from_env", lambda p, m: provider)
    config = _config(workspace, docker, sandbox_auto_approve=True)

    async def main():
        app = await open_app(config)
        app = dataclasses.replace(
            app, engine=AgentEngine(provider, app.registry, config.engine_config())
        )
        try:
            return await run_turn(app, (), "run something")
        finally:
            await app.aclose()

    outcome = _run(main())

    assert outcome.reply == "ran it"
    observation = next(m for m in outcome.history if m.role is Role.TOOL)
    assert observation.content.startswith("[exit status 3]")
    system = provider.seen[0][0].content
    assert "## Execution sandbox" in system
    assert "no network access" in system
    assert "omicsclaw/test:1" in system


def test_the_prompt_section_sits_between_tool_guidance_and_the_environment(
    docker, workspace
):
    """Stable text belongs before the one section that changes daily."""
    app = build_app(_config(workspace, docker))
    rendered = app.prompt.render().system_prompt

    assert (
        rendered.index("## Tool guidance")
        < rendered.index("## Execution sandbox")
        < rendered.index("## Environment")
    )


def test_a_failure_after_the_sandbox_started_removes_it(docker, workspace):
    """``open_app`` owns the container until it hands the app back."""
    twice = [BashTool(Workspace(workspace)), BashTool(Workspace(workspace))]

    with pytest.raises(Exception, match="already registered"):
        _run(open_app(_config(workspace, docker), tools=twice))

    assert any(call[0] == "run" for call in docker.calls())
    assert docker.containers() == []


def test_unstarted_sandbox_is_off_for_an_off_config(workspace):
    assert unstarted_sandbox(_config(workspace)) == SandboxBinding()
