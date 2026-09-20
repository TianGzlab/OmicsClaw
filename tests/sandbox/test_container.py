"""``run_arguments`` and the container state machine."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from omicsclaw.sandbox import (
    EXCHANGE_DIR,
    LABEL,
    OWNER_LABEL,
    Container,
    ContainerState,
    SandboxConfig,
    SandboxError,
    run_arguments,
)
from omicsclaw.sandbox.runner import CommandTimedOut

from ._support import ScriptedRunner, fail, healthy_docker, ok


def _args(tmp_path: Path, **overrides) -> list[str]:
    config = SandboxConfig(image="omics:1", **overrides)
    return run_arguments(
        config,
        sandbox_id="abc",
        workspace=tmp_path / "ws",
        owner="host:42",
    )


def _pairs(args: list[str]) -> set[tuple[str, str]]:
    return {(args[i], args[i + 1]) for i in range(len(args) - 1)}


# ---- the command line ----------------------------------------------------


def test_the_container_is_hardened(tmp_path):
    args = _args(tmp_path)
    pairs = _pairs(args)

    assert ("--cap-drop", "ALL") in pairs
    assert ("--security-opt", "no-new-privileges:true") in pairs
    assert ("--pids-limit", "4096") in pairs
    assert "--init" in args
    assert "--cap-add" not in args
    assert "--privileged" not in args


def test_the_network_is_off_by_default(tmp_path):
    """The primary control for a data-exfiltration threat model. harness9's
    ``--add-host`` DNS blackhole calls itself a behavioural guard rather
    than a boundary; ``--network none`` is a boundary."""
    assert ("--network", "none") in _pairs(_args(tmp_path))
    assert "--add-host" not in _args(tmp_path)


def test_nothing_is_pulled(tmp_path):
    """A GB-sized omics image cannot be pulled inside a start timeout."""
    assert "--pull=never" in _args(tmp_path)


def test_no_host_environment_crosses_into_the_container(tmp_path):
    """Local ``bash`` inherits ``LLM_API_KEY`` and every other secret in
    this process's environment. The container gets exactly one variable."""
    args = _args(tmp_path)
    passed = [args[i + 1] for i, arg in enumerate(args) if arg in ("--env", "-e")]

    assert passed == ["HOME=/tmp"]
    assert "--env-file" not in args


def test_the_workspace_is_the_only_read_write_mount_and_keeps_its_path(tmp_path):
    """Same path inside and out is what lets ``bash`` receive the resolved
    host path as its working directory unchanged. The pid/log exchange
    directory lives inside the workspace, so it needs no mount of its own —
    in particular none nested under the ``/tmp`` tmpfs, whose ordering
    relative to a bind mount would be the runtime's business."""
    ws = tmp_path / "ws"
    args = _args(tmp_path)
    volumes = [args[i + 1] for i, arg in enumerate(args) if arg == "--volume"]

    assert volumes == [f"{ws}:{ws}"]
    assert ("--workdir", str(ws)) in _pairs(args)


def test_extra_mounts_are_read_only(tmp_path):
    pairs = _pairs(_args(tmp_path, read_only_mounts=(Path("/ref/hg38"),)))

    assert ("--volume", "/ref/hg38:/ref/hg38:ro") in pairs


def test_limits_appear_only_when_configured(tmp_path):
    bare = _args(tmp_path)
    capped = _pairs(_args(tmp_path, memory="32g", cpus="8", gpus="all"))

    assert not {"--memory", "--cpus", "--gpus"} & set(bare)
    assert {("--memory", "32g"), ("--cpus", "8"), ("--gpus", "all")} <= capped


def test_labels_name_the_owner_and_the_image_runs_sleep(tmp_path):
    args = _args(tmp_path)
    pairs = _pairs(args)

    assert ("--label", f"{LABEL}=1") in pairs
    assert ("--label", f"{OWNER_LABEL}=host:42") in pairs
    assert ("--name", "omicsclaw-sandbox-abc") in pairs
    assert args[-3:] == ["omics:1", "sleep", "infinity"]


def test_the_user_flag_follows_the_config(tmp_path):
    assert ("--user", "1000:1000") in _pairs(_args(tmp_path, user="1000:1000"))
    assert "--user" not in _args(tmp_path, user=None)


# ---- the lifecycle -------------------------------------------------------


def _container(tmp_path: Path, runner: ScriptedRunner, **overrides) -> Container:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    values: dict = {"image": "omics:1", "start_timeout_s": 2.0, **overrides}
    config = SandboxConfig(**values)
    return Container("abc", workspace, config, runner, owner="host:1")


def test_a_healthy_start_reaches_running_and_stop_removes_everything(tmp_path):
    runner = ScriptedRunner(healthy_docker)
    container = _container(tmp_path, runner)

    asyncio.run(container.start())
    io_dir = container.io_dir

    assert container.state is ContainerState.RUNNING
    assert container.docker_id == "c" * 64
    assert io_dir is not None and io_dir.is_dir()
    assert io_dir.parent == tmp_path / "ws" / EXCHANGE_DIR
    assert io_dir.stat().st_mode & 0o777 == 0o700

    asyncio.run(container.stop())

    assert container.state is ContainerState.TERMINATED
    assert runner.commands()[-2:] == ["stop", "rm"]
    assert not io_dir.exists()
    assert not (tmp_path / "ws" / EXCHANGE_DIR).exists()


