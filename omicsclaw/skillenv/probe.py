"""Fixed Python programs that report on the interpreter ``bash`` uses.

The programs run under whichever ``python`` the execution location resolves
— this machine's ``bash`` or the sandbox's — and print one JSON line. They
remove ``''`` and ``'.'`` from ``sys.path`` before importing anything, so no
file in the working directory is executed or mistaken for a package, and
put the skill directory first when it exists there, as running a script
from that directory would. The first reports which modules import; the
second, the inventory, also reports the interpreter's identity, the
distributions in its own site-packages and the top-level names it can
import, which is what an overlay built on it needs to know.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from omicsclaw.tools.builtin.bash import (
    BashEnvironment,
    spawn_group_leader,
    without_control_credentials,
)

__all__ = [
    "INVENTORY_TIMEOUT_S",
    "PROBE_TIMEOUT_S",
    "BaseInventory",
    "LocalProbeRunner",
    "ProbeError",
    "ProbeResult",
    "ProbeRunner",
    "SandboxProbeRunner",
    "inventory_command",
    "parse_inventory",
    "parse_probe",
    "probe_command",
    "run_inventory",
    "run_probe",
]

PROBE_TIMEOUT_S = 10.0
"""Seconds one probe may take before it is killed."""

_CODE = """\
import sys
sys.path[:] = [p for p in sys.path if p not in ("", ".")]
import json, os, site, importlib.util
args = json.loads(sys.argv[1])
skill_dir = args.get("skill_dir") or ""
if skill_dir and os.path.isdir(skill_dir):
    sys.path.insert(0, os.path.abspath(skill_dir))
try:
    user_site = site.getusersitepackages()
except Exception:
    user_site = ""
user_prefix = os.path.join(os.path.abspath(user_site), "") if user_site else ""
missing, from_user = [], []
for name in args.get("imports", []):
    try:
        spec = importlib.util.find_spec(name)
    except Exception:
        continue
    if spec is None:
        missing.append(name)
        continue
    origin = spec.origin or ""
    if not origin or origin in ("namespace", "built-in", "frozen"):
        locations = list(spec.submodule_search_locations or [])
        origin = locations[0] if locations else ""
    if user_prefix and origin and os.path.abspath(origin).startswith(user_prefix):
        from_user.append(name)
versions = {}
if args.get("dists"):
    from importlib import metadata
    for dist in args["dists"]:
        try:
            versions[dist] = metadata.version(dist)
        except Exception:
            versions[dist] = None
print(json.dumps({
    "executable": sys.executable,
    "version": "%d.%d.%d" % sys.version_info[:3],
    "prefix": sys.prefix,
    "base_prefix": getattr(sys, "base_prefix", sys.prefix),
    "user_site_enabled": bool(site.ENABLE_USER_SITE),
    "missing": missing,
    "from_user_site": from_user,
    "versions": versions,
}))
"""

_FIELDS = ("executable", "version", "prefix", "base_prefix", "missing", "from_user_site", "versions")

INVENTORY_TIMEOUT_S = 30.0
"""Seconds the inventory may take before it is killed."""

_INVENTORY_CODE = """\
import sys
sys.path[:] = [p for p in sys.path if p not in ("", ".")]
import json, os, site, platform, importlib.util
args = json.loads(sys.argv[1])
skill_dir = args.get("skill_dir") or ""
if skill_dir and os.path.isdir(skill_dir):
    sys.path.insert(0, os.path.abspath(skill_dir))
missing = []
for name in args.get("imports", []):
    try:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    except Exception:
        pass
from importlib import metadata
records = []
for dist in metadata.distributions(path=site.getsitepackages()):
    try:
        name = dist.metadata["Name"]
        version = dist.metadata["Version"]
    except Exception:
        name = version = None
    where = getattr(dist, "_path", None)
    records.append([name or None, version or None, os.path.basename(str(where)) if where else ""])
top = {}
for entry in sys.path:
    if not entry or not os.path.isdir(entry):
        continue
    try:
        items = os.listdir(entry)
    except OSError:
        continue
    for item in items:
        if item.startswith(".") or item == "__pycache__":
            continue
        if item.endswith((".dist-info", ".egg-info", ".data", ".pth", ".egg-link")):
            continue
        full = os.path.join(entry, item)
        if os.path.isdir(full):
            name = item
            try:
                inner = os.listdir(full)
            except OSError:
                inner = []
            kind = "package" if any(n.startswith("__init__.") for n in inner) else "namespace"
        elif item.endswith((".py", ".pyc", ".so", ".pyd")):
            name = item.split(".", 1)[0]
            kind = "module"
        else:
            continue
        if not name.isidentifier():
            continue
        if top.get(name) in (None, "namespace"):
            top[name] = kind
