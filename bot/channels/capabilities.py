"""
Channel capabilities declaration system.

Each channel declares its capabilities via a ChannelCapabilities dataclass,
enabling the framework to adapt behavior automatically (formatting, chunking,
media handling, etc.) without per-channel branching in core logic.

Inspired by EvoScientist's capabilities.py, adapted for OmicsClaw's
lightweight AsyncOpenAI-based architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FormatType = Literal["html", "markdown", "plain"]


@dataclass(frozen=True)
class ChannelCapabilities:
    """Immutable declaration of what a channel supports.

    Set once as a class attribute on each Channel subclass.
    The framework inspects these at runtime to auto-configure behavior.
    """

    # ── Messaging features ──────────────────────────────────────────
    format_type: FormatType = "plain"
    max_text_length: int = 4096
    max_file_size: int = 20 * 1024 * 1024  # 20 MB

    # ── Interaction capabilities ────────────────────────────────────
    typing: bool = False          # typing indicator API
    reactions: bool = False       # emoji reactions on messages

    # ── Media capabilities ──────────────────────────────────────────
    media_send: bool = False      # can send files/images
    media_receive: bool = False   # can receive files/images
    voice: bool = False           # voice/audio messages

    # ── Group features ──────────────────────────────────────────────
    groups: bool = False          # group chat support
    mentions: bool = False        # @mention detection

    # ── Rich text ───────────────────────────────────────────────────
    markdown: bool = False        # supports Markdown rendering
    html: bool = False            # supports HTML rendering

    # ── Extended capabilities ────────────────────────────────────────
    edit: bool = False            # message editing after send
    native_commands: bool = False # platform-native slash commands

    def supports(self, feature: str) -> bool:
        """Check if a feature is supported by name."""
        return getattr(self, feature, False)


# ═════════════════════════════════════════════════════════════════════
# Pre-built capability profiles for OmicsClaw channels
# ═════════════════════════════════════════════════════════════════════

TELEGRAM = ChannelCapabilities(
    format_type="html",
    max_text_length=4000,     # Safe limit (Telegram hard limit is 4096)
    max_file_size=50 * 1024 * 1024,
    typing=True,
    reactions=True,
    media_send=True,
    media_receive=True,
    voice=True,
    groups=True,
    mentions=True,
    html=True,
    edit=True,
    native_commands=True,
)

FEISHU = ChannelCapabilities(
    format_type="markdown",
    max_text_length=4000,
    max_file_size=20 * 1024 * 1024,
    typing=False,             # Feishu has no typing indicator API
    media_send=True,
    media_receive=True,
    voice=True,
    groups=True,
    mentions=True,
    markdown=True,
    edit=True,
)

DINGTALK = ChannelCapabilities(
    format_type="markdown",
    max_text_length=4096,
    typing=False,
    media_send=True,
    media_receive=True,
    groups=True,
    mentions=True,
    markdown=True,
)

DISCORD = ChannelCapabilities(
    format_type="markdown",
    max_text_length=2000,
    typing=True,
    reactions=True,
    media_send=True,
    media_receive=True,
    groups=True,
    mentions=True,
    markdown=True,
    edit=True,
    native_commands=True,
)

SLACK = ChannelCapabilities(
    format_type="plain",     # Slack mrkdwn is non-standard
    max_text_length=4000,
    reactions=True,
    media_send=True,
    media_receive=True,
    groups=True,
    mentions=True,
    edit=True,
    native_commands=True,
)

WECHAT = ChannelCapabilities(
    format_type="markdown",
    max_text_length=4096,
    media_send=True,
    media_receive=True,
    groups=True,
    mentions=True,
    markdown=True,
)

QQ = ChannelCapabilities(
    format_type="plain",
    max_text_length=4096,
    media_send=True,
    media_receive=True,
    groups=True,
    mentions=True,
)

EMAIL = ChannelCapabilities(
    format_type="html",
    max_text_length=0,      # No practical limit
    max_file_size=20 * 1024 * 1024,
    media_send=True,
    media_receive=True,
    html=True,
)

IMESSAGE = ChannelCapabilities(
    format_type="plain",
    max_text_length=4000,
    media_send=True,
    media_receive=True,
    groups=True,
    voice=True,
)
