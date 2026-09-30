"""Where a channel reply goes: built once, validated once.

An inbound handler builds a reply target; the platform's delivery adapter
reads it back several layers later, in another module, after the exchange has
run. The two halves must agree on the same four key names, and a disagreement
between them is **silent**: the delivery adapter rejects the target as
malformed, the reply pump logs one warning and stops sending the rest of the
answer, and the person sees a bot that went quiet mid-sentence. Constructing
and validating in one module is what makes that disagreement impossible
instead of merely unlikely.

Four keys are common to every platform — ``schema_version``, ``kind``,
``adapter`` and ``destination_id`` — and they are all this module knows.
Everything a single platform needs on top (a Telegram ``thread_id``, a Slack
``thread_ts``, a QQ ``msg_id``, an email ``subject``) travels as an extra and
is read by that platform's adapter alone.
"""

from __future__ import annotations

from typing import Any, Final, Mapping

from .delivery import DeliveryAttemptRequest

__all__ = [
    "REPLY_TARGET_SCHEMA_VERSION",
    "InvalidReplyTarget",
    "build",
    "read",
]

REPLY_TARGET_SCHEMA_VERSION: Final = 1
"""Version stamped into every target this module builds.

A target outlives the handler that made it: it is carried on the inbound
message, held for the length of the exchange, and read by the delivery
adapter afterwards. The stamp is what lets a future change to the common
keys be told apart from a target built by an older build of this process.
"""

_KIND: Final = "channel"


class InvalidReplyTarget(ValueError):
    """The target does not name a destination this adapter can send to.

    Raised by :func:`read`, and caught by the calling delivery adapter, which
    turns it into a permanent rejection: a target that cannot be addressed
    never reached the platform, so there is nothing ambiguous about it.
    """


def build(
    adapter: str,
    account_namespace: str,
    destination_id: str,
    /,
    **extras: object,
) -> dict[str, Any]:
    """The only place an inbound handler builds a reply target.

    *extras* are that platform's own keys; this function neither knows nor
    validates them. An extra whose value is ``None`` is dropped rather than
    stored, so a handler can pass an optional field unconditionally without
    putting a null into a mapping the delivery adapter has to re-check.

    The three common fields are positional-only so that a platform key which
    happens to be spelled like one of them is refused rather than silently
    binding to the parameter — an ``adapter`` extra that overwrote the
    adapter name would route one platform's reply through another's token.

    Raises:
        InvalidReplyTarget: *adapter* or *destination_id* is empty, or an
            extra collides with one of the four common keys.
    """
    adapter_name = str(adapter).strip()
    destination = str(destination_id).strip()
    if not adapter_name:
        raise InvalidReplyTarget("a reply target must name its adapter")
    if not destination:
        raise InvalidReplyTarget("a reply target must name a destination_id")
    target: dict[str, Any] = {
        "schema_version": REPLY_TARGET_SCHEMA_VERSION,
        "kind": _KIND,
        "adapter": adapter_name,
        "account_namespace": str(account_namespace).strip(),
        "destination_id": destination,
    }
    for key, value in extras.items():
        if key in target:
            raise InvalidReplyTarget(f"{key!r} is a common key and cannot be an extra")
        if value is None:
            continue
        target[key] = value
    return target


def read(
    request: DeliveryAttemptRequest,
    *,
    adapter: str,
) -> Mapping[str, Any]:
    """The only place a delivery adapter validates a reply target.

    Checks the four common fields and the text there is to send, then hands
    the whole mapping back so the caller can take its own extras out of it.

    ``kind`` and ``adapter`` are checked only when present: a target built
    before this module existed carries neither, and defaulting them to
    "matches" keeps such a target addressable rather than turning an upgrade
    into a wave of undeliverable replies.

    Raises:
        InvalidReplyTarget: any of the four fields is missing, of the wrong
            shape, or names a different adapter; or there is no text to send.
    """
    target = request.reply_target
    if not isinstance(target, Mapping):
        raise InvalidReplyTarget("reply_target must be a mapping")
    if target.get("kind", _KIND) != _KIND:
        raise InvalidReplyTarget(f"reply_target kind must be {_KIND}")
    if target.get("adapter", adapter) != adapter:
        raise InvalidReplyTarget(f"reply_target adapter must be {adapter}")
    destination_id = target.get("destination_id")
    if not isinstance(destination_id, str) or not destination_id:
        raise InvalidReplyTarget("reply_target has no destination_id")
    if not isinstance(request.text, str) or not request.text:
        raise InvalidReplyTarget("delivery item text must be non-empty")
    return target
