"""Overlay environments: a virtual environment over the base interpreter holding only what the base lacks.

An overlay is created with ``--system-site-packages`` from the interpreter
``bash`` runs, so every base package stays visible and the overlay's own
site-packages comes first. Its directory is ``<root>/<key>/.venv``, where the
key is a digest of the base's identity, the distributions in the base's own
site-packages and the requested requirements: any change to the base gives a
new key. An overlay with a fingerprint file is finished and is never changed
or deleted here; a directory without one is a half-built overlay and is
removed under the key's lock, which lives in ``<root>/.locks`` and is never
deleted.

:class:`OverlayBuilder` builds one overlay: resolve with ``pip install
--dry-run --only-binary=:all: --report``, keep what the base already has
(:func:`fill_only`), install the rest pinned with ``--no-deps``, compare what
was installed with what was planned, check where every installed file landed
and which top-level names it adds, compare ``pip check`` before and after,
import the skill's modules, and only then write the metadata and the
fingerprint. Any failure, cancellation or time-out removes the half-built
directory.
"""

from __future__ import annotations

import asyncio
import csv
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import tempfile
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from omicsclaw.tools.builtin.bash import spawn_group_leader

from .probe import BaseInventory, ProbeError, ProbeResult, ProbeRunner, run_inventory
from .registry import normalise
from .sources import (
    RequirementError,
    artifact_source,
    artifact_transport,
    check_pin,
    clean_environment,
    config_list_environment,
    foreign_reason,
    location_settings,
    pip_environment,
    redact,
    wheel_name,
)

__all__ = [
    "FINGERPRINT",
    "META",
    "PACKAGE_SOURCES",
    "Artifact",
    "BaseDistributions",
    "CommandOutput",
    "CommandRunner",
    "FillPlan",
    "Foreign",
    "InstallLimits",
    "Kept",
    "LocalCommandRunner",
    "OverlayBuilder",
    "OverlayInfo",
    "OverlayRequest",
    "OverlayResult",
    "RecordCheck",
    "base_distributions",
    "check_records",
    "default_root",
    "fill_only",
    "find_overlays",
    "list_overlays",
    "new_violations",
    "overlay_key",
]

FINGERPRINT = ".omicsclaw.fingerprint"
"""File inside ``.venv`` whose presence marks a finished overlay."""

META = ".meta.json"
"""File beside ``.venv`` recording what the overlay holds and where it came from."""

PACKAGE_SOURCES = "pip configuration of this machine (not checked)"
"""What the metadata says about where packages come from."""

_KEY = re.compile(r"[0-9a-f]{16}")
_METADATA_DIR = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._]*?)-(?P<version>[^-]+?)(?:-py\d+(?:\.\d+)*)?\.(?:dist|egg)-info$"
)
_CLEAR = "No broken requirements found."
_NO_MATCH = re.compile(r"No matching distribution found for (\S+)")
_VERIFY_MARK = "OMICSCLAW_VERIFY="


def default_root(environment: Mapping[str, str]) -> Path:
    """``$XDG_CACHE_HOME/omicsclaw/envs``, else ``~/.cache/omicsclaw/envs``, from *environment*."""
    cache = environment.get("XDG_CACHE_HOME", "").strip()
    if cache:
        return Path(cache).expanduser() / "omicsclaw" / "envs"
    home = environment.get("HOME", "").strip()
    return (Path(home) if home else Path.home()) / ".cache" / "omicsclaw" / "envs"


# ---- the base's distributions ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BaseDistributions:
    """The distributions in the base's own site-packages, by normalised name."""

    versions: Mapping[str, tuple[str, ...]]
    """Normalised name to every version recorded for it, sorted; more than one
    when the base holds duplicate metadata for the same name."""
    unknown: int = 0
    """Metadata records whose name could not be read."""

    def has(self, name: str) -> bool:
        """Whether the base holds any record of *name*."""
        return normalise(name) in self.versions

    def of(self, name: str) -> tuple[str, ...]:
        """The versions recorded for *name*; empty when the base lacks it."""
        return self.versions.get(normalise(name), ())

    @property
    def digest(self) -> str:
        """sha256 of the sorted ``(name, version)`` records: the base's identity in a key, not a check."""
        pairs = sorted((name, version) for name, versions in self.versions.items() for version in versions)
        return hashlib.sha256(json.dumps(pairs).encode()).hexdigest()