def test_a_missing_image_fails_with_advice_and_leaves_nothing(tmp_path):
    def docker(args):
        if args[0] == "run":
            return fail("docker: Error response from daemon: No such image: omics:1.")
        return ok()

    runner = ScriptedRunner(docker)
    container = _container(tmp_path, runner)

    with pytest.raises(SandboxError, match="pull omics:1"):
        asyncio.run(container.start())

    assert container.state is ContainerState.FAILED
    assert container.io_dir is not None and not container.io_dir.exists()
    assert runner.calls[-1] == ["rm", "--force", "omicsclaw-sandbox-abc"]


def test_a_container_that_exits_at_once_fails_without_waiting(tmp_path):
    def docker(args):
        if args[0] == "inspect":
            return ok("exited 127\n")
        return healthy_docker(args)

    runner = ScriptedRunner(docker)
    container = _container(tmp_path, runner, start_timeout_s=30.0)

    with pytest.raises(SandboxError, match="exited with status 127"):
        asyncio.run(container.start())

    assert runner.commands().count("inspect") == 1
    assert runner.calls[-1] == ["rm", "--force", "c" * 64]


def test_a_container_that_never_runs_times_out_and_is_removed(tmp_path):
    """harness9's own fix: a container that exists after ``run`` but never
    became ready must be removed now, not leak until the next reap."""

    def docker(args):
        if args[0] == "inspect":
            return ok("created 0\n")
        return healthy_docker(args)

    runner = ScriptedRunner(docker)
    container = _container(tmp_path, runner, start_timeout_s=0.5)

    with pytest.raises(SandboxError, match="did not start within"):
        asyncio.run(container.start())

    assert container.state is ContainerState.FAILED
    assert runner.calls[-1] == ["rm", "--force", "c" * 64]


def test_a_run_that_hangs_is_removed_by_name(tmp_path):
    """Its id never arrived, but the container may exist anyway."""

    def docker(args):
        if args[0] == "run":
            return CommandTimedOut("docker run did not finish")
        return ok()

    runner = ScriptedRunner(docker)
    container = _container(tmp_path, runner)

    with pytest.raises(SandboxError, match="did not start within"):
        asyncio.run(container.start())

    assert runner.calls[-1] == ["rm", "--force", "omicsclaw-sandbox-abc"]


def test_a_missing_mount_source_is_refused_before_docker_is_asked(tmp_path):
    """``docker -v`` would create it, empty and root-owned, on the host."""
    runner = ScriptedRunner(healthy_docker)
    container = _container(
        tmp_path, runner, read_only_mounts=(tmp_path / "no-such-reference",)
    )

    with pytest.raises(SandboxError, match="does not exist"):
        asyncio.run(container.start())

    assert runner.calls == []
    assert container.state is ContainerState.FAILED


def test_the_workspace_cannot_also_be_a_read_only_mount(tmp_path):
    runner = ScriptedRunner(healthy_docker)
    container = _container(tmp_path, runner, read_only_mounts=(tmp_path / "ws",))

    with pytest.raises(SandboxError, match="is the workspace"):
        asyncio.run(container.start())


def test_cancellation_during_start_cleans_up_and_propagates(tmp_path):
    def docker(args):
        if args[0] == "inspect":
            return ok("created 0\n")
        return healthy_docker(args)

    runner = ScriptedRunner(docker)
    container = _container(tmp_path, runner, start_timeout_s=30.0)

    async def main():
        task = asyncio.ensure_future(container.start())
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())

    assert container.state is ContainerState.FAILED
    assert runner.calls[-1] == ["rm", "--force", "c" * 64]
    assert container.io_dir is not None and not container.io_dir.exists()


def test_stop_removes_even_when_stop_itself_fails_and_is_idempotent(tmp_path):
    def docker(args):
        if args[0] == "stop":
            return fail("daemon hiccup")
        return healthy_docker(args)

    runner = ScriptedRunner(docker)
    container = _container(tmp_path, runner)
    asyncio.run(container.start())

    asyncio.run(container.stop())
    asyncio.run(container.stop())

    assert runner.commands().count("rm") == 1
    assert container.state is ContainerState.TERMINATED


def test_a_failed_removal_is_recorded_not_raised(tmp_path):
    def docker(args):
        if args[0] == "rm":
            return fail("device busy")
        return healthy_docker(args)

    container = _container(tmp_path, ScriptedRunner(docker))
    asyncio.run(container.start())

    asyncio.run(container.stop())

    assert container.state is ContainerState.TERMINATED
    assert "could not be removed" in container.error


def test_a_container_starts_once(tmp_path):
    container = _container(tmp_path, ScriptedRunner(healthy_docker))
    asyncio.run(container.start())

    with pytest.raises(SandboxError, match="already started"):
        asyncio.run(container.start())


def test_the_workspace_is_resolved(tmp_path):
    """``bash`` hands the container the *resolved* workspace root as its
    working directory, so the mount must be at that path too."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    config = SandboxConfig(image="x")

    container = Container("abc", link, config, ScriptedRunner(healthy_docker))

    assert container.workspace == real.resolve()


def test_the_stop_grace_is_rounded_up_not_down(tmp_path):
    runner = ScriptedRunner(healthy_docker)
    container = _container(tmp_path, runner, stop_grace_s=2.5)
    asyncio.run(container.start())

    asyncio.run(container.stop())

    assert ["stop", "--time", "3", "c" * 64] in runner.calls


def test_an_unwritable_workspace_fails_before_docker_is_asked(tmp_path):
    runner = ScriptedRunner(healthy_docker)
    container = _container(tmp_path, runner)
    (tmp_path / "ws" / ".omicsclaw").write_text("a file where a directory goes")

    with pytest.raises(SandboxError, match="cannot create"):
        asyncio.run(container.start())

    assert runner.calls == []
    assert container.state is ContainerState.FAILED
