"""OmicsClaw's instant-messaging surface: nine platforms, one agent.

Plan 0031 task D1, and the first real consumer of :mod:`omicsclaw.entry` — a
contract that only a reference consumer has exercised has not been exercised.

**This package is a port.** ``omicsclaw/surfaces/channels/`` is its input, not
its predecessor: 7,059 lines that were measured as coupled to the deleted
packages at thirteen lines, all of them in the two production adapters and all
of them one missing symbol
(:class:`~omicsclaw.entry.channel.binding.ChannelSurfaceBinding`). What is new
here is :mod:`.binding`, :mod:`.delivery` and :mod:`.runtime`, which are that
symbol and the two things it names.

**The shape of a deployment**::

    app = attach_sessions(await open_app(resolve_app_config(argv, env)))
    channel = TelegramChannel(TelegramConfig(bot_token=..., ...))
    manager = ChannelManager()
    manager.register(channel)
    runtime = await compose_channel_runtime(app, manager.channels.values())
    await manager.start_all()      # opens every channel's ingress at once

Three properties of that arrangement are load-bearing:

*One runtime per process.* Several channels share one
:class:`~omicsclaw.entry.session.SessionRegistry`, because two registries
would be two sets of conversations for one person.

*Ingress opens last, and for everyone at once.* A message arriving mid
start-up would otherwise reach a runtime that cannot run it.

*Nobody gets in without an allowlist.*
:class:`~omicsclaw.entry.ingress.SenderPolicy` has no default and a binding
cannot be built without one. ``CLAUDE.md``: authoritative ingress "admits
nobody else and refuses to start without it", and group chats "fail closed"
without a bot identity to attribute an @-mention to.

**What is verified and what is only moved.** Plan 0031 §5.3 accepts Telegram
and Feishu; the other seven adapters (WeChat/WeCom, Email, iMessage, DingTalk,
QQ, Slack, Discord) were moved with no changes beyond line lengths, are not
tested here, and **are not claimed to work** — they are also gated at start-up
by :meth:`~omicsclaw.entry.channel.base.Channel.require_authoritative_ingress`,
which refuses any adapter that has not declared the cutover.

**No optional dependency is imported here.** ``python-telegram-bot`` and
``lark-oapi`` are imported inside the factory that needs them, in plainly
visible syntax, so importing this package costs neither (plan 0031 trap 13).
:func:`get_channel_class` keeps the adapter modules themselves lazy for the
same reason the ported registry did.
"""

from .base import Channel, DedupCache, RateLimiter, TypingManager, chunk_text
from .binding import ChannelSurfaceBinding
from .capabilities import ChannelCapabilities
from .commands import SlashCommandContext, dispatch, registered_commands
from .config import BaseChannelConfig
from .delivery import (
    DeliveryAdapter,
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
    deliver,
)
from .manager import ChannelHealth, ChannelManager
from .runtime import (
    ChannelRuntime,
    ChannelSubmission,
    TurnAcceptanceResult,
    TurnAcceptanceStatus,
    VALUE_REPLY_TARGET,
    collect_reply,
    compose_channel_runtime,
)

CHANNEL_REGISTRY: dict[str, tuple[str, str]] = {
    "telegram": ("omicsclaw.entry.channel.telegram", "TelegramChannel"),
    "feishu": ("omicsclaw.entry.channel.feishu", "FeishuChannel"),
    "dingtalk": ("omicsclaw.entry.channel.dingtalk", "DingTalkChannel"),
    "discord": ("omicsclaw.entry.channel.discord", "DiscordChannel"),
    "slack": ("omicsclaw.entry.channel.slack", "SlackChannel"),
    "wechat": ("omicsclaw.entry.channel.wechat", "WeChatChannel"),
    "qq": ("omicsclaw.entry.channel.qq", "QQChannel"),
    "email": ("omicsclaw.entry.channel.email", "EmailChannel"),
    "imessage": ("omicsclaw.entry.channel.imessage", "IMessageChannel"),
}
"""Channel name to ``(module, class)``.

Nine names for ten platforms: WeChat and WeCom share one adapter and one
file. Only the first two are verified by plan 0031 task D1.
"""


def get_channel_class(name: str) -> type:
    """Import and return a Channel subclass by name.

    Lazy on purpose, and the reason survives the port: a platform SDK is an
    optional dependency, and resolving all nine names eagerly would make
    ``pip install lark-oapi`` a requirement for running a Telegram bot.

    Raises:
        KeyError: the channel name is not registered.
        ImportError: the module is registered but cannot be imported, which
            on this machine means its SDK is not installed.
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
    "CHANNEL_REGISTRY",
    "BaseChannelConfig",
    "Channel",
    "ChannelCapabilities",
    "ChannelHealth",
    "ChannelManager",
    "ChannelRuntime",
    "ChannelSubmission",
    "ChannelSurfaceBinding",
    "DedupCache",
    "DeliveryAdapter",
    "DeliveryAdapterResult",
    "DeliveryAttemptOutcome",
    "DeliveryAttemptRequest",
    "RateLimiter",
    "SlashCommandContext",
    "TurnAcceptanceResult",
    "TurnAcceptanceStatus",
    "TypingManager",
    "VALUE_REPLY_TARGET",
    "chunk_text",
    "collect_reply",
    "compose_channel_runtime",
    "deliver",
    "dispatch",
    "get_channel_class",
    "registered_commands",
]