def base_distributions(records: Iterable[tuple[str | None, str | None, str]]) -> BaseDistributions:
    """Group ``(Name, Version, metadata directory)`` records by normalised name.

    A record without a name or version takes them from its directory name
    (``<name>-<version>.dist-info`` or ``.egg-info``); one whose directory
    name cannot be read is counted in :attr:`BaseDistributions.unknown`.
    """
    found: dict[str, set[str]] = {}
    unknown = 0
    for name, version, directory in records:
        if not name or not version:
            parsed = _METADATA_DIR.match(directory or "")
            if parsed is None:
                unknown += 1
                continue
            name = name or parsed.group("name")
            version = version or parsed.group("version")
        found.setdefault(normalise(name), set()).add(version)
    return BaseDistributions({key: tuple(sorted(value)) for key, value in found.items()}, unknown)


def overlay_key(inventory: BaseInventory, base: BaseDistributions, specs: Iterable[str]) -> str:
    """The 16-hex-digit directory name for an overlay of *specs* on *inventory*'s interpreter."""
    payload = [
        inventory.real_executable,
        inventory.version,
        inventory.prefix,
        inventory.mtime_ns,
        base.digest,
        inventory.platform,
        inventory.machine,
        sorted(specs),
    ]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:16]


# ---- planning from pip's report --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Artifact:
    """One wheel pip resolved or installed."""

    name: str
    version: str
    wheel: str
    source: str
    """``scheme://host[:port]`` of the artifact URL without user info, or ``file:<directory>``."""
    transport: str
    """The artifact URL's scheme; ``http`` is plain text."""
    requested: bool = False

    @property
    def pin(self) -> str:
        """``name==version``."""
        return f"{self.name}=={self.version}"

    @property
    def identity(self) -> tuple[str, str, str]:
        """Normalised name, version and wheel file name."""
        return (normalise(self.name), self.version, self.wheel)

    def as_record(self) -> dict[str, str]:
        """The fields written to the overlay's metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "wheel": self.wheel,
            "source": self.source,
            "transport": self.transport,
        }


@dataclass(frozen=True, slots=True)
class Kept:
    """A package pip wanted at another version, left as the base has it."""

    name: str
    base_versions: tuple[str, ...]
    wanted: str

    @property
    def ambiguous(self) -> bool:
        """Whether the base records more than one version of it."""
        return len(self.base_versions) > 1


@dataclass(frozen=True, slots=True)
class Foreign:
    """A resolved package that is not an ordinary wheel, and which packages named it."""

    name: str
    version: str
    reason: str
    required_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FillPlan:
    """What to install, what the base keeps, and what may not be installed."""

    install: tuple[Artifact, ...]
    kept_from_base: tuple[Kept, ...]
    foreign: tuple[Foreign, ...]


def _artifact(item: Mapping[str, Any]) -> Artifact:
    metadata = item.get("metadata") or {}
    name, version = str(metadata.get("name", "")), str(metadata.get("version", ""))
    check_pin(name, version)
    url = str((item.get("download_info") or {}).get("url") or "")
    return Artifact(
        name=name,
        version=version,
        wheel=wheel_name(url),
        source=artifact_source(url),
        transport=artifact_transport(url),
        requested=bool(item.get("requested")),
    )


def fill_only(report: Mapping[str, Any], base: BaseDistributions) -> FillPlan:
    """Split a ``pip install --dry-run --report`` into what to install and what the base keeps.

    Every entry that is a direct URL, not an archive or not a wheel is
    foreign, with the names of the entries whose requirements mention it.
    An entry the base already has, under any version, is kept.

    :raises RequirementError: A name or version in the report is not well formed.
    """
    items = list(report.get("install") or [])
    install: list[Artifact] = []
    kept: list[Kept] = []
    foreign: list[Foreign] = []
    for item in items:
        artifact = _artifact(item)
        reason = foreign_reason(item)
        if reason:
            foreign.append(Foreign(artifact.name, artifact.version, reason, _required_by(artifact.name, items)))
        elif base.has(artifact.name):
            kept.append(Kept(artifact.name, base.of(artifact.name), artifact.version))
        else:
            install.append(artifact)
    return FillPlan(tuple(install), tuple(kept), tuple(foreign))


def _required_by(name: str, items: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    wanted = normalise(name)
    found = []
    for item in items:
        metadata = item.get("metadata") or {}
        for requirement in metadata.get("requires_dist") or ():
            head = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(requirement))
            if head and normalise(head.group(1)) == wanted:
                found.append(str(metadata.get("name", "")))
                break
    return tuple(found)


def new_violations(before: str, after: str) -> tuple[str, ...]:
    """The lines of ``pip check`` output *after* that are not in *before*, in *after*'s order."""
    seen = {line.strip() for line in before.splitlines()}
    fresh = []
    for line in after.splitlines():
        text = line.strip()
        if text and text != _CLEAR and text not in seen and text not in fresh:
            fresh.append(text)
    return tuple(fresh)


