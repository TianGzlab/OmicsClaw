"""What the cut-over conformance suite needs in order to drive one adapter.

Seven adapters answer seven platforms, and the thing that keeps them
consistent is a shared **test**, not a shared base class: a template method
over seven transport lifecycles, three attribution models and four different
mandatory outbound parameters is how a package grows a ``**kwargs`` and an
``if self.name ==``.

So each platform describes itself here, in its own test module, and
:mod:`tests.entry.test_channel_cutover_conformance` walks the registry and
holds every description to the same nine rules. An adapter that declares
``authoritative_ingress`` without registering a fixture fails the suite,
which is the point: an eighth adapter has to turn this red before it can
be born.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from omicsclaw.entry.channel.delivery import (
    DeliveryAdapter,
    DeliveryAttemptOutcome,
)

__all__ = [
    "DEFAULT_OWNER",
    "DEFAULT_STRANGER",
    "FIXTURES",
    "MENTION_GUARDED_ADAPTERS",
    "MENTION_PROBE",
    "ChannelFixture",
    "DeliveryCase",
    "MentionGuard",
    "SentCall",
    "register",
]

MENTION_PROBE = (
    '<!channel> <!here> @everyone <at user_id="all"></at> a & b < c > d'
)
"""Text that notifies a whole room on at least one platform when sent as written.

``<!channel>`` and ``<!here>`` are Slack's, ``@everyone`` is Discord's and
the ``<at>`` element is Feishu's. ``a & b < c > d`` carries the three
characters Slack reads as markup, so an escape that forgot one of them, or
applied itself twice, shows up in the payload.
"""

DEFAULT_OWNER = "ou_owner"
"""The sender id the suite speaks with unless a fixture names its own.

On most platforms an owner id is an opaque token, so one arbitrary string is
as good as another and this is the one the rest of the channel tests use.
Email is the exception: an address is checked as an address.
"""

DEFAULT_STRANGER = "conformance_stranger"
"""A sender no fixture's allowlist may contain."""


@dataclass(frozen=True)
class DeliveryCase:
    """One provider failure and the acceptance it must be classified as.

    Three of these are mandatory for every adapter and are named in
    :data:`REQUIRED_DELIVERY_CASES`: a call that timed out, a call that
    raised something nobody anticipated, and a rate limit the platform
    actually named. The first two are ambiguous — the message may be in
    front of the person already — and only the third may be retried.
    """

    label: str
    adapter: DeliveryAdapter
    expected: DeliveryAttemptOutcome


@dataclass(frozen=True)
class SentCall:
    """One provider call, reduced to the two facts a mention depends on."""

    text: str
    """The message text exactly as the provider was handed it."""

    notifies: bool
    """Whether the platform is left free to notify whoever *text* mentions.

    ``False`` only when the call itself told the platform to notify nobody,
    as Discord's ``allowed_mentions`` does. A platform with no such switch
    reports ``True`` on every call, and its text then has to be inert."""


@dataclass(frozen=True)
class MentionGuard:
    """What rule 9 needs to hold one platform to "no reply notifies anybody"."""

    live_spellings: tuple[str, ...]
    """Every substring of :data:`MENTION_PROBE` that notifies somebody on this
    platform when it reaches the provider as written."""

    accepting_delivery: Callable[[], tuple[DeliveryAdapter, list[SentCall]]]
    """A delivery adapter whose platform accepts everything, and the list its
    double appends one :class:`SentCall` to per provider call."""


