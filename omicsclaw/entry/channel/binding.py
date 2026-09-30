"""What one channel adapter contributes to the shared channel runtime.

``telegram.py:20`` and ``feishu.py:21`` each import exactly one symbol from
the deleted control plane, and it is this one. Plan 0031 §5.3 measured the
whole reconnection of both production adapters at thirteen lines because of
that: 1,518 lines of shipped code were missing a name, not a design.

**The name is kept and the fields are translated** (plan 0031 Q23). Three of
the five cross unchanged — :attr:`adapter`, :attr:`account_namespace`,
:attr:`delivery_adapter`. The fourth, ``owner_identities: Mapping[str,
frozenset[str]]``, was a durable identity-scope table keyed
``channel/<adapter>/<account>/<subject kind>``; there is no durable identity
table in this rebuild, and the question that table was answering — *may this
person drive the agent* — is :class:`~omicsclaw.entry.ingress.SenderPolicy`'s.
So the field becomes one, and it has **no default**: a binding is the act of
naming the owners, and authoritative ingress admits nobody else and refuses
to start without it.

**The fifth is refused rather than translated.** ``attachment_input_enabled``
declared that a platform's inbound photos had somewhere to go. They do not:
:class:`~omicsclaw.schema.Message` carries ``content: str`` and no
content parts (``omicsclaw/schema/message.py:178-179``), so
plan 0031 §5.3 discards the photo path outright. The field is kept and pinned
to ``False`` instead of deleted, because a binding is where a future
attachment cutover would announce itself, and a silently-ignored ``True``
would look like support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from omicsclaw.entry.ingress import SenderPolicy

from .delivery import DeliveryAdapter

__all__ = ["DEFAULT_TEXT_CHUNK_LIMIT", "ChannelSurfaceBinding"]

DEFAULT_TEXT_CHUNK_LIMIT: Final = 4096
"""Characters per outbound message when a binding does not say.

``BaseChannelConfig.text_chunk_limit`` (``config.py:22``), unchanged. Every
adapter that cares overrides it from its own
:class:`~omicsclaw.entry.channel.capabilities.ChannelCapabilities` — Telegram
and Feishu both declare 4,000 against hard limits of 4,096.
"""


@dataclass(frozen=True, slots=True)
class ChannelSurfaceBinding:
    """One adapter's account, its owners, and the way out to that account.

    Built by :meth:`~omicsclaw.entry.channel.base.Channel
    .prepare_control_binding` during phase 1 of startup and handed to
    :meth:`~omicsclaw.entry.channel.runtime.ChannelRuntime
    .for_channel_surfaces`, which composes one runtime over all of them. A
    channel never composes its own: several adapters in one process share one
    agent, and two runtimes would be two views of one deployment's sessions.
    """

    adapter: str
    """Platform name — ``"telegram"``, ``"feishu"``. Matches
    :attr:`~omicsclaw.entry.ingress.InboundMessage.surface`, which is how an
    inbound message finds the binding that admitted it."""

    account_namespace: str
    """Which account of that platform this is: a Telegram ``bot-<id>``, a
    Feishu App ID. Authenticated rather than configured — both adapters read
    it back from the provider — so one process serving two bots cannot deliver
    one bot's reply through the other's token."""

    sender_policy: SenderPolicy
    """Who may drive the agent through this account, and this bot's own
    identity for proving a group @-mention.

    No default. Omitting it is a :exc:`TypeError` at construction, which is
    where "refuses to start without it" has to happen: a binding that admitted
    everyone would not look broken, it would look like a popular bot.
    """

    delivery_adapter: DeliveryAdapter
    """The single-attempt sender for this account. Called once per chunk by
    :func:`~omicsclaw.entry.channel.delivery.deliver`, which owns retry."""

    text_chunk_limit: int = DEFAULT_TEXT_CHUNK_LIMIT
    """Longest single message this account will accept, in characters.

    The one field with no counterpart in the deleted binding, and it is here
    because the runtime sends replies and the *channel* is what knows the
    platform's limit (``ChannelCapabilities.max_text_length``). The old
    control plane did not need it: it chunked nowhere and its adapters were
    handed pre-chunked items by a durable outbox this step does not have.

    Must exceed 20. That is not a sanity bound but the width of the code
    fence :func:`~omicsclaw.entry.channel.base.chunk_text` reserves: at or
    below it the per-chunk budget goes non-positive and the chunker never
    advances. An adapter whose platform declares "no practical limit" — the
    email capability profile says ``0`` — must name a real number here.
    """

    attachment_input_enabled: bool = False
    """Inbound attachments. Must be ``False``; see the module docstring."""

    def __post_init__(self) -> None:
        """Refuse a binding that cannot be acted on, at composition time.

        Every check here fails a start-up rather than a message. A runtime
        composed over a nameless account or an uncallable sender would fail
        on the first real message instead, which on an IM surface means the
        first person to say hello is the smoke test.
        """
        adapter = self.adapter.strip() if isinstance(self.adapter, str) else ""
        account = (
            self.account_namespace.strip()
            if isinstance(self.account_namespace, str)
            else ""
        )
        if not adapter or not account:
            raise ValueError("Channel adapter and account_namespace must be non-empty")
        object.__setattr__(self, "adapter", adapter)
        object.__setattr__(self, "account_namespace", account)
        if not isinstance(self.sender_policy, SenderPolicy):
            raise TypeError(
                "sender_policy must be a SenderPolicy; it is the allowlist "
                "this account admits and it has no default"
            )
        if not callable(self.delivery_adapter):
            raise TypeError("delivery_adapter must be callable")
        if not isinstance(self.text_chunk_limit, int) or self.text_chunk_limit <= 20:
            raise ValueError(
                "text_chunk_limit must exceed the 20 characters chunk_text() "
                "reserves for code fences; at or below it the chunker loops "
                "forever, synchronously, and stops the whole process"
            )
        if self.attachment_input_enabled:
            raise ValueError(
                "attachment_input_enabled must be False: this layer has no "
                "content parts, so an attachment would be dropped silently"
            )

    @property
    def account_key(self) -> tuple[str, str]:
        """``(adapter, account_namespace)``, reserved for multiple accounts.

        **Not how bindings are indexed today.**
        :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime` keys on
        :attr:`adapter` alone (``runtime.py:281-289``) and refuses two
        bindings claiming one adapter outright, because an inbound message
        names its surface by adapter and nothing else — so a second Feishu
        app in the same process is a second process, not a second key.

        Kept because the pair is what a runtime would index on the day an
        :class:`~omicsclaw.entry.ingress.InboundMessage` can say which
        account it arrived at. Nothing in this package calls it.
        """
        return (self.adapter, self.account_namespace)
