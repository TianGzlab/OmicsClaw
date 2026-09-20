"""Two test doubles for the container CLI.

:class:`ScriptedRunner` answers in-process, for lifecycle logic that
needs a failure on demand. :class:`FakeDocker` is an executable on disk
whose ``exec`` really runs the command, for everything that depends on a
real process: the wrapper script, the pid file, the output file, and the
in-container kill.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from omicsclaw.sandbox import Completed, SandboxConfig

_FAKE = Path(__file__).resolve().parent / "fake_docker.py"

Handler = Callable[[list[str]], "Completed | BaseException"]


def ok(stdout: str = "") -> Completed:
    return Completed(returncode=0, stdout=stdout, stderr="")


def fail(stderr: str, code: int = 1) -> Completed:
    return Completed(returncode=code, stdout="", stderr=stderr)


@dataclass
class ScriptedRunner:
    """Answers each call with ``handler(args)``; raises it if it is an exception."""

    handler: Handler
    calls: list[list[str]] = field(default_factory=list)
    timeouts: list[float | None] = field(default_factory=list)

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
    ) -> Completed:
        self.calls.append(list(args))
        self.timeouts.append(timeout)
        answer = self.handler(list(args))
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def commands(self) -> list[str]:
        return [call[0] for call in self.calls]


def healthy_docker(args: list[str]) -> Completed:
    """A daemon on which everything succeeds."""
    command = args[0]
    if command == "info":
        return ok("27.0.0")
    if command == "run":
        return ok("c" * 64 + "\n")
    if command == "inspect":
        return ok("running 0\n")
    if command == "ps":
        return ok("")
    return ok()


@dataclass
class FakeDocker:
    """``tests/sandbox/fake_docker.py`` behind an executable named ``docker``."""

    root: Path

    @classmethod
    def install(cls, root: Path) -> "FakeDocker":
        root.mkdir(parents=True, exist_ok=True)
        (root / "state").mkdir(exist_ok=True)
        binary = root / "docker"
        binary.write_text(
            "#!/bin/sh\n"
            f"FAKE_DOCKER_STATE='{root / 'state'}' "
            f"exec '{sys.executable}' '{_FAKE}' \"$@\"\n",
            encoding="utf-8",
        )
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        return cls(root)

    @property
    def binary(self) -> str:
        return str(self.root / "docker")

    @property
    def state(self) -> Path:
        return self.root / "state"

    def config(self, **overrides: object) -> SandboxConfig:
        values: dict[str, object] = {
            "image": "omicsclaw/test:1",
            "runtime": self.binary,
            "start_timeout_s": 20.0,
        }
        values.update(overrides)
        return SandboxConfig(**values)  # type: ignore[arg-type]

    def calls(self) -> list[list[str]]:
        path = self.state / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def containers(self) -> list[dict]:
        folder = self.state / "containers"
        if not folder.exists():
            return []
        return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]

    def add_container(self, container_id: str, labels: dict[str, str]) -> None:
        folder = self.state / "containers"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{container_id}.json").write_text(
            json.dumps(
                {
                    "id": container_id,
                    "name": "",
                    "labels": labels,
                    "args": [],
                    "status": "running",
                }
            )
        )

    def set_flag(self, name: str) -> None:
        (self.state / name).touch()

    def clear_flag(self, name: str) -> None:
        (self.state / name).unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    """Is *pid* a running (not zombie) process on this machine?"""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().split(") ", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, IndexError):
        return False
    except OSError:
        return os.path.exists(f"/proc/{pid}")