for name in sys.builtin_module_names:
    top.setdefault(name, "module")
pip = None
try:
    if importlib.util.find_spec("pip") is not None:
        pip = metadata.version("pip")
except Exception:
    pip = None
real = os.path.realpath(sys.executable)
print(json.dumps({
    "executable": sys.executable,
    "real_executable": real,
    "version": "%d.%d.%d" % sys.version_info[:3],
    "prefix": sys.prefix,
    "base_prefix": getattr(sys, "base_prefix", sys.prefix),
    "mtime_ns": os.stat(real).st_mtime_ns,
    "platform": sys.platform,
    "machine": platform.machine(),
    "pip_version": pip,
    "missing": missing,
    "records": records,
    "top_level": top,
}))
"""

_INVENTORY_FIELDS = (
    "executable", "real_executable", "version", "prefix", "base_prefix", "mtime_ns",
    "platform", "machine", "pip_version", "missing", "records", "top_level",
)


class ProbeError(RuntimeError):
    """The probe could not run or its output was not what it prints."""


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What the probed interpreter reported."""

    executable: str
    version: str
    prefix: str
    base_prefix: str
    missing: tuple[str, ...]
    """Import names ``find_spec`` did not find."""
    from_user_site: tuple[str, ...]
    """Import names found, but only under the user site directory."""
    versions: Mapping[str, str | None] = field(default_factory=dict)
    """Distribution name to installed version, ``None`` when not installed."""


@dataclass(frozen=True, slots=True)
class BaseInventory:
    """What the inventory reported about the interpreter ``bash`` runs."""

    executable: str
    real_executable: str
    """:attr:`executable` with every symbolic link resolved."""
    version: str
    prefix: str
    base_prefix: str
    mtime_ns: int
    """Modification time of :attr:`real_executable`."""
    platform: str
    machine: str
    pip_version: str | None
    """``None`` when the interpreter has no pip."""
    missing: tuple[str, ...]
    """Import names ``find_spec`` did not find."""
    records: tuple[tuple[str | None, str | None, str], ...]
    """``(Name, Version, metadata directory name)`` of every distribution in the
    interpreter's own site-packages; a field the metadata lacks is ``None``."""
    top_level: Mapping[str, str] = field(default_factory=dict)
    """Every top-level name importable from ``sys.path``, as ``"module"``,
    ``"package"`` (a directory with ``__init__``) or ``"namespace"``."""

    @property
    def is_venv(self) -> bool:
        """Whether the interpreter is itself a virtual environment."""
        return self.prefix != self.base_prefix


