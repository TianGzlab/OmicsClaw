"""``SandboxManager``: create, retry, bootstrap, destroy, reap, notify."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
from pathlib import Path

import pytest

from omicsclaw.sandbox import (
    LABEL,
    OWNER_LABEL,
    ContainerState,
    SandboxConfig,
    SandboxError,
    SandboxManager,
    owner_is_dead,
)
from omicsclaw.sandbox import environment as environment_module

from ._support import FakeDocker, ScriptedRunner, fail, healthy_docker, ok


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 60))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path


def _manager(runner, **overrides) -> SandboxManager:
    values: dict = {"image": "omics:1", "start_timeout_s": 2.0, **overrides}
    listener = values.pop("on_change", None)
    return SandboxManager(
        SandboxConfig(**values),
        runner=runner,
        on_change=listener,
        start_daemon=None,
    )


def _dead_pid() -> int:
    process = subprocess.Popen(["true"])
    process.wait()
    return process.pid


# ---- create / list / destroy ---------------------------------------------


def test_the_listener_sees_pending_then_running_then_nothing(workspace):
    seen: list[tuple] = []
    manager = _manager(ScriptedRunner(healthy_docker), on_change=seen.append)

    async def main():
        environment = await manager.create(workspace, label="main")
        listed = manager.list_all()
        await manager.destroy(environment.id)
        return environment, listed

    environment, listed = _run(main())

    states = [tuple(info.state for info in snapshot) for snapshot in seen]
    assert states[0] == (ContainerState.PENDING,)
    assert (ContainerState.RUNNING,) in states
    assert states[-1] == ()
    assert listed[0].label == "main"
    assert listed[0].image == "omics:1"
    assert listed[0].docker_id == "c" * 12
    assert environment.container_id == "c" * 64


def test_a_listener_that_raises_breaks_nothing(workspace):
    def listener(snapshot):
        raise RuntimeError("status bar crashed")

    manager = _manager(ScriptedRunner(healthy_docker), on_change=listener)

    async def main():
        await manager.create(workspace)
        await manager.aclose()

    _run(main())


def test_a_failed_create_is_forgotten_and_raises(workspace):
    def docker(args):
        return fail("no space left on device") if args[0] == "run" else ok()

    seen: list[tuple] = []
    manager = _manager(ScriptedRunner(docker), on_change=seen.append)

    with pytest.raises(SandboxError, match="no space left"):
        _run(manager.create(workspace))

    assert manager.list_all() == ()
    assert seen[-1] == ()


def test_each_agent_gets_its_own_sandbox_under_its_own_label(workspace):
    """The seam a sub-agent layer will use: same config, own container."""
    manager = _manager(ScriptedRunner(healthy_docker))

    async def main():
        first = await manager.create(workspace, label="main")
        second = await manager.create(workspace, label="sub-1")
        return first, second, manager.list_all()

    first, second, listed = _run(main())

    assert first.id != second.id
    assert {info.label for info in listed} == {"main", "sub-1"}
    _run(manager.aclose())
    assert manager.list_all() == ()


def test_destroying_an_unknown_sandbox_is_a_no_op():
    _run(_manager(ScriptedRunner(healthy_docker)).destroy("nope"))


# ---- retry ---------------------------------------------------------------


def test_the_daemon_is_checked_before_the_first_create(workspace):
    runner = ScriptedRunner(healthy_docker)

    _run(_manager(runner).create_with_retry(workspace))

    assert runner.commands()[:2] == ["info", "run"]


def test_one_failed_create_is_retried(workspace):
    answers = iter([fail("cold start"), ok("d" * 64)])

    def docker(args):
        return next(answers) if args[0] == "run" else healthy_docker(args)

    environment = _run(_manager(ScriptedRunner(docker)).create_with_retry(workspace))

    assert environment.container_id == "d" * 64


def test_two_failures_name_both(workspace):
    answers = iter([fail("first problem"), fail("second problem")])

    def docker(args):
        return next(answers) if args[0] == "run" else healthy_docker(args)

    with pytest.raises(SandboxError) as caught:
        _run(_manager(ScriptedRunner(docker)).create_with_retry(workspace))

    assert "second problem" in str(caught.value)
    assert "first attempt" in str(caught.value) and "first problem" in str(caught.value)


def test_no_daemon_means_no_create(workspace):
    runner = ScriptedRunner(lambda args: fail("Cannot connect to the Docker daemon"))

    with pytest.raises(SandboxError, match="daemon"):
        _run(_manager(runner).create_with_retry(workspace))

    assert "run" not in runner.commands()


# ---- bootstrap (real processes, through the fake CLI) --------------------


def test_the_bootstrap_runs_once_in_the_workspace(tmp_path, workspace):
    docker = FakeDocker.install(tmp_path / "fake")
    manager = SandboxManager(
        docker.config(bootstrap="pwd > booted.txt"), start_daemon=None
    )

    async def main():
        environment = await manager.create(workspace)
        try:
            return manager.info(environment.id)
        finally:
            await manager.aclose()

    info = _run(main())

    assert info is not None and info.bootstrap is not None and info.bootstrap.ok
    assert (workspace / "booted.txt").read_text().strip() == str(workspace.resolve())


def test_a_failing_bootstrap_is_recorded_and_does_not_fail_creation(
    tmp_path, workspace
):
    """harness9 means to do the same, but its ``RunBash`` never returns an
    error, so its failure branch is unreachable and a broken bootstrap is
    silent. The exit status crosses the seam here."""
    docker = FakeDocker.install(tmp_path / "fake")
    manager = SandboxManager(docker.config(bootstrap="exit 4"), start_daemon=None)

    async def main():
        environment = await manager.create(workspace)
        try:
            return manager.info(environment.id)
        finally:
            await manager.aclose()

    info = _run(main())

    assert info.bootstrap.exit_code == 4
    assert not info.bootstrap.ok


def test_a_bootstrap_that_overruns_is_stopped_on_its_own_budget(
    tmp_path, workspace, monkeypatch
):
    monkeypatch.setattr(environment_module, "OWN_DEADLINE_GRACE_S", 0.0)
    docker = FakeDocker.install(tmp_path / "fake")
    manager = SandboxManager(
        docker.config(bootstrap="sleep 30", bootstrap_timeout_s=0.5),
        start_daemon=None,
    )

    async def main():
        environment = await manager.create(workspace)
        try:
            return manager.info(environment.id)
        finally:
            await manager.aclose()

    info = _run(main())

    assert info.bootstrap.timed_out


# ---- orphans -------------------------------------------------------------


def test_only_containers_of_dead_local_processes_are_reaped(tmp_path, workspace):
    """harness9 reaps every labelled container at start-up, before it owns
    any — which removes the live containers of a second harness9 running
    beside it. Here a container is removed only when its owner label names
    this host and a PID that no longer exists."""
    docker = FakeDocker.install(tmp_path / "fake")
    host = socket.gethostname()
    docker.add_container("a" * 64, {LABEL: "1", OWNER_LABEL: f"{host}:{_dead_pid()}"})
    docker.add_container("b" * 64, {LABEL: "1", OWNER_LABEL: f"{host}:{os.getppid()}"})
    docker.add_container("e" * 64, {LABEL: "1", OWNER_LABEL: "elsewhere:1"})
    docker.add_container("f" * 64, {LABEL: "1", OWNER_LABEL: f"{host}:{os.getpid()}"})
    docker.add_container("9" * 64, {LABEL: "1"})
    docker.add_container("8" * 64, {"unrelated": "1"})
    manager = SandboxManager(docker.config(), start_daemon=None)

    async def main():
        environment = await manager.create(workspace)
        try:
            return await manager.reap_orphans(), environment
        finally:
            await manager.aclose()

    report, environment = _run(main())

    assert report.removed == ("a" * 12,)
    assert report.failed == ()
    assert report.kept == 5  # b, e, f, 9 and the manager's own
    left = {record["id"][:12] for record in docker.containers()}
    assert left == {"b" * 12, "e" * 12, "f" * 12, "9" * 12, "8" * 12}


def test_a_listing_that_fails_is_an_error():
    runner = ScriptedRunner(lambda args: fail("permission denied"))

    with pytest.raises(SandboxError, match="permission denied"):
        _run(_manager(runner).reap_orphans())


@pytest.mark.parametrize(
    ("owner", "dead"),
    [
        ("", False),
        ("no-colon", False),
        (f"{socket.gethostname()}:abc", False),
        (f"other-host:{_dead_pid()}", False),
        (f"{socket.gethostname()}:{os.getpid()}", False),
        (f"{socket.gethostname()}:{os.getppid()}", False),
        (f"{socket.gethostname()}:1", False),
        (f"{socket.gethostname()}:{_dead_pid()}", True),
    ],
)
def test_an_owner_is_dead_only_when_that_is_proved(owner: str, dead: bool):
    assert owner_is_dead(owner) is dead
