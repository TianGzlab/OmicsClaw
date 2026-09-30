"""Who gets in, and whether the reply was taken.

Plan 0031 task A, decision Q23. Three surfaces — channel, desktop, CLI —
share exactly two questions at their edge: *is this sender allowed to
drive the agent*, and *did the message we sent back actually land*. Both
were answered by ``omicsclaw/control/``, which this rebuild deletes.
This module is that half of it, and only that half.

**The names are deliberately the old ones.** ``telegram.py:20`` and
``feishu.py:21`` import ``ChannelSurfaceBinding`` today;
``desktop/turn_submission.py:30`` imports ``RawInboundV1`` and
``RawContentBlockV1``. :class:`InboundMessage` stands where
``RawInboundV1`` stood and :class:`Acceptance` where
``DeliveryAttemptOutcome`` stood, because the reconnection is meant to
be a changed import path rather than thirteen small acts of translation.
Keeping a vocabulary three call sites already speak is not the same as
keeping the architecture that coined it.

**What was not brought across, and why it matters more than what was.**
``ControlRuntimePorts`` had twenty-two fields; five of them were a bare
:data:`~typing.Any` and a sixth was ``dict[str, Any] | None``. It is the
shape the owner's "high cohesion, low coupling" instruction was aimed at,
and the same shape plan 0030 already cut down once in
``ContextAssemblyRequest``. So: **no field in this module mentions**
:data:`~typing.Any` **at all**. :attr:`InboundMessage.values` is
``Mapping[str, object]``, which is what ``Any`` was being used to avoid
saying — a caller that puts something in gets ``object`` back and has to
admit it is narrowing.

**Both classes fail closed, and that is the whole of their value.** A
sender allowlist is not a feature that can be added later without
regression, because the regression is silent: a surface with no policy
does not look broken, it looks like anybody may drive the agent. So
:class:`SenderPolicy` has no default allowlist — omitting it is a
:exc:`TypeError` — and an empty one is refused at construction rather
than quietly admitting nobody.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "Acceptance",
    "DeliveryResult",
    "GROUP_CHAT_TYPES",
    "InboundMessage",
    "SenderPolicy",
    "VALUE_CHAT_TYPE",
    "VALUE_MENTIONS",
    "parse_senders",
]

_EMPTY_VALUES: Mapping[str, object] = MappingProxyType({})

VALUE_CHAT_TYPE = "chat_type"
"""Key under which :attr:`InboundMessage.values` carries the chat kind.

``InboundMessage`` has no ``is_group`` field: plan 0031 §3.2 froze its
six fields (``:352-358``) before Q23's group-chat rule was written down,
and widening a frozen contract while two other lanes build against it is
worse than one documented key. A surface that cannot say which chat a
message came from is a surface :meth:`SenderPolicy.admits` refuses in a
group.
"""

VALUE_MENTIONS = "mentions"
"""Key holding the identities a group message @-mentioned.

Any iterable of strings. ``feishu`` gives a list of ``open_id``; the
attribution question is the same on every platform that has groups.
"""

GROUP_CHAT_TYPES = frozenset({"group", "supergroup", "channel"})
"""Chat kinds where being addressed has to be proven, not assumed.

