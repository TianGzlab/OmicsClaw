"""The sandbox, as one deployment uses it: started, degraded, or off.

:func:`open_sandbox` starts the container a configuration asks for and
returns a :class:`SandboxBinding`. A sandbox that cannot start leaves the
deployment running ``bash`` on this machine — logged as a warning and
stated in the system prompt — unless
:attr:`~omicsclaw.entry.config.AppConfig.sandbox_required` is set, in
which case start-up fails.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass

from omicsclaw.context import Section, static
from omicsclaw.sandbox import (
    ChangeListener,
    CommandRunner,
    DockerEnvironment,
    SandboxConfig,
    SandboxError,
    SandboxManager,
)
from omicsclaw.tools import ApprovalMode, ToolPolicy

from .config import AppConfig, SandboxMode

__all__ = [
    "SandboxBinding",
    "bash_policy",
    "open_sandbox",
    "sandbox_section",
    "unstarted_sandbox",
]

_log = logging.getLogger(__name__)

_REASON_CHARS = 300


@dataclass(frozen=True, slots=True)
class SandboxBinding:
    """What one deployment got when it asked for a sandbox."""

    mode: SandboxMode = SandboxMode.OFF
    environment: DockerEnvironment | None = None
    """Where ``bash`` runs; ``None`` means on this machine."""

    manager: SandboxManager | None = None
    """Owns the container; ``None`` unless :attr:`environment` is set."""

    config: SandboxConfig | None = None
    unavailable: str = ""
    """Why a requested sandbox is not in use. Empty when off or running."""

    @property
    def active(self) -> bool:
        return self.environment is not None

    @property
    def degraded(self) -> bool:
        """A sandbox was asked for and ``bash`` runs on this machine anyway."""
        return self.mode is not SandboxMode.OFF and not self.active

    @property
    def isolates_network(self) -> bool:
        """``True`` only while commands run in a container with no network."""
        return self.active and self.config is not None and self.config.isolates_network

    async def aclose(self) -> None:
        """Stop and remove the container, if there is one."""
        if self.manager is not None:
            await self.manager.aclose()


async def open_sandbox(
    config: AppConfig,
    *,
    on_change: ChangeListener | None = None,
    runner: CommandRunner | None = None,
) -> SandboxBinding:
    """Start the sandbox *config* asks for, over its workspace.

    Orphans of dead processes are removed first; creation waits for the
    daemon and is retried once. Returns an inactive binding when the
    sandbox is off, and a degraded one when it could not start.

    Raises :exc:`~omicsclaw.sandbox.SandboxConfigError` for an unusable
    setting, and :exc:`~omicsclaw.sandbox.SandboxError` when it could not
    start and :attr:`AppConfig.sandbox_required` is set.
    """
    sandbox_config = config.sandbox_config()
    if sandbox_config is None:
        return SandboxBinding()

    manager = SandboxManager(sandbox_config, runner=runner, on_change=on_change)
    try:
        report = await manager.reap_orphans()
    except SandboxError as exc:
        _log.warning("could not look for orphaned sandboxes: %s", exc)
    else:
        if report.removed:
            _log.info("removed %d orphaned sandbox(es)", len(report.removed))
        if report.failed:
            _log.warning(
                "could not remove orphaned sandbox(es): %s", ", ".join(report.failed)
            )

    try:
        environment = await manager.create_with_retry(config.workspace)
    except SandboxError as exc:
        await manager.aclose()
        return _degraded(config, sandbox_config, str(exc))

    info = manager.info(environment.id)
    if info is not None and info.bootstrap is not None and not info.bootstrap.ok:
        _log.warning(
            "sandbox bootstrap %s; continuing",
            (
                "timed out"
                if info.bootstrap.timed_out
                else f"exited with status {info.bootstrap.exit_code}"
            ),
        )
    _log.info(
        "sandbox running: image=%s network=%s container=%s",
        sandbox_config.image,
        sandbox_config.network,
        environment.container_id[:12],
    )
    return SandboxBinding(
        mode=config.sandbox,
        environment=environment,
        manager=manager,
        config=sandbox_config,
    )


def unstarted_sandbox(config: AppConfig) -> SandboxBinding:
    """The binding for a deployment built without :func:`open_sandbox`.

    Off stays off. A requested sandbox is reported degraded, since nothing
    started it — or refused, when :attr:`AppConfig.sandbox_required` is
    set.
    """
    if config.sandbox is SandboxMode.OFF:
        return SandboxBinding()
    return _degraded(
        config,
        config.sandbox_config(),
        "this deployment was built without starting it (use open_app)",
    )


def sandbox_section(binding: SandboxBinding) -> Section | None:
    """The system-prompt section describing where ``bash`` runs.

    ``None`` when the sandbox is off, so an unsandboxed deployment's
    prompt is unchanged.
    """
    if binding.mode is SandboxMode.OFF:
        return None
    if binding.active and binding.config is not None:
        text = _running_text(binding.config)
    else:
        text = _degraded_text(binding.unavailable)
    return Section("sandbox", "## Execution sandbox", static(text))


def bash_policy(
    binding: SandboxBinding,
    policy: ToolPolicy,
    *,
    auto_approve: bool,
) -> ToolPolicy:
    """*policy* with approval switched off, when that is safe; else *policy*.

    Only when *auto_approve* is requested **and** the sandbox is running
    **and** its container has no network. A degraded sandbox or an open
    network always keeps *policy* as given.
    """
    if not auto_approve:
        return policy
    if not binding.isolates_network:
        why = (
            "the sandbox is not running"
            if not binding.active
            else "the sandbox network is not 'none'"
        )
        _log.warning("sandbox_auto_approve ignored: %s; bash still asks", why)
        return policy
    return dataclasses.replace(policy, approval_mode=ApprovalMode.AUTO)


def _degraded(
    config: AppConfig,
    sandbox_config: SandboxConfig | None,
    reason: str,
) -> SandboxBinding:
    if config.sandbox_required:
        raise SandboxError(
            f"sandbox_required is set and the sandbox is unavailable: {reason}"
        )
    _log.warning(
        "sandbox unavailable, bash runs on this machine without isolation: %s",
        reason,
    )
    return SandboxBinding(
        mode=config.sandbox,
        config=sandbox_config,
        unavailable=reason,
    )


def _running_text(config: SandboxConfig) -> str:
    lines = [
        f"- `bash` runs inside an isolated container (image `{config.image}`), "
        "not on this machine.",
        "- Its working directory is the workspace, mounted at the same path, "
        "so files it writes are the files read_file, write_file and "
        "edit_file see. Those tools and the web tools run on this machine.",
    ]
    if config.isolates_network:
        lines.append(
            "- The container has no network access: downloads, package "
            "installs and remote APIs fail by design. Use the software "
            "already in the image."
        )
    else:
        lines.append(f"- The container can reach network `{config.network}`.")
    if config.read_only_mounts:
        mounts = ", ".join(str(path) for path in config.read_only_mounts)
        lines.append(f"- Also visible, read-only: {mounts}.")
    lines.append(
        "- Nothing else of this machine's filesystem is visible, and anything "
        "written outside the workspace is lost when the session ends."
    )
    return "\n".join(lines)


def _degraded_text(reason: str) -> str:
    if len(reason) > _REASON_CHARS:
        reason = reason[: _REASON_CHARS - 1] + "…"
    return "\n".join(
        (
            f"- A container sandbox was requested but is not running: {reason}",
            "- `bash` therefore runs directly on this machine, as the user "
            "running this agent, with no isolation. Ask the user before "
            "anything destructive or irreversible.",
        )
    )