# ---- where installed files landed ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecordCheck:
    """What the ``RECORD`` files of an overlay's site-packages say about the installation."""

    landed: frozenset[str]
    """Normalised names of the checked distributions found in the overlay."""
    outside: tuple[str, ...] = ()
    """Recorded paths that resolve outside the overlay."""
    shadows: tuple[str, ...] = ()
    """New top-level modules or packages whose name the base can already import."""
    namespaces: tuple[str, ...] = ()
    """New namespace directories that share a name with something in the base."""
    pth_files: tuple[str, ...] = ()
    """New top-level ``.pth`` files."""


def check_records(
    site_packages: Path,
    overlay: Path,
    base_top_level: Mapping[str, str],
    installed: Iterable[str],
) -> RecordCheck:
    """Read the ``RECORD`` of each distribution in *installed* and check it against *overlay* and the base.

    :param site_packages: The overlay's site-packages directory.
    :param overlay: The overlay's ``.venv``; every recorded path must be inside it.
    :param base_top_level: Top-level names the base can import, by kind.
    :param installed: Names of the distributions this installation added; others
        in the overlay, such as a pip that ``ensurepip`` put there, are not checked.
    """
    wanted = {normalise(name) for name in installed}
    landed: set[str] = set()
    outside: list[str] = []
    top: dict[str, str] = {}
    pth: list[str] = []
    root = os.path.normpath(str(overlay))
    if not site_packages.is_dir():
        return RecordCheck(frozenset())
    for info in sorted(site_packages.glob("*.dist-info")):
        name = normalise(_metadata_name(info))
        if name not in wanted:
            continue
        landed.add(name)
        record = info / "RECORD"
        if not record.is_file():
            continue
        with open(record, newline="", encoding="utf-8") as source:
            paths = [row[0] for row in csv.reader(source) if row]
        for path in paths:
            placed = os.path.normpath(os.path.join(str(site_packages), path))
            if os.path.commonpath([root, placed]) != root:
                outside.append(path)
                continue
            head, _, rest = path.partition("/")
            if head.startswith("..") or head == "__pycache__" or head.endswith((".dist-info", ".data")):
                continue
            if not rest:
                if head.endswith(".pth"):
                    pth.append(head)
                elif head.endswith((".py", ".so", ".pyd")):
                    top[head.split(".", 1)[0]] = "module"
                continue
            kind = "package" if rest.startswith("__init__.") else "namespace"
            if top.get(head) in (None, "namespace"):
                top[head] = kind
    shadows = sorted(n for n, kind in top.items() if kind != "namespace" and n in base_top_level)
    namespaces = sorted(n for n, kind in top.items() if kind == "namespace" and n in base_top_level)
    return RecordCheck(frozenset(landed), tuple(outside), tuple(shadows), tuple(namespaces), tuple(sorted(pth)))


def _metadata_name(info: Path) -> str:
    try:
        with open(info / "METADATA", encoding="utf-8", errors="replace") as source:
            for line in source:
                if line.startswith("Name:"):
                    return line.partition(":")[2].strip()
                if not line.strip():
                    break
    except OSError:
        pass
    parsed = _METADATA_DIR.match(info.name)
    return parsed.group("name") if parsed else ""


# ---- running commands ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CommandOutput:
    """How one command ended."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class CommandRunner(Protocol):
    """Runs one command on this machine."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        timeout: float,
    ) -> CommandOutput:
        """Run *argv* in *cwd* with exactly *env*; kill its process group on timeout or cancellation."""
        ...


