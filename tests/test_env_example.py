"""``.env.example`` describes the stack that exists, not the one that did.

The previous version of this file asserted that twenty-one names were
*substrings* of the template. That check could not fail in the way it
needed to: after the rebuild moved eight chat platforms and the legacy
memory service out of the reachable configuration, the template listed
them under "no longer read" —— and the substring test passed, because
the names were still on the page. A guard that cannot tell "you can set
this" from "this does nothing" is a spelling check.

So the two halves are asserted separately, against how the template is
*written* rather than what it mentions: a settable variable is one that
appears as ``NAME=`` or ``#NAME=`` at the start of a line, and a retired
one is named in prose inside the closing section.
"""

from __future__ import annotations

import pathlib
import re

TEMPLATE = pathlib.Path(".env.example")

_SETTABLE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", re.MULTILINE)

READ_BY_THE_STACK = (
    # the provider layer
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "OMICSCLAW_MODEL",
    "OMICSCLAW_LLM_TIMEOUT_SECONDS",
    # the entry layer's deployment options
    "OMICSCLAW_WORKSPACE",
    "OMICSCLAW_TOOL_TIMEOUT_S",
    "OMICSCLAW_MAX_TURNS",
    "OMICSCLAW_COMPACT_AT",
    "OMICSCLAW_SKILLS_INDEX",
    "OMICSCLAW_PERMISSION_MODE",
    "OMICSCLAW_SANDBOX",
    "OMICSCLAW_MCP_CONFIG",
    # the surfaces that can be started
    "OMICSCLAW_REMOTE_AUTH_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "FEISHU_APP_ID",
    "FEISHU_ALLOWED_SENDERS",
)
"""Variables a deployment can actually set today.

Every one is read by ``omicsclaw/{provider,entry,launch}/``; this list is
deliberately a sample of each group rather than the full table, because
the full table lives in ``omicsclaw/entry/config.py`` and duplicating it
here would give two things to update and one of them would rot.
"""

RETIRED = (
    "SLACK_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "WECHAT_APP_ID",
    "WECOM_CORP_ID",
    "DINGTALK_CLIENT_ID",
    "QQ_APP_ID",
    "IMESSAGE_CLI_PATH",
    "EMAIL_IMAP_HOST",
    "OMICSCLAW_MEMORY_DB_URL",
    "OMICSCLAW_MAX_HISTORY",
    "OMICSCLAW_MAX_TOOL_ITERATIONS",
    "OMICSCLAW_DATA_DIRS",
    "GLOBAL_RATE_LIMIT",
)
"""Variables the rebuilt stack ignores.

Kept in the template on purpose: someone upgrading has them in their own
``.env`` and needs to be told they do nothing, which is a different
message from silence. The eight chat platforms are gated rather than
deleted —— ``build_channel`` has a builder for Telegram and Feishu only.
"""


def _settable() -> set[str]:
    """Names the template offers as an assignment, anywhere in the file.

    Whole-file rather than "everything above the retired heading": the
    closing section names its variables in prose, so it has nothing to
    lose by being scanned —— and scanning it is what stops a retired name
    from being quietly re-offered by appending one line to the bottom.
    A first draft of this helper cut the text at the heading, and a
    mutation that appended ``#SLACK_BOT_TOKEN=`` survived it.
    """
    return set(_SETTABLE.findall(TEMPLATE.read_text(encoding="utf-8")))


def test_every_live_variable_can_be_set_from_the_template():
    missing = [name for name in READ_BY_THE_STACK if name not in _settable()]

    assert not missing, (
        f"{missing} are read by the rebuilt stack but the template offers "
        "no line to set them"
    )


def test_a_retired_variable_is_named_but_never_offered():
    """The half the old substring check could not express.

    Being *mentioned* is required —— an upgrader has these in their own
    file. Being *settable* is forbidden, because a commented ``NAME=`` is
    an invitation, and the whole point is that filling it in would do
    nothing.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    offered = _settable()

    unmentioned = [name for name in RETIRED if name not in text]
    advertised = [name for name in RETIRED if name in offered]

    assert not unmentioned, f"{unmentioned} vanished instead of being retired"
    assert not advertised, (
        f"{advertised} are offered as settings but nothing reads them"
    )


def test_the_template_says_where_it_is_read():
    """A template that does not say when it is loaded invites the bug
    plan 0037 found: the shell did not read ``.env`` at all, and every
    error looked like a wrong key instead of an unread file."""
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "omicsclaw/launch/" in text
    assert "exported" in text
