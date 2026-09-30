"""A local trial never receives the framework's control-plane credentials.

Plan 0062 §3.7 / case 11. ``ENV_WHITELIST`` already leaves the token behind;
``LocalExecutor.environment`` also filters what the caller adds on top, so a
future whitelist entry or ``extra`` key cannot carry it into a trial. This is
defence in depth — today's callers only pass fixed keys.
"""

from __future__ import annotations

import asyncio
import os
import shutil

from omicsclaw.ensemble.execution import ENV_WHITELIST, LocalExecutor
from omicsclaw.tools.builtin.bash import CONTROL_CREDENTIAL_NAMES


def _base():
    return {"PATH": os.environ["PATH"], "OMICSCLAW_REMOTE_AUTH_TOKEN": "base-secret"}


def test_environment_drops_the_token_from_base_and_extra():
    env = LocalExecutor(base_env=_base()).environment(
        {"OMICSCLAW_REMOTE_AUTH_TOKEN": "x", "omicsclaw_remote_auth_token": "y", "A": "1"}
    )
    assert "A" in env and env["A"] == "1"
    assert not {name.upper() for name in env} & CONTROL_CREDENTIAL_NAMES


def test_whitelist_and_credential_names_do_not_overlap():
    assert not {name.upper() for name in ENV_WHITELIST} & CONTROL_CREDENTIAL_NAMES


def test_a_real_run_does_not_see_the_token(tmp_path):
    log = tmp_path / "run.log"
    result = asyncio.run(
        LocalExecutor(base_env=_base()).run(
            [shutil.which("env") or "/usr/bin/env"],
            cwd=tmp_path,
            env={"OMICSCLAW_REMOTE_AUTH_TOKEN": "extra-secret", "TRIAL_KEEP": "kept"},
            log=log,
            timeout=30,
        )
    )
    text = log.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert "TRIAL_KEEP=kept" in text
    assert "secret" not in text
