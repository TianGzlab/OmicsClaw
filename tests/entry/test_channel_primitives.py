"""The small shared objects every adapter uses, on their own.

De-duplication, rate limiting, the capability table, the base config, the
owner gate a slash command passes through, and the manager's health record.
Each is exercised indirectly by an adapter's tests; each is also worth one
direct test, because a defect in any of them shows up as an adapter
misbehaving and is then looked for in the adapter.

These take over what ``tests/test_channels.py`` covered for the package that
``omicsclaw/entry/channel/`` replaced, with one addition the older suite did
not have: the two-step form of the dedup cache, which is the half that stops
a failed submission plus a platform redelivery losing a message in silence.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from omicsclaw.entry.channel.base import Channel, DedupCache, RateLimiter
from omicsclaw.entry.channel.capabilities import (
    DISCORD,
    FEISHU,
    TELEGRAM,
    ChannelCapabilities,
)
from omicsclaw.entry.channel.config import BaseChannelConfig
from omicsclaw.entry.channel.manager import ChannelHealth


# ---- de-duplication ----------------------------------------------------


def test_the_two_step_cache_does_not_record_what_it_is_only_asked_about():
    """The property the one-step form cannot have.

    An ingress checks, submits, and records only if the submission was
    accepted. Recording on the check instead loses the message whenever the
    submission fails and the platform redelivers inside the TTL — no
    exchange, no answer, and nothing in the log but one warning.
    """
    cache = DedupCache()

    assert cache.seen("m1") is False
    assert cache.seen("m1") is False, "a read must not be a write"

    cache.remember("m1")

    assert cache.seen("m1") is True


def test_the_one_step_cache_still_records_as_it_reads():
    """Kept for callers with nothing that can fail in between."""
    cache = DedupCache()

    assert cache.is_duplicate("m1") is False
    assert cache.is_duplicate("m1") is True
    assert cache.is_duplicate("m2") is False


def test_an_empty_message_id_is_never_a_duplicate():
    """A platform that reported no id has told us nothing to match on.

    Treating "no id" as one id would fold every such message into the
    first of them.
    """
    cache = DedupCache()

    assert cache.seen("") is False
    cache.remember("")
    assert cache.seen("") is False
    assert cache.is_duplicate("") is False


def test_the_cache_is_bounded_and_forgets_the_oldest_first():
    """A long-lived process must not grow one entry per message it has seen."""
    cache = DedupCache(max_size=4, trim_to=2)

    for index in range(5):
        cache.remember(f"m{index}")

    assert cache.seen("m0") is False
    assert cache.seen("m4") is True


def test_a_cache_entry_expires_with_its_ttl():
    cache = DedupCache(ttl_seconds=0.0)
    cache.remember("m1")

    assert cache.seen("m1") is False


# ---- rate limiting -----------------------------------------------------


def test_a_sender_within_the_window_is_allowed():
    limiter = RateLimiter(max_per_hour=2)

    assert limiter.check("owner") is True
    assert limiter.check("owner") is True


def test_a_sender_over_the_window_is_refused_and_others_are_not():
    """Per sender, so one busy conversation cannot starve another."""
    limiter = RateLimiter(max_per_hour=2)
    limiter.check("owner")
    limiter.check("owner")

    assert limiter.check("owner") is False
    assert limiter.check("someone-else") is True


def test_a_limit_of_zero_means_no_limit():
    """Which is the default, and is what every adapter ships with."""
    limiter = RateLimiter(max_per_hour=0)

    assert all(limiter.check("owner") for _ in range(100))


# ---- the capability table ---------------------------------------------


def test_a_capability_profile_is_frozen():
    """It is a class attribute shared by every instance of an adapter.

    One mutable table would let a deployment that adjusted a limit at
    runtime adjust it for a second account in the same process.
    """
    with pytest.raises(dataclasses.FrozenInstanceError):
        TELEGRAM.max_text_length = 10  # type: ignore[misc]


def test_a_capability_is_readable_by_name():
    assert TELEGRAM.supports("groups") is True
    assert FEISHU.supports("typing") is False
    assert DISCORD.supports("not_a_capability") is False


def test_every_profile_names_a_text_limit_a_chunker_can_act_on():
    """Except email's, which is the one the binding guard exists for.

    ``EMAIL.max_text_length`` is 0 and means "no practical limit" to a
    reader; the chunker reads it as a budget of zero. The email adapter
    therefore names its own number, and this records why a zero in the
    table is not simply corrected: the table says what the *platform*
    allows, and email genuinely has no useful ceiling.
    """
    from omicsclaw.entry.channel.capabilities import EMAIL

    assert TELEGRAM.max_text_length > 20
    assert DISCORD.max_text_length > 20
    assert EMAIL.max_text_length == 0


def test_the_default_profile_claims_nothing():
    """A platform that has not declared a capability does not have it."""
    default = ChannelCapabilities()

    assert default.groups is False
    assert default.media_send is False
    assert default.native_commands is False
    assert default.format_type == "plain"


# ---- the base configuration -------------------------------------------


def test_the_base_config_admits_nobody_and_limits_nothing_by_default():
    """Both halves matter, and in opposite directions.

    ``allowed_senders`` defaults to ``None`` so that a builder which forgot
    it produces a binding refusal rather than an open bot; the rate limit
    defaults to off because throttling an owner is a deployment's choice.
    """
    config = BaseChannelConfig()

    assert config.allowed_senders is None
    assert config.rate_limit_per_hour == 0
    assert config.text_chunk_limit > 20
    assert config.proxy is None


# ---- who may drive the bot --------------------------------------------


class _Adapter(Channel):
    """The least a channel can be: an allowlist and a record of what it sent."""

    name = "primitives"

    def __init__(self, config: BaseChannelConfig) -> None:
        super().__init__(config)
        self.answers: list[str] = []

    async def start(self) -> None:  # pragma: no cover - never started
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover - never started
        raise NotImplementedError

    async def send_command_output(self, reply_target, text: str) -> None:
        self.answers.append(text)


def _answer(channel: _Adapter, sender: str | None) -> bool:
    return asyncio.run(channel.answer_slash_command({}, "chat", sender, "/skills"))


@pytest.mark.parametrize(
    "allowed, sender",
    [
        (None, "owner"),
        (set(), "owner"),
        ({"   "}, "owner"),
        ({"owner"}, "stranger"),
        ({"owner"}, ""),
        ({"owner"}, None),
    ],
)
def test_a_command_from_anyone_but_an_owner_is_answered_with_nothing(allowed, sender):
    """Deny by default, and say nothing while denying.

    A slash command is answered by a direct provider call that reaches
    neither the rate limiter nor the ingress gate, so this is the only place
    the allowlist applies to one. An empty allowlist is the case worth
    naming: it admits nobody, exactly as ``SenderPolicy`` does by refusing
    to be built from one, because a bot that admits everybody looks the same
    from outside as a bot nobody has messaged.

    Refused means silent. A reply would tell an unknown sender both that the
    bot is there and that their id was checked against a list — and it still
    reports handled, so the text cannot fall through to the model instead.
    """
    channel = _Adapter(BaseChannelConfig(allowed_senders=allowed))

    assert _answer(channel, sender) is True
    assert channel.answers == []


def test_an_owner_still_gets_the_command_answered():
    """The other half, so the refusal above is not vacuous."""
    channel = _Adapter(BaseChannelConfig(allowed_senders={"owner"}))

    assert _answer(channel, " owner ") is True
    assert channel.answers, "an owner's /skills has to be answered"


# ---- the manager's health record --------------------------------------


def test_a_channel_health_record_counts_failures_and_resets_on_success():
    """The consecutive count is what tells a flapping channel from a dead one."""
    health = ChannelHealth()
    health.record_failure("TimeoutError")
    health.record_failure("TimeoutError")

    assert health.total_errors == 2
    assert health.consecutive_failures == 2
    assert health.last_error == "TimeoutError"
    assert health.last_error_time is not None

    health.record_success()

    assert health.consecutive_failures == 0
    assert health.total_errors == 2, "a success does not erase the history"