@dataclass(frozen=True)
class ChannelFixture:
    """One platform, described well enough to be held to the nine rules.

    Every callable here builds fresh state, because the conformance suite
    runs each rule against its own channel: a fixture that returned one
    shared adapter would let rule 5's refusal be observed on an object rule
    3 had already driven.
    """

    name: str
    """Must equal the adapter's ``Channel.name`` and its registry key."""

    new_channel: Callable[[], Any]
    """Build the adapter with platform doubles attached, ready for
    ``prepare_control_binding()`` and with no network behind it."""

    reply_target: Callable[[Any], Mapping[str, Any]]
    """The target this adapter's inbound path builds for a given channel.

    Must come from :func:`omicsclaw.entry.channel.reply_target.build`: rule
    4 sends it through this platform's own delivery adapter, which is the
    only check that the two halves of the target agree."""

    accepting_delivery: Callable[[], tuple[DeliveryAdapter, list[str]]]
    """A delivery adapter whose platform accepts everything, and the list
    the double appends each accepted body to — so rule 8 can read what the
    platform was actually handed rather than what we hoped."""

    delivery_cases: Callable[[], Sequence[DeliveryCase]]
    """Every case rule 3 requires of this platform — see
    :data:`REQUIRED_DELIVERY_CASES` and :attr:`has_retryable_refusal`."""

    submit: Callable[..., Awaitable[None]]
    """``async (channel, *, text, sender, group, mentions_bot) -> None``.

    Drives the adapter's **real** inbound entry point exactly as its SDK
    would — on a thread where the SDK uses a thread. A fixture that called
    the submission helper directly would skip the gates being tested."""

    direct_replies: Callable[[Any, Any], list[str]]
    """``(channel, transport) -> list[str]``: what the adapter sent back
    outside an exchange. Command output travels this way on every platform,
    but not always through the same object, so the fixture says where."""

    has_groups: bool
    """Whether the platform has group chats at all. ``False`` changes what
    rule 6 asserts; it never switches it off."""

    strips_markdown: bool
    """Whether this platform's delivery adapter must reduce Markdown to
    plain text before the provider call, because the platform renders none."""

    unregistered_commands_reach_the_agent: bool
    """Whether an unregistered ``/verb`` is ordinary text here.

    ``True`` for the adapters that detect commands by text prefix. ``False``
    for Telegram, where the platform routes only the verbs registered with
    it and an unknown one reaches no handler at all — so rule 7 proves it is
    not vacuous with ordinary text instead."""

    owner: str = DEFAULT_OWNER
    """The identity this platform's allowlist admits, in its own spelling."""

    stranger: str = DEFAULT_STRANGER
    """An identity it must not admit, in the same spelling."""

    has_retryable_refusal: bool = True
    """Whether this platform can refuse in a way that is safe to repeat.

    ``False`` only where the protocol itself has no such answer: SMTP names
    no interval to come back after, so an email adapter has nothing it may
    classify as retryable and rule 3 holds it to exactly that. Declared
    rather than inferred, so that an adapter which simply forgot to
    classify a rate limit cannot pass by supplying no case for it.
    """

    mention_guard: MentionGuard | None = None
    """How this platform keeps model-written text from notifying anybody.

    ``None`` for a platform whose delivery adapter does not neutralise
    mentions yet. Which platforms must declare one is pinned by
    :data:`MENTION_GUARDED_ADAPTERS`, so that dropping a guard fails the
    suite instead of silently skipping rule 9.
    """


REQUIRED_DELIVERY_CASES = ("timeout", "unknown")
"""The two classifications every adapter must get right, whatever it speaks.

Named rather than counted so a fixture cannot satisfy rule 3 by supplying
two copies of the easy one. A platform that can refuse safely-repeatably
owes a third, ``"rate_limited"`` — see
:attr:`ChannelFixture.has_retryable_refusal`.
"""

RETRYABLE_DELIVERY_CASE = "rate_limited"
"""The label of the one case that may be classified retryable."""

MENTION_GUARDED_ADAPTERS = frozenset({"discord", "feishu", "slack"})
"""The adapters whose delivery must neutralise mentions in every outbound text.

Each of these platforms turns some spelling in a plain message into a
notification for a whole room. Telegram's plain text has no such
spelling, although ``@username`` in it does notify that one person;
Email has no mentions at all. DingTalk and QQ are not covered yet.
"""


FIXTURES: dict[str, ChannelFixture] = {}
"""Fixture by adapter name, filled at import time by each platform's tests."""


def register(fixture: ChannelFixture) -> ChannelFixture:
    """Publish *fixture* to the conformance suite.

    Re-registering a name is a programming error rather than a silent
    overwrite: two fixtures for one adapter means one of them is never run,
    and the one that is never run is the one that would have failed.
    """
    if fixture.name in FIXTURES:
        raise ValueError(f"a conformance fixture for {fixture.name!r} already exists")
    FIXTURES[fixture.name] = fixture
    return fixture
