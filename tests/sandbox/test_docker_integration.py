"""Against a real Docker daemon. Skipped where there is none.

Set ``OMICSCLAW_SANDBOX_TEST_IMAGE`` to an image that is already pulled
and has ``bash`` and ``sleep`` (default ``ubuntu:22.04``). These are the
properties the fake CLI cannot vouch for: that the hardening flags are
accepted together, that ``--network none`` really has no route out, that
the host user can write the workspace (and its exchange directory) from
inside, and that a cancelled command dies inside a real container.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from omicsclaw.sandbox import SandboxConfig, SandboxManager

_IMAGE = os.environ.get("OMICSCLAW_SANDBOX_TEST_IMAGE", "ubuntu:22.04")


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "image", "inspect", _IMAGE], capture_output=True, timeout=30
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_ready(), reason=f"no docker daemon or image {_IMAGE} not pulled"
)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 180))


def test_a_real_container_runs_isolated_and_is_removed(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    manager = SandboxManager(SandboxConfig(image=_IMAGE))

    async def main():
        environment = await manager.create_with_retry(workspace)
        try:
            written = await environment.run_bash(
                "echo inside > made.txt; id -u",
                str(workspace.resolve()),
                60,
            )
            network = await environment.run_bash(
                "cat /sys/class/net/*/operstate 2>/dev/null | wc -l; "
                "getent hosts example.com || echo no-dns",
                str(workspace.resolve()),
                60,
            )
            return environment, written, network
        finally:
            await manager.aclose()

    environment, written, network = _run(main())

    assert written.exit_code == 0, written.output
    assert (workspace / "made.txt").read_text() == "inside\n"
    assert written.output.splitlines()[0] == str(os.getuid())
    assert "no-dns" in network.output
    listed = subprocess.run(
        ["docker", "ps", "-a", "-q", "--filter", f"id={environment.container_id}"],
        capture_output=True,
        text=True,
    )
    assert listed.stdout.strip() == ""


def test_a_cancelled_command_dies_inside_a_real_container(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    manager = SandboxManager(SandboxConfig(image=_IMAGE))

    async def main():
        environment = await manager.create_with_retry(workspace)
        try:
            task = asyncio.ensure_future(
                environment.run_bash("sleep 300", str(workspace.resolve()), 600)
            )
            await asyncio.sleep(2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(1)
            return await environment.run_bash(
                "for f in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < \"$f\"; echo; "
                "done 2>/dev/null | grep -c '^sleep 300' || true",
                str(workspace.resolve()),
                60,
            )
        finally:
            await manager.aclose()

    remaining = _run(main())

    assert remaining.output.strip() == "0"
