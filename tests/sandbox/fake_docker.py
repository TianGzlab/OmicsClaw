"""A stand-in for the ``docker`` CLI, just wide enough for ``omicsclaw.sandbox``.

State lives in the directory named by ``FAKE_DOCKER_STATE``: ``calls.jsonl``
records every invocation, ``containers/<id>.json`` one record per
container, and a file named after a flag switches a failure on
(``daemon_down``, ``fail_run``, ``exit_after_run``).

``exec`` really runs ``bash -c …`` on this machine, as a **child** of this
process rather than in its place. Killing this process therefore leaves the
command running, exactly as killing a real ``docker exec`` client leaves the
container's process running — which is what the sandbox's in-container kill
exists to handle.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

STATE = Path(os.environ["FAKE_DOCKER_STATE"])
CONTAINERS = STATE / "containers"


def main(argv: list[str]) -> int:
    CONTAINERS.mkdir(parents=True, exist_ok=True)
    with open(STATE / "calls.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(argv) + "\n")
    command, rest = argv[0], argv[1:]
    handler = {
        "info": _info,
        "run": _run,
        "inspect": _inspect,
        "exec": _exec,
        "ps": _ps,
        "stop": _stop,
        "rm": _rm,
    }.get(command)
    if handler is None:
        print(f"fake docker: unknown command {command}", file=sys.stderr)
        return 2
    return handler(rest)


def _flag(name: str) -> bool:
    return (STATE / name).exists()


def _info(_: list[str]) -> int:
    if _flag("daemon_down"):
        print("Cannot connect to the Docker daemon", file=sys.stderr)
        return 1
    print("27.0.0-fake")
    return 0


def _run(args: list[str]) -> int:
    if _flag("fail_run"):
        print(
            "docker: Error response from daemon: No such image: missing:1.",
            file=sys.stderr,
        )
        return 125
    labels = {}
    name = ""
    for index, arg in enumerate(args):
        if arg == "--label":
            key, _, value = args[index + 1].partition("=")
            labels[key] = value
        if arg == "--name":
            name = args[index + 1]
    container_id = secrets.token_hex(32)
    status = "exited" if _flag("exit_after_run") else "running"
    _save(
        container_id,
        {"id": container_id, "name": name, "labels": labels, "args": args,
         "status": status},
    )
    print(container_id)
    return 0


def _find(ref: str) -> dict | None:
    for path in CONTAINERS.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["id"].startswith(ref) or record.get("name") == ref:
            return record
    return None


def _save(container_id: str, record: dict) -> None:
    (CONTAINERS / f"{container_id}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


def _inspect(args: list[str]) -> int:
    fmt = args[args.index("--format") + 1]
    record = _find(args[-1])
    if record is None:
        print(f"Error: No such object: {args[-1]}", file=sys.stderr)
        return 1
    if "State.Status" in fmt:
        print(f"{record['status']} {0 if record['status'] == 'running' else 1}")
    elif "Config.Labels" in fmt:
        print(record["labels"].get("omicsclaw.sandbox.owner", ""))
    return 0


def _exec(args: list[str]) -> int:
    workdir = None
    if args[0] == "--workdir":
        workdir, args = args[1], args[2:]
    record = _find(args[0])
    if record is None or record["status"] != "running":
        print(
            f"Error response from daemon: container {args[0]} is not running",
            file=sys.stderr,
        )
        return 1
    child = subprocess.Popen(args[1:], cwd=workdir, stdin=subprocess.DEVNULL)
    code = child.wait()
    return 128 - code if code < 0 else code


def _ps(args: list[str]) -> int:
    wanted = ""
    if "--filter" in args:
        wanted = args[args.index("--filter") + 1].removeprefix("label=")
    key, _, value = wanted.partition("=")
    for path in sorted(CONTAINERS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not key or record["labels"].get(key) == value:
            print(record["id"][:12])
    return 0


def _stop(args: list[str]) -> int:
    record = _find(args[-1])
    if record is None:
        print(f"Error: No such container: {args[-1]}", file=sys.stderr)
        return 1
    record["status"] = "exited"
    _save(record["id"], record)
    print(args[-1])
    return 0


def _rm(args: list[str]) -> int:
    record = _find(args[-1])
    if record is None:
        print(f"Error: No such container: {args[-1]}", file=sys.stderr)
        return 1
    (CONTAINERS / f"{record['id']}.json").unlink()
    print(args[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
