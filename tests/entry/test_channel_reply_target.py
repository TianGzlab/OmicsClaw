"""The one piece of knowledge both ends of a reply have to share.

An inbound handler builds a reply target and a delivery adapter validates it
an exchange later, in another module. Everything here is about the failure
that costs the most and shows the least: the two ends disagreeing about a key
name. The adapter answers ``REJECTED_PERMANENT``, the pump logs one warning
and stops, and the person watches a bot go quiet in the middle of an answer.
"""

from __future__ import annotations

import pytest

from omicsclaw.entry.channel import reply_target
from omicsclaw.entry.channel.delivery import DeliveryAttemptRequest
from omicsclaw.entry.channel.reply_target import InvalidReplyTarget


def request(text: str = "hello", **target) -> DeliveryAttemptRequest:
    return DeliveryAttemptRequest(item_id="t-0", text=text, reply_target=target)


def test_a_built_target_carries_the_four_fields_every_adapter_reads():
    target = reply_target.build("slack", "team-T1", "C123", thread_ts="17.5")

    assert target == {
        "schema_version": 1,
        "kind": "channel",
        "adapter": "slack",
        "account_namespace": "team-T1",
        "destination_id": "C123",
        "thread_ts": "17.5",
    }


def test_an_absent_extra_is_dropped_rather_than_stored_as_none():
    """So a handler can pass an optional field unconditionally.

    The alternative is every caller writing the same two-line ``if`` — and
    the one that forgets puts a ``None`` into a mapping the delivery adapter
    then has to re-check.
    """
    target = reply_target.build("telegram", "bot-1", "42", thread_id=None)

    assert "thread_id" not in target


@pytest.mark.parametrize(
    "adapter, destination",
    [("", "42"), ("   ", "42"), ("telegram", ""), ("telegram", "  ")],
)
def test_a_target_that_names_nothing_is_refused_where_it_is_built(
    adapter, destination
):
    """At the handler, which still has the platform event to say why."""
    with pytest.raises(InvalidReplyTarget):
        reply_target.build(adapter, "bot-1", destination)


def test_an_extra_cannot_quietly_overwrite_a_common_field():
    """``adapter`` is how an inbound message finds its way back out."""
    with pytest.raises(InvalidReplyTarget, match="common key"):
        reply_target.build("telegram", "bot-1", "42", adapter="slack")


def test_reading_back_a_built_target_returns_it_whole():
    """The adapter takes its own extras out of what ``read`` hands back."""
    built = reply_target.build("qq", "app-1", "grp", msg_id="m7")

    seen = reply_target.read(request(**built), adapter="qq")

    assert seen["msg_id"] == "m7"
    assert seen["destination_id"] == "grp"


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"kind": "email"}, "kind"),
        ({"adapter": "discord"}, "adapter"),
        ({"destination_id": None}, "destination_id"),
        ({"destination_id": ""}, "destination_id"),
        ({"destination_id": 42}, "destination_id"),
    ],
)
def test_a_target_this_adapter_cannot_address_is_refused(overrides, reason):
    target = reply_target.build("telegram", "bot-1", "42")
    target.update(overrides)

    with pytest.raises(InvalidReplyTarget, match=reason):
        reply_target.read(request(**target), adapter="telegram")


def test_an_empty_body_is_refused_before_a_provider_call():
    """A send of nothing is a wasted call at best and a visible blank at worst."""
    target = reply_target.build("telegram", "bot-1", "42")

    with pytest.raises(InvalidReplyTarget, match="text"):
        reply_target.read(request(text="", **target), adapter="telegram")


def test_a_target_from_before_this_module_is_still_addressable():
    """``kind`` and ``adapter`` are checked only when the target names them.

    A process upgraded mid-conversation must not turn every reply already in
    flight into a permanent rejection.
    """
    seen = reply_target.read(request(destination_id="42"), adapter="telegram")

    assert seen["destination_id"] == "42"
