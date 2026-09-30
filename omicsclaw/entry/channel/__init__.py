"""OmicsClaw's instant-messaging surface: seven platforms, one agent.

The first real consumer of :mod:`omicsclaw.entry` — a contract that only a
reference consumer has exercised has not been exercised.

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
cannot be built without one. Authoritative ingress admits nobody else and
refuses to start without it, and group chats fail closed without a bot
identity to attribute an @-mention to.

*One way in and one way out.* A message becomes an exchange through
:meth:`~omicsclaw.entry.channel.base.Channel.inbound` and
:meth:`~omicsclaw.entry.channel.runtime.ChannelRuntime.submit`; the answer
leaves through that runtime's delivery pump, which is the only thing that
classifies whether a send was accepted. No adapter has a ``send`` of its own
and no base class offers one.

**What holds seven similar adapters together is a test, not a base class.**
``tests/entry/test_channel_cutover_conformance.py`` walks this registry and
holds every adapter declaring ``authoritative_ingress`` to the same eight
rules — the places where similar implementations diverge *silently*: a reply
target whose two halves disagree, a timeout classified as retryable, a group
gate that is always open, a slash command that reaches the model, a Markdown
asterisk in a client that renders none. Only three things are shared as
**code**: :mod:`.reply_target`, the chunk-limit guard on
:class:`~omicsclaw.entry.channel.binding.ChannelSurfaceBinding`, and
:meth:`~omicsclaw.entry.channel.base.Channel.command_context`.

**No optional dependency is imported here.** Every platform SDK is imported
inside the method that first needs a client, in plainly visible syntax, so
importing this package costs none of them and ``oc channel -- --list`` can
read a class attribute off all seven without installing anything.
:func:`get_channel_class` keeps the adapter modules themselves lazy for the
same reason.
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
    compose_channel_runtime,
)

CHANNEL_REGISTRY: dict[str, tuple[str, str]] = {
    "telegram": ("omicsclaw.entry.channel.telegram", "TelegramChannel"),
    "feishu": ("omicsclaw.entry.channel.feishu", "FeishuChannel"),
    "dingtalk": ("omicsclaw.entry.channel.dingtalk", "DingTalkChannel"),
    "discord": ("omicsclaw.entry.channel.discord", "DiscordChannel"),
    "slack": ("omicsclaw.entry.channel.slack", "SlackChannel"),
    "qq": ("omicsclaw.entry.channel.qq", "QQChannel"),
    "email": ("omicsclaw.entry.channel.email", "EmailChannel"),
}
"""Channel name to ``(module, class)``.

Every name in this table can be started —
"registered but unable to start" is a state that no longer exists here, and
``Channel.require_authoritative_ingress`` is the gate that says so.
"""


def get_channel_class(name: str) -> type:
    """Import and return a Channel subclass by name.

    Lazy on purpose, and the reason survives the port: a platform SDK is an
    optional dependency, and resolving all seven names eagerly would make
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
    "compose_channel_runtime",
    "deliver",
    "dispatch",
    "get_channel_class",
    "registered_commands",
]
