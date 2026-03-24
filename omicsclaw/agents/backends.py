"""Custom backends for the OmicsClaw research pipeline.

Adapts EvoScientist's backend architecture:
- OmicsClawSandboxBackend: sandboxed shell execution + file ops
- ReadOnlySkillsBackend: read-only access to skills/ directory

These backends are used by deepagents' create_deep_agent() to provide
file system and shell capabilities within the research pipeline.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# System path prefixes to block — only truly dangerous system areas.
# NOTE: /home/ and /tmp/ are intentionally NOT blocked because research
# workspaces and data directories typically live under /home/ or /data*/.
_SYSTEM_PATH_PREFIXES = (
    "/var/", "/etc/",
    "/opt/", "/usr/", "/bin/", "/sbin/", "/dev/",
    "/proc/", "/sys/", "/root/",
)

# Dangerous commands
BLOCKED_COMMANDS = [
    "sudo", "chmod", "chown", "mkfs", "dd", "shutdown", "reboot",
]

BLOCKED_PATTERNS = [
    r"~/",
    r"\bcd\s+/",
    r"\brm\s+-rf\s+/",
]


def validate_command(command: str) -> str | None:
    """Validate a shell command for safety.

    Returns None if safe, error message if blocked.
    """
    # Check path traversal
    for token in command.split():
        if ".." in Path(token).parts if "/" in token else ():
            return (
                "Command blocked: contains '..' path traversal. "
                "Use relative paths within the workspace."
            )

    # Check dangerous patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return f"Command blocked: forbidden pattern '{pattern}'."

    # Check dangerous commands
    for segment in re.split(r"\s*(?:&&|\|\||;)\s*", command):
        for pipe_seg in segment.split("|"):
            pipe_seg = pipe_seg.strip()
            if not pipe_seg:
                continue
            try:
                tokens = shlex.split(pipe_seg)
            except ValueError:
                tokens = pipe_seg.split()
            if tokens and tokens[0] in BLOCKED_COMMANDS:
                return f"Command blocked: '{tokens[0]}' is not allowed."

    return None


def convert_virtual_paths(command: str, workspace_name: str = "") -> str:
    """Convert virtual paths in commands to relative paths."""

    def _replace(match: re.Match[str]) -> str:
        path = match.group(0)
        if "://" in command[max(0, match.start() - 10):match.end() + 10]:
            return path
        if workspace_name:
            for prefix in _SYSTEM_PATH_PREFIXES:
                if path.startswith(prefix):
                    marker = f"/{workspace_name}/"
                    idx = path.find(marker)
                    if idx != -1:
                        rel = path[idx + len(marker):]
                        return "./" + rel if rel else "."
                    break
        return "." if path == "/" else "." + path

    pattern = r'(?<=\s)/[^\s;|&<>\'"`` ]*|^/[^\s;|&<>\'"`` ]*'
    return re.sub(pattern, _replace, command)


def create_sandbox_backend(workspace_dir: str):
    """Create a sandboxed backend for the research pipeline.

    Uses deepagents' LocalShellBackend with safety wrappers.

    Parameters
    ----------
    workspace_dir : str
        Root directory for the pipeline workspace.

    Returns
    -------
    CustomSandboxBackend instance
    """
    from deepagents.backends import LocalShellBackend

    class OmicsClawSandboxBackend(LocalShellBackend):
        """Sandboxed backend with command validation."""

        def __init__(self, root_dir: str, **kwargs):
            super().__init__(
                root_dir=root_dir,
                virtual_mode=False,
                timeout=300,
                max_output_bytes=100_000,
                inherit_env=True,
                **kwargs,
            )
            self._sandbox_id = f"omicsclaw-{uuid.uuid4().hex[:8]}"
            os.makedirs(str(self.cwd), exist_ok=True)

        def execute(self, command: str, *, timeout=None):
            """Execute with safety validation."""
            from deepagents.backends.protocol import ExecuteResponse

            error = validate_command(command)
            if error:
                return ExecuteResponse(output=error, exit_code=1, truncated=False)

            # Still replace the workspace absolute path with ./ for cleaner shell commands
            ws = str(self.cwd).rstrip("/") + "/"
            if ws in command:
                command = command.replace(ws, "./")

            return super().execute(command, timeout=timeout)

    return OmicsClawSandboxBackend(workspace_dir)


def create_skills_backend(project_root: str):
    """Create a read-only backend for the skills directory.

    Parameters
    ----------
    project_root : str
        OmicsClaw project root (parent of skills/).

    Returns
    -------
    ReadOnlyFilesystemBackend instance
    """
    from deepagents.backends import FilesystemBackend
    from deepagents.backends.protocol import EditResult, WriteResult

    skills_dir = os.path.join(project_root, "skills")

    class ReadOnlySkillsBackend(FilesystemBackend):
        """Read-only access to OmicsClaw skills definitions."""

        def write(self, *args, **kwargs):
            return WriteResult(error="Skills directory is read-only.")

        def edit(self, *args, **kwargs):
            return EditResult(error="Skills directory is read-only.")

    return ReadOnlySkillsBackend(root_dir=skills_dir, virtual_mode=True)
