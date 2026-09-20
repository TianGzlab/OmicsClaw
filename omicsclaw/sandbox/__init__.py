"""``omicsclaw.sandbox`` — run the agent's shell commands in a container.

Starts one Docker (or Docker-compatible) container per agent, with no
network, no capabilities and the workspace bind-mounted at its own path,
and hands back an environment whose ``run_bash`` the ``bash`` tool can be
constructed with::

    from omicsclaw.sandbox import SandboxConfig, SandboxManager

    manager = SandboxManager(SandboxConfig(image="omicsclaw/runtime:1"))
    await manager.reap_orphans()
    environment = await manager.create_with_retry(workspace)
    bash = BashTool(workspace_boundary, environment=environment)
    ...
    await manager.aclose()

Only ``bash`` runs inside the container. Standard library only; this
package imports no other ``omicsclaw`` package.
"""

from .config import (
    NETWORK_NONE,
    SandboxConfig,
    SandboxConfigError,
    check_mount_path,
    host_user,
)
from .container import (
    EXCHANGE_DIR,
    LABEL,
    NAME_PREFIX,
    OWNER_LABEL,
    Container,
    ContainerState,
    owner_token,
    run_arguments,
)
from .daemon import DaemonStarter, desktop_starter, ensure_daemon_ready
from .environment import DockerEnvironment, ExecResult
from .manager import (
    BootstrapOutcome,
    ChangeListener,
    ReapReport,
    SandboxInfo,
    SandboxManager,
    owner_is_dead,
)
from .runner import (
    CommandRunner,
    CommandTimedOut,
    Completed,
    SandboxError,
    SubprocessRunner,
)

__all__ = [
    "BootstrapOutcome",
    "ChangeListener",
    "CommandRunner",
    "CommandTimedOut",
    "Completed",
    "Container",
    "ContainerState",
    "DaemonStarter",
    "DockerEnvironment",
    "EXCHANGE_DIR",
    "ExecResult",
    "LABEL",
    "NAME_PREFIX",
    "NETWORK_NONE",
    "OWNER_LABEL",
    "ReapReport",
    "SandboxConfig",
    "SandboxConfigError",
    "SandboxError",
    "SandboxInfo",
    "SandboxManager",
    "SubprocessRunner",
    "check_mount_path",
    "desktop_starter",
    "ensure_daemon_ready",
    "host_user",
    "owner_is_dead",
    "owner_token",
    "run_arguments",
]