@runtime_checkable
class ProbeRunner(Protocol):
    """Runs one shell command where ``bash`` runs."""

    location: str
    """``"local"`` or ``"sandbox"``."""

    async def run(
        self,
        command: str,
        *,
        cwd: str,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> tuple[int, str]:
        """Run *command* in *cwd*; return its exit status and merged output."""
        ...


def _payload(imports: Sequence[str], dists: Sequence[str], skill_dir: str) -> str:
    return json.dumps({"imports": list(imports), "dists": list(dists), "skill_dir": skill_dir})


def probe_command(imports: Sequence[str], dists: Sequence[str], skill_dir: str) -> str:
    """The shell command that probes with the ``python`` found on ``PATH``.

    It changes into *skill_dir* when that directory exists and otherwise
    stays where it was started.
    """
    return (
        f"cd {shlex.quote(skill_dir)} 2>/dev/null || true; "
        f"python -B -c {shlex.quote(_CODE)} {shlex.quote(_payload(imports, dists, skill_dir))}"
    )


def inventory_command(imports: Sequence[str], skill_dir: str) -> str:
    """The shell command that takes the inventory of the ``python`` found on ``PATH``."""
    return (
        f"cd {shlex.quote(skill_dir)} 2>/dev/null || true; "
        f"python -B -c {shlex.quote(_INVENTORY_CODE)} {shlex.quote(_payload(imports, (), skill_dir))}"
    )


def parse_inventory(output: str) -> BaseInventory:
    """Parse the inventory's JSON line, the last non-empty line of *output*.

    :raises ProbeError: No line, not JSON, or a field missing or of the wrong type.
    """
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise ProbeError("the inventory printed nothing")
    try:
        data = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ProbeError(f"the inventory printed something other than its report: {lines[-1][:200]}") from exc
    if not isinstance(data, dict) or any(name not in data for name in _INVENTORY_FIELDS):
        raise ProbeError("the inventory's report is missing fields")
    try:
        return BaseInventory(
            executable=str(data["executable"]),
            real_executable=str(data["real_executable"]),
            version=str(data["version"]),
            prefix=str(data["prefix"]),
            base_prefix=str(data["base_prefix"]),
            mtime_ns=int(data["mtime_ns"]),
            platform=str(data["platform"]),
            machine=str(data["machine"]),
            pip_version=None if data["pip_version"] is None else str(data["pip_version"]),
            missing=tuple(str(name) for name in data["missing"]),
            records=tuple(
                (None if n is None else str(n), None if v is None else str(v), str(d))
                for n, v, d in data["records"]
            ),
            top_level={str(k): str(v) for k, v in dict(data["top_level"]).items()},
        )
    except (TypeError, ValueError) as exc:
        raise ProbeError(f"the inventory's report is malformed: {exc}") from exc


async def run_inventory(
    runner: ProbeRunner,
    imports: Sequence[str],
    skill_dir: str,
    *,
    cwd: str,
    timeout: float = INVENTORY_TIMEOUT_S,
    env: Mapping[str, str] | None = None,
) -> BaseInventory:
    """Take the inventory through *runner* in *cwd* and parse it.

    :raises ProbeError: The command failed, timed out or printed no report.
    """
    code, output = await runner.run(inventory_command(imports, skill_dir), cwd=cwd, timeout=timeout, env=env)
    if code != 0:
        tail = output.strip().splitlines()[-1:] or [""]
        raise ProbeError(f"the inventory exited with status {code}: {tail[0][:200]}")
    return parse_inventory(output)


def parse_probe(output: str) -> ProbeResult:
    """Parse the probe's JSON line, the last non-empty line of *output*.

    :raises ProbeError: No line, not JSON, or a field missing or of the wrong type.
    """
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise ProbeError("the probe printed nothing")
    try:
        data = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise ProbeError(f"the probe printed something other than its report: {lines[-1][:200]}") from exc
    if not isinstance(data, dict) or any(name not in data for name in _FIELDS):
        raise ProbeError("the probe's report is missing fields")
    try:
        return ProbeResult(
            executable=str(data["executable"]),
            version=str(data["version"]),
            prefix=str(data["prefix"]),
            base_prefix=str(data["base_prefix"]),
            missing=tuple(str(name) for name in data["missing"]),
            from_user_site=tuple(str(name) for name in data["from_user_site"]),
            versions={str(k): (None if v is None else str(v)) for k, v in dict(data["versions"]).items()},
        )
    except (TypeError, ValueError) as exc:
        raise ProbeError(f"the probe's report is malformed: {exc}") from exc


async def run_probe(
    runner: ProbeRunner,
    imports: Sequence[str],
    dists: Sequence[str],
    skill_dir: str,
    *,
    cwd: str,
    timeout: float = PROBE_TIMEOUT_S,
    env: Mapping[str, str] | None = None,
) -> ProbeResult:
    """Run the probe through *runner* in *cwd* and parse what it printed.

    :raises ProbeError: The command failed, timed out or printed no report.
    """
    code, output = await runner.run(probe_command(imports, dists, skill_dir), cwd=cwd, timeout=timeout, env=env)
    if code != 0:
        tail = output.strip().splitlines()[-1:] or [""]
        raise ProbeError(f"the probe exited with status {code}: {tail[0][:200]}")
    return parse_probe(output)


class LocalProbeRunner:
    """Runs commands through ``bash -c`` on this machine, with the environment ``bash`` gets.

    The shell leads its own process group; on timeout the whole group is
    killed and the status is ``124``.
    """

    location = "local"

    async def run(
        self,
        command: str,
        *,
        cwd: str,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> tuple[int, str]:
        environment = without_control_credentials()
        if env:
            environment.update(env)
        process = await spawn_group_leader(
            asyncio.create_subprocess_exec(
                "bash",
                "-c",
                command,
                cwd=cwd,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        )
        try:
            async with asyncio.timeout(timeout):
                output, _ = await process.communicate()
        except TimeoutError:
            _kill_group(process)
            await process.wait()
            return 124, f"timed out after {timeout:g} s"
        except BaseException:
            _kill_group(process)
            raise
        return process.returncode or 0, output.decode("utf-8", errors="replace")


def _kill_group(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class SandboxProbeRunner:
    """Runs commands where the sandboxed ``bash`` runs.

    *env* is applied as ``env NAME=value … bash -c <command>``, because a
    sandbox runs a command line and takes no environment of its own.
    """

    location = "sandbox"

    def __init__(self, environment: BashEnvironment) -> None:
        self._environment = environment

    async def run(
        self,
        command: str,
        *,
        cwd: str,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> tuple[int, str]:
        if env:
            assignments = " ".join(shlex.quote(f"{name}={value}") for name, value in env.items())
            command = f"env {assignments} bash -c {shlex.quote(command)}"
        outcome = await self._environment.run_bash(command, cwd, timeout)
        if getattr(outcome, "timed_out", False):
            return 124, outcome.output
        return outcome.exit_code, outcome.output