class LocalCommandRunner:
    """Runs commands as the leaders of new process groups, with no standard input.

    On timeout the whole group is killed and the output has ``timed_out``
    set; on cancellation the group is killed and the cancellation propagates.
    """

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        timeout: float,
    ) -> CommandOutput:
        process = await spawn_group_leader(
            asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=dict(env),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        )
        try:
            async with asyncio.timeout(timeout):
                stdout, stderr = await process.communicate()
        except TimeoutError:
            _kill_group(process)
            await process.wait()
            return CommandOutput(124, "", f"timed out after {timeout:g} s", timed_out=True)
        except BaseException:
            _kill_group(process)
            raise
        return CommandOutput(
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )


def _kill_group(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


# ---- building one overlay --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstallLimits:
    """Time limits of one installation, in seconds."""

    total_s: float = 1800.0
    """Everything after approval, the dry run and the installation included."""
    lock_s: float = 300.0
    """Waiting for another installation of the same overlay to finish."""
    resolve_s: float = 300.0
    """The dry run."""
    verify_s: float = 120.0
    """Importing the skill's modules in the finished overlay."""
    step_s: float = 300.0
    """Each other command: creating the overlay, reading pip's configuration, ``pip check``."""


@dataclass(frozen=True, slots=True)
class OverlayRequest:
    """What one overlay is built for."""

    skill: str
    names: tuple[str, ...]
    """The declared names asked for."""
    specs: tuple[str, ...]
    """The requirements handed to pip, already checked against the grammar."""
    required_imports: tuple[str, ...]
    """Modules of the names asked for, which must import."""
    other_imports: tuple[str, ...] = ()
    """The skill's other modules, imported and reported only."""


@dataclass(frozen=True, slots=True)
class OverlayResult:
    """How building an overlay ended."""

    status: str
    """``installed``, ``reused`` or ``failed``."""
    key: str
    python: Path
    reason: str = ""
    installed: tuple[Artifact, ...] = ()
    kept_from_base: tuple[Kept, ...] = ()
    violations: tuple[str, ...] = ()
    """``pip check`` lines the installation added."""
    namespaces: tuple[str, ...] = ()
    pth_files: tuple[str, ...] = ()
    imports: Mapping[str, str] = field(default_factory=dict)
    """Module to ``""`` when it imported, otherwise the error."""
    plan: FillPlan | None = None
    """The resolved plan, when a failure came after the dry run."""
    log_tail: str = ""
    unknown_base_records: int = 0
    escaped: bool = False
    """The failure was that installed files went outside the overlay, so removing
    the overlay did not remove everything the installation wrote."""


@dataclass(frozen=True, slots=True)
class OverlayInfo:
    """A finished overlay, as its metadata describes it."""

    key: str
    python: Path
    packages: tuple[str, ...]
    base_executable: str
    base_version: str
    base_prefix: str
    base_mtime_ns: int
    base_dists_sha256: str


def list_overlays(root: Path) -> tuple[OverlayInfo, ...]:
    """Every finished overlay under *root* whose metadata can be read. Reads files only."""
    found = []
    if not root.is_dir():
        return ()
    for directory in sorted(root.iterdir()):
        if not _KEY.fullmatch(directory.name):
            continue
        venv = directory / ".venv"
        if not (venv / FINGERPRINT).is_file():
            continue
        try:
            meta = json.loads((directory / META).read_text(encoding="utf-8"))
            found.append(
                OverlayInfo(
                    key=directory.name,
                    python=venv / "bin" / "python",
                    packages=tuple(str(name) for name in meta.get("packages", ())),
                    base_executable=str(meta["base_executable"]),
                    base_version=str(meta["base_version"]),
                    base_prefix=str(meta["base_prefix"]),
                    base_mtime_ns=int(meta["base_mtime_ns"]),
                    base_dists_sha256=str(meta["base_dists_sha256"]),
                )
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return tuple(found)


async def find_overlays(
    root: Path,
    result: ProbeResult,
    names: Iterable[str],
    runner: ProbeRunner,
    *,
    cwd: str,
) -> tuple[str, ...]:
    """Interpreters of finished overlays, built on the interpreter *result* describes, that hold any of *names*.

    For use where ``bash`` runs on this machine. The metadata is read first;
    only when an overlay was built on the same interpreter path, version,
    prefix and modification time is the base inventoried through *runner* to
    compare its distributions digest. Never raises: anything unreadable
    means no overlay.
    """
    wanted = {normalise(name) for name in names}
    if not wanted:
        return ()
    real = os.path.realpath(result.executable)
    try:
        mtime = os.stat(real).st_mtime_ns
    except OSError:
        return ()
    candidates = [
        info
        for info in list_overlays(root)
        if info.base_executable == real
        and info.base_version == result.version
        and info.base_prefix == result.prefix
        and info.base_mtime_ns == mtime
        and wanted & {normalise(name) for name in info.packages}
    ]
    if not candidates:
        return ()
    try:
        inventory = await run_inventory(runner, (), "", cwd=cwd, env={"PYTHONNOUSERSITE": "1"})
    except (ProbeError, OSError):
        return ()
    digest = base_distributions(inventory.records).digest
    return tuple(str(info.python) for info in candidates if info.base_dists_sha256 == digest)


class _Failure(Exception):
    def __init__(
        self,
        reason: str,
        *,
        plan: FillPlan | None = None,
        violations: Sequence[str] = (),
        escaped: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.plan = plan
        self.violations = tuple(violations)
        self.escaped = escaped


class _LockTimeout(Exception):
    pass


Progress = Callable[[str], Awaitable[object]]


class OverlayBuilder:
    """Builds overlays under one root directory.

    :param root: Where overlays and their locks live; a relative path is taken
        against the current directory now.
    :param environment: Returns the agent's environment when called; pip gets
        a whitelist of it (see :func:`~omicsclaw.skillenv.sources.pip_environment`)
        and interpreters started after the installation get less.
    :param runner: Runs the commands; defaults to :class:`LocalCommandRunner`.
    :param limits: Time limits.
    """

    def __init__(
        self,
        root: Path,
        *,
        environment: Callable[[], Mapping[str, str]],
        runner: CommandRunner | None = None,
        limits: InstallLimits = InstallLimits(),
    ) -> None:
        self.root = Path(root).expanduser().absolute()
        self._environment = environment
        self._runner = runner or LocalCommandRunner()
        self.limits = limits

    def python(self, key: str) -> Path:
        """The interpreter of overlay *key*."""
        return self.root / key / ".venv" / "bin" / "python"

    def finished(self, key: str) -> bool:
        """Whether overlay *key* has its fingerprint."""
        return (self.root / key / ".venv" / FINGERPRINT).is_file()

    async def build(
        self,
        request: OverlayRequest,
        inventory: BaseInventory,
        base: BaseDistributions,
        key: str,
        *,
        progress: Progress | None = None,
    ) -> OverlayResult:
        """Build overlay *key* for *request*, or reuse it when another call finished it first.

        *progress* is awaited with a short message at each stage. Only a
        cancellation propagates; every other failure, the overall time limit
        included, is an ``OverlayResult`` with ``status="failed"``.
        """
        python = self.python(key)
        directory = self.root / key
        work = Path(tempfile.mkdtemp(prefix="omicsclaw-install-"))
        log: list[str] = []
        lock: int | None = None
        try:
            async with asyncio.timeout(self.limits.total_s):
                self.root.mkdir(parents=True, exist_ok=True)
                lock = await _lock(self.root / ".locks" / f"{key}.lock", self.limits.lock_s)
                if self.finished(key):
                    return OverlayResult("reused", key, python)
                if directory.exists():
                    shutil.rmtree(directory)
                directory.mkdir()
                return await self._build(request, inventory, base, key, work, log, progress)
        except _LockTimeout:
            return OverlayResult(
                "failed", key, python,
                reason=f"another installation of the same overlay held its lock for {self.limits.lock_s:g} s",
            )
        except _Failure as failure:
            return OverlayResult(
                "failed", key, python, reason=failure.reason, plan=failure.plan,
                violations=failure.violations, log_tail=_tail(log), unknown_base_records=base.unknown,
                escaped=failure.escaped,
            )
        except TimeoutError:
            return OverlayResult(
                "failed", key, python,
                reason=f"the installation did not finish within {self.limits.total_s:g} s",
                log_tail=_tail(log),
            )
        finally:
            if lock is not None:
                if not self.finished(key) and directory.exists():
                    shutil.rmtree(directory, ignore_errors=True)
                fcntl.flock(lock, fcntl.LOCK_UN)
                os.close(lock)
            shutil.rmtree(work, ignore_errors=True)

    async def _build(
        self,
        request: OverlayRequest,
        inventory: BaseInventory,
        base: BaseDistributions,
        key: str,
        work: Path,
        log: list[str],
        progress: Progress | None,
    ) -> OverlayResult:
        directory = self.root / key

        async def say(message: str) -> None:
            if progress is not None:
                await progress(message)

        venv = directory / ".venv"
        python = str(venv / "bin" / "python")
        cwd = work / "cwd"
        home = work / "home"
        reports = work / "reports"
        for path in (cwd, home, reports):
            path.mkdir()
        agent = dict(self._environment())
        pip_env = pip_environment(agent)
        clean = clean_environment(agent, str(home))
        checking = {**clean, "PIP_CONFIG_FILE": os.devnull}

        async def run(
            stage: str, argv: list[str], env: Mapping[str, str], timeout: float, *, logged: bool = True
        ) -> CommandOutput:
            output = await self._runner.run(argv, cwd=str(cwd), env=env, timeout=timeout)
            log.append(f"$ {stage} (exit {output.exit_code})" + (f"\n{output.stdout}{output.stderr}" if logged else ""))
            if output.timed_out:
                raise _Failure(f"{stage} timed out after {timeout:g} s")
            return output

        await say("creating the overlay")
        create = [inventory.real_executable, "-I", "-m", "venv", "--system-site-packages"]
        if inventory.pip_version:
            create.append("--without-pip")
        made = await run("creating the overlay", [*create, str(venv)], clean, self.limits.step_s)
        if made.exit_code != 0 or not Path(python).exists():
            raise _Failure(f"creating the overlay failed (exit {made.exit_code})")

        pip = [python, "-I", "-m", "pip"]
        listed = await run("pip config list", [*pip, "config", "list"], config_list_environment(pip_env),
                           self.limits.step_s, logged=False)
        if listed.exit_code != 0:
            raise _Failure(f"pip config list failed (exit {listed.exit_code})")
        settings = location_settings(listed.stdout, pip_env)
        if settings:
            raise _Failure(
                "pip is configured to install somewhere other than the overlay, which could change the "
                "base environment: " + "; ".join(settings) + ". Remove those settings (for a file, "
                "`pip config unset <key>` or edit it; for a variable, unset it before starting OmicsClaw) "
                "and try again."
            )

        before = await run("pip check (before)", [*pip, "check"], checking, self.limits.step_s, logged=False)

        await say("resolving")
        plan_file = reports / "plan.json"
        resolved = await run(
            "pip install --dry-run",
            [*pip, "install", "--dry-run", "--only-binary=:all:", "--report", str(plan_file), "--", *request.specs],
            pip_env,
            self.limits.resolve_s,
        )
        if resolved.exit_code != 0 or not plan_file.is_file():
            wheelless = _NO_MATCH.findall(resolved.stderr)
            if wheelless:
                raise _Failure(
                    "no-wheel: pip found no wheel for " + ", ".join(dict.fromkeys(wheelless))
                    + " through this machine's pip configuration; source distributions are not built"
                )
            raise _Failure(f"pip could not resolve {', '.join(request.specs)} (exit {resolved.exit_code})")
        try:
            report = json.loads(plan_file.read_text(encoding="utf-8"))
            plan = fill_only(report, base)
        except RequirementError as exc:
            raise _Failure(str(exc)) from None
        except (ValueError, TypeError, AttributeError) as exc:
            raise _Failure(f"pip's dry-run report could not be read: {exc}") from None
        if plan.foreign:
            described = "; ".join(
                f"{item.name} {item.version}: {item.reason}"
                + (f", named by {', '.join(item.required_by)}" if item.required_by else "")
                for item in plan.foreign
            )
            raise _Failure("the resolution includes packages that are not ordinary wheels: " + described, plan=plan)
        if not plan.install:
            raise _Failure(
                "pip found every requirement already satisfied by the base environment, "
                "so there is nothing to put in an overlay",
                plan=plan,
            )

        await say(f"installing {len(plan.install)} wheel(s)")
        installed_file = reports / "installed.json"
        pins = [artifact.pin for artifact in plan.install]
        done = await run(
            "pip install",
            [*pip, "install", "--no-deps", "--only-binary=:all:", "--report", str(installed_file), "--", *pins],
            pip_env,
            self.limits.total_s,
        )
        if done.exit_code != 0 or not installed_file.is_file():
            raise _Failure(f"pip install failed (exit {done.exit_code})", plan=plan)
        try:
            installed = tuple(_artifact(item) for item in json.loads(installed_file.read_text())["install"])
        except (RequirementError, KeyError, ValueError) as exc:
            raise _Failure(f"pip's installation report could not be read: {exc}", plan=plan) from None
        if sorted(a.identity for a in installed) != sorted(a.identity for a in plan.install):
            planned = ", ".join(sorted(a.wheel for a in plan.install))
            actual = ", ".join(sorted(a.wheel for a in installed))
            raise _Failure(f"pip installed other files than it planned: planned {planned}; installed {actual}",
                           plan=plan)

        await say("checking")
        version = ".".join(inventory.version.split(".")[:2])
        records = check_records(
            venv / "lib" / f"python{version}" / "site-packages", venv, inventory.top_level, (a.name for a in installed)
        )
        if records.outside:
            raise _Failure("installed files landed outside the overlay: " + ", ".join(records.outside[:10]),
                           plan=plan, escaped=True)
        absent = sorted(a.name for a in installed if normalise(a.name) not in records.landed)
        if absent:
            raise _Failure("installed packages are not in the overlay's site-packages: " + ", ".join(absent),
                           plan=plan, escaped=True)
        if records.shadows:
            raise _Failure(
                "new modules would hide ones the base environment already has: " + ", ".join(records.shadows),
                plan=plan,
            )

        after = await run("pip check (after)", [*pip, "check"], checking, self.limits.step_s, logged=False)
        added = new_violations(before.stdout, after.stdout)
        if added:
            raise _Failure("the installation breaks declared requirements", plan=plan, violations=added)

        await say("verifying imports")
        modules = tuple(dict.fromkeys((*request.required_imports, *request.other_imports)))
        verified = await run("verifying imports", [python, "-I", "-B", "-c", _verify_code(modules)], clean,
                             self.limits.verify_s)
        imports = _verify_result(verified.stdout)
        failed = [name for name in request.required_imports if imports.get(name, "not reported") != ""]
        if failed:
            raise _Failure(
                "the installed packages do not import: "
                + "; ".join(f"{name}: {imports.get(name, 'not reported')}" for name in failed),
                plan=plan,
            )

        meta = {
            "key": key,
            "skill": request.skill,
            "packages": list(request.names),
            "requested_specs": list(request.specs),
            "installed": [artifact.as_record() for artifact in installed],
            "kept_from_base": [
                {"name": item.name, "base_versions": list(item.base_versions), "wanted": item.wanted}
                for item in plan.kept_from_base
            ],
            "package_sources": PACKAGE_SOURCES,
            "base_executable": inventory.real_executable,
            "base_version": inventory.version,
            "base_prefix": inventory.prefix,
            "base_mtime_ns": inventory.mtime_ns,
            "base_platform": inventory.platform,
            "base_machine": inventory.machine,
            "base_dists_sha256": base.digest,
            "pip_version": str(report.get("pip_version", "")),
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        (directory / META).write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
        (venv / FINGERPRINT).write_text(key + "\n", encoding="utf-8")
        return OverlayResult(
            "installed", key, Path(python),
            installed=installed, kept_from_base=plan.kept_from_base, namespaces=records.namespaces,
            pth_files=records.pth_files, imports=imports, plan=plan, unknown_base_records=base.unknown,
        )


async def _lock(path: Path, timeout: float) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except BlockingIOError:
                if loop.time() >= deadline:
                    raise _LockTimeout() from None
                await asyncio.sleep(0.05)
    except BaseException:
        os.close(handle)
        raise


def _verify_code(modules: Sequence[str]) -> str:
    return (
        "import sys\n"
        "sys.path[:] = [p for p in sys.path if p not in ('', '.')]\n"
        "import importlib, json\n"
        f"names = json.loads({json.dumps(list(modules))!r})\n"
        "results = {}\n"
        "for name in names:\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "        results[name] = ''\n"
        "    except BaseException as exc:\n"
        "        results[name] = '%s: %s' % (type(exc).__name__, exc)\n"
        f"print({_VERIFY_MARK!r} + json.dumps(results))\n"
    )


def _verify_result(output: str) -> dict[str, str]:
    for line in reversed(output.splitlines()):
        if line.startswith(_VERIFY_MARK):
            try:
                return {str(k): str(v) for k, v in json.loads(line[len(_VERIFY_MARK):]).items()}
            except (ValueError, AttributeError):
                break
    return {}


def _tail(log: Sequence[str], limit: int = 2000) -> str:
    return redact("\n".join(log))[-limit:]
