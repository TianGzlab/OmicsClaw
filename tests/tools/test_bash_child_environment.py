"""The ``bash`` tool's local shell does not inherit framework control credentials.

Plan 0062 D4 / §3.7: scrubbing moved out of the skill helpers and into the
framework's launch boundary. The name list is compared case-insensitively,
as the deleted ``is_internal_control_credential_name`` did with
``str(name).upper()``; the lower-case variant below pins that. Everything
else in the environment is inherited exactly as before.
"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

from omicsclaw.launch._surfaces import DESKTOP_TOKEN_VARIABLE
from omicsclaw.tools import ApprovalDecision
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.builtin import bash as bash_module
from omicsclaw.tools.builtin.bash import (
    CONTROL_CREDENTIAL_NAMES,
    BashTool,
    without_control_credentials,
)
from omicsclaw.tools.context import use_tool_context


def _bash(tmp_path: Path, command: str) -> str:
    tool = BashTool(Workspace(tmp_path))
    with use_tool_context(approval=lambda request: ApprovalDecision(approved=True)):
        return asyncio.run(asyncio.wait_for(tool.execute(json.dumps({"command": command})), 20))


def test_local_shell_drops_the_token_and_keeps_the_rest(monkeypatch, tmp_path):
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "secret-upper")
    monkeypatch.setenv("omicsclaw_remote_auth_token", "secret-lower")
    monkeypatch.setenv("OMICSCLAW_BASH_SENTINEL", "sentinel-value")

    out = _bash(
        tmp_path,
        "echo ${OMICSCLAW_REMOTE_AUTH_TOKEN-unset}:${omicsclaw_remote_auth_token-unset}:$OMICSCLAW_BASH_SENTINEL",
    )

    assert "unset:unset:sentinel-value" in out
    assert "secret" not in out


def test_without_control_credentials_filters_a_given_mapping():
    source = {
        "OMICSCLAW_REMOTE_AUTH_TOKEN": "x",
        "Omicsclaw_Remote_Auth_Token": "y",
        "PATH": "/bin",
    }
    assert without_control_credentials(source) == {"PATH": "/bin"}
    assert source["OMICSCLAW_REMOTE_AUTH_TOKEN"] == "x"


def test_without_control_credentials_defaults_to_the_process_environment(monkeypatch):
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "x")
    monkeypatch.setenv("OMICSCLAW_BASH_SENTINEL", "kept")
    env = without_control_credentials()
    assert "OMICSCLAW_REMOTE_AUTH_TOKEN" not in env
    assert env["OMICSCLAW_BASH_SENTINEL"] == "kept"


def test_the_desktop_token_is_on_the_list():
    assert DESKTOP_TOKEN_VARIABLE.upper() in CONTROL_CREDENTIAL_NAMES
    assert all(name == name.upper() for name in CONTROL_CREDENTIAL_NAMES)


def test_no_function_shares_the_mcp_child_environment_name():
    """``omicsclaw/mcp/stdio.py`` already has ``child_environment``; two would be confused."""
    tree = ast.parse(Path(bash_module.__file__).read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "child_environment" not in names