Telegram spells a group ``group`` / ``supergroup`` / ``channel`` and a
private chat ``private``; Feishu spells them ``group`` and ``p2p``. The
set names what needs proof, so an unfamiliar spelling is treated as a
direct message and falls back to the allowlist alone — the sender check
never stops applying.
"""


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """One thing a human said, before anything has been decided about it.

    Frozen: it crosses a task boundary, and a surface that could edit a
    message after submitting it would be editing what a running turn was
    admitted on.
    """

    text: str
    """What was said. Plain text; this layer has no content parts, which
    is why the channel photo path is out of scope (plan 0031 §5.3)."""

    session_id: str
    """Which conversation this continues. A surface decides how a chat
    maps to a session; this layer only requires that the mapping is
    stable, because it is what history is keyed by."""

    source_request_id: str
    """Idempotency key, and the reason this field is not optional.

    The desktop client's published contract declares
    ``source_request_id_required`` and ``durable_ingress_idempotency``
    (plan 0031 Q24), which together mean a redelivery of the *same* id
    must resolve to the *same* turn rather than start a second one. A
    default would make "the surface forgot" indistinguishable from "this
    is genuinely new", and the failure only shows up as a duplicated
    answer under a retry — the condition nobody reproduces on purpose."""

    sender: str = ""
    """Platform identity of whoever spoke, as
    :class:`SenderPolicy` spells it — a Feishu ``open_id``, a Telegram
    numeric id as text. ``""`` is *unidentified*, and an allowlist never
    contains it."""

    surface: str = ""
    """Which edge this arrived at — ``"telegram"``, ``"desktop"``,
    ``"cli"``. For attribution in logs and for a surface that multiplexes
    several transports; nothing routes on it."""

    values: Mapping[str, object] = field(default_factory=lambda: _EMPTY_VALUES)
    """Turn-level facts the surface knows and this layer does not.

    Reaches the tools through ``ToolContext.values``, which is what a
    tool reads with :func:`~omicsclaw.tools.context_value`. Typed
    ``object`` rather than ``Any`` on purpose — see the module docstring.
    """


def parse_senders(raw: str) -> frozenset[str]:
    """Split a comma-separated allowlist, the spelling ``.env`` uses.

    ``FEISHU_ALLOWED_SENDERS`` holds comma-separated owner ``open_id``
    values. Blanks are dropped and
    entries are stripped, so a trailing comma does not add an empty
    identity — which would otherwise admit every message whose sender the
    platform failed to report.

    Deliberately **not** reading the variable itself: plan 0031 Q8 leaves
    :func:`~omicsclaw.entry.config.resolve_app_config` the only function
    *in this package* that interprets a deployment, and a policy built
    from a string it was handed is one a test can describe in full. The
    stronger reading —— that it is the only function in the program that
    reads a process global —— was never true and is enumerated in
    ``tests/launch/test_the_environment_is_read_in_known_places.py``.
    """
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True, slots=True)
class SenderPolicy:
    """Who may drive this agent. Deny by default, and deny loudly.

    The rule this class is: ``FEISHU_ALLOWED_SENDERS`` is *required* —
    authoritative Feishu ingress admits nobody else and refuses to start
    without it — and group chats fail closed without
    ``FEISHU_BOT_OPEN_ID``.

    Both halves are enforced here rather than in an adapter, because
    seven adapters means seven chances to forget one.
    """

    allowed_senders: frozenset[str]
    """No default. Constructing a policy is the act of naming the owners,
    and a keyword a caller can omit is a keyword a caller will omit."""

    bot_identity: str = ""
    """This bot's own platform id, used to prove a group @-mention was
    aimed here. Empty is allowed — a deployment with no group chats does
    not need one — and it is precisely what makes every group message
    fail :meth:`admits`."""

    def __post_init__(self) -> None:
        """Refuse an empty allowlist at construction, not at first message.

        An empty :class:`frozenset` would already be fail-closed: nobody
        matches, nothing runs. That is the problem. A bot that admits
        nobody looks exactly like a bot nobody has messaged, so an
        unset ``FEISHU_ALLOWED_SENDERS`` parsed to ``frozenset()`` would
        be discovered days later. "Refuses to start" is what the contract
        says, and this is where starting fails.
        """
        if not self.allowed_senders:
            raise ValueError(
                "SenderPolicy needs at least one allowed sender; an empty "
                "allowlist admits nobody, which is indistinguishable from "
                "a bot nobody has messaged"
            )

    def admits(self, msg: InboundMessage) -> bool:
        """Whether *msg* may start a turn. Two gates, both closed by default.

        1. :attr:`InboundMessage.sender` is in :attr:`allowed_senders`.
           An empty sender never is.
        2. If the message came from a group (see :data:`GROUP_CHAT_TYPES`),
           this bot must be among the identities it @-mentioned, and
           :attr:`bot_identity` must be set to know which those are.
           Without that, a group message that mentions *some other*
           participant would be read as addressed to this agent.

        The second gate reads :data:`VALUE_CHAT_TYPE` and
        :data:`VALUE_MENTIONS` out of :attr:`InboundMessage.values`
        because the frozen field list has nowhere else to put them; see
        those constants. A surface that reports neither is treated as a
        direct message, which is the safe reading — gate 1 still applies,
        and a surface *with* groups that forgets to report the chat type
        is the case gate 2 is written to catch when it does report it.

        Returns a plain :class:`bool` rather than raising: refusal is an
        ordinary outcome at an ingress that faces the open internet, and
        the caller's obligation is to create no turn — not to answer.
        """
        if not msg.sender or msg.sender not in self.allowed_senders:
            return False

        chat_type = msg.values.get(VALUE_CHAT_TYPE)
        if not isinstance(chat_type, str) or chat_type not in GROUP_CHAT_TYPES:
            return True

        if not self.bot_identity:
            return False

        mentions = msg.values.get(VALUE_MENTIONS)
        # A bare ``str`` is excluded by the tuple below on purpose: it is
        # iterable, so a surface reporting one identity as a plain string
        # would otherwise be matched character by character.
        if isinstance(mentions, (list, tuple, set, frozenset)):
            return self.bot_identity in set(mentions)
        return False


class Acceptance(StrEnum):
    """Whether a message this agent sent out was taken by the platform.

    Three states, not two, and the third is the one that carries the
    engineering. ``telegram_delivery.py:161-164`` says it in its own
    words: "The Pump must not retry blindly."
    """

    ACCEPTED = "accepted"
    """The platform took it. Do not send it again."""

    REJECTED = "rejected"
    """The platform refused it and said so. Retrying is meaningful only
    if :attr:`DeliveryResult.retry_after` says when."""

    UNKNOWN = "unknown"
    """The attempt ended without an answer — a timeout, a dropped
    connection, a 5xx. The message may or may not have been delivered,
    so a resend may duplicate it. Anything retrying an ``UNKNOWN`` needs
    an idempotency key at the far end; it does not get one for free."""


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """The outcome of one attempt to put a message in front of a human."""

    acceptance: Acceptance
    """See :class:`Acceptance`; ``UNKNOWN`` is not a softer ``REJECTED``."""

    retry_after: float | None = None
    """Seconds the platform asked us to wait, when it said.

    ``None`` means *it did not say*, which is not the same as *zero*.
    A caller that reads a missing value as "retry now" turns one rate
    limit into a tighter loop against the thing that just rate-limited
    it."""
