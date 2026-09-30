"""The chunker's two non-terminating inputs, and the guard above them.

``chunk_text`` does not raise on a non-positive per-chunk budget — it loops,
synchronously, forever. That matters more than it sounds: the loop holds the
event loop's only thread, so ``asyncio.timeout`` cannot interrupt it and
every other conversation in the process stops with it. Neither input is
hypothetical. The email capability profile declares ``max_text_length = 0``
("no practical limit") and the idiom every adapter uses to pick a limit is
``config.text_chunk_limit or capabilities.max_text_length``, so a config-side
zero resolves to exactly that; and the second path needs only a limit at or
below the twenty characters reserved for a code fence.

Both halves are asserted, because they fail differently: the binding refuses
such a limit at composition, and the clamp protects the callers that chunk
without going through a binding.
"""

from __future__ import annotations

import signal

import pytest

from omicsclaw.entry.channel.base import chunk_text
from omicsclaw.entry.channel.binding import ChannelSurfaceBinding
from omicsclaw.entry.ingress import SenderPolicy

DEADLINE_S = 3
"""Seconds a call gets before it is declared non-terminating.

``SIGALRM`` rather than a timeout plugin, because there is none on this
machine and because the defect being pinned is precisely one that no
asynchronous timeout can reach.
"""

FENCED = "```py\n" + "x = 1\n" * 200 + "```"


class _TookTooLong(Exception):
    pass


def bounded(call, *args):
    """Run *call*, failing rather than hanging if it does not return."""

    def fire(_signum, _frame):
        raise _TookTooLong()

    previous = signal.signal(signal.SIGALRM, fire)
    signal.alarm(DEADLINE_S)
    try:
        return call(*args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def policy() -> SenderPolicy:
    return SenderPolicy(allowed_senders=frozenset({"owner"}), bot_identity="bot")


async def _deliver(_request):  # pragma: no cover - never called
    raise AssertionError("this binding never delivers")


def binding(**overrides) -> ChannelSurfaceBinding:
    fields = {
        "adapter": "telegram",
        "account_namespace": "bot-1",
        "sender_policy": policy(),
        "delivery_adapter": _deliver,
    }
    fields.update(overrides)
    return ChannelSurfaceBinding(**fields)


# ---- trap 2: the chunker itself ---------------------------------------


@pytest.mark.parametrize("limit", [0, -1, 1, 5, 10])
def test_the_chunker_always_advances_however_small_the_budget(limit):
    """A budget of zero or less used to leave the cursor where it was.

    ``remaining[0:]`` is ``remaining``, three ``rfind`` calls all return
    ``-1``, and the loop condition is still true. The clamp is what turns
    that into slow progress instead of none.
    """
    text = "a b c\n\nd e f\n" * 20

    chunks = bounded(chunk_text, text, limit)

    assert chunks
    assert "".join(chunk.replace("\n", "") for chunk in chunks).strip()


def test_a_code_fence_under_a_small_limit_still_terminates():
    """The second path, and the one that is not obvious from the signature.

    Twenty characters are reserved for the re-opened fence as soon as the
    text enters a code block, so any limit at or below twenty makes the
    budget non-positive *mid-text* — the call starts out looking healthy.

    What the clamp buys is termination and no lost payload, not a readable
    split: at a budget of one character the result is one character per
    fenced chunk. That is a deployment nobody should have, which is what the
    binding guard is for; this only has to not hang.
    """
    chunks = bounded(chunk_text, FENCED, 10)

    assert chunks
    assert sum(chunk.count("x") for chunk in chunks) == 200

    # A limit the guard would admit splits the same text readably, so the
    # assertion above is about the clamp and not about the chunker.
    readable = bounded(chunk_text, FENCED, 30)
    assert any("x = 1\nx = 1" in chunk for chunk in readable)


# ---- trap 2: the guard that stops it being reachable ------------------


@pytest.mark.parametrize("limit", [0, -1, 1, 20])
def test_a_binding_refuses_a_chunk_limit_the_chunker_cannot_use(limit):
    """At composition, not at the first message.

    A start-up that refuses names the misconfiguration. The alternative is a
    deployment that comes up, answers nothing, and pins a CPU.
    """
    with pytest.raises(ValueError, match="text_chunk_limit"):
        binding(text_chunk_limit=limit)


def test_a_binding_accepts_the_first_usable_limit():
    """21 is the boundary, so the refusal above is not simply "any number"."""
    assert binding(text_chunk_limit=21).text_chunk_limit == 21
