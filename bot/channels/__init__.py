"""OmicsClaw Multi-Channel communication framework.

Provides an extensible interface for different messaging channels
(Telegram, Feishu, DingTalk, Discord, Slack, WeChat, etc.)
to communicate with the OmicsClaw LLM engine.

Architecture:
    Channel handler → core.llm_tool_loop → reply via channel.send

Each channel calls ``bot.core.llm_tool_loop`` directly from its
platform handler. Cross-cutting concerns (rate limit, dedup, audit)
live in ``bot.core`` / ``bot.rate_limit`` rather than a separate
middleware pipeline.

Components:
    - Channel ABC:          base interface for all channels
    - ChannelCapabilities:  feature declaration per channel
    - ChannelManager:       multi-channel lifecycle + health
    - run.py:               CLI entry ``python -m bot.run --channels telegram,feishu``
"""

from .base import Channel, chunk_text, DedupCache, RateLimiter, TypingManager
from .capabilities import ChannelCapabilities
from .config import BaseChannelConfig

# Channel registry: maps channel name → (module_path, class_name)
# Channels are lazy-imported to avoid pulling in platform SDKs unless needed.
CHANNEL_REGISTRY: dict[str, tuple[str, str]] = {
    "telegram": ("bot.channels.telegram",  "TelegramChannel"),
    "feishu":   ("bot.channels.feishu",    "FeishuChannel"),
    "dingtalk": ("bot.channels.dingtalk",  "DingTalkChannel"),
    "discord":  ("bot.channels.discord",   "DiscordChannel"),
    "slack":    ("bot.channels.slack",     "SlackChannel"),
    "wechat":   ("bot.channels.wechat",    "WeChatChannel"),
    "qq":       ("bot.channels.qq",        "QQChannel"),
    "email":    ("bot.channels.email",     "EmailChannel"),
    "imessage": ("bot.channels.imessage",  "IMessageChannel"),
}


def get_channel_class(name: str) -> type:
    """Dynamically import and return a Channel subclass by name.

    Raises:
        KeyError: If the channel name is not registered.
        ImportError: If the channel module cannot be imported.
    """
    if name not in CHANNEL_REGISTRY:
        raise KeyError(
            f"Unknown channel: {name!r}. "
            f"Available: {', '.join(sorted(CHANNEL_REGISTRY))}"
        )
    module_path, class_name = CHANNEL_REGISTRY[name]
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


__all__ = [
    # Core abstractions
    "Channel",
    "ChannelCapabilities",
    "BaseChannelConfig",
    # Registry
    "CHANNEL_REGISTRY",
    "get_channel_class",
    # Utilities
    "chunk_text",
    "DedupCache",
    "RateLimiter",
    "TypingManager",
]
