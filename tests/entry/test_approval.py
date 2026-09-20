"""Asking a human without deadlocking the loop that is waiting.

Plan 0031 trap 1, Q12 and Q18. The broker is the only object in this
package whose whole purpose is to suspend one Task until a *different*
one answers, so every test here either resolves the question from
another Task or asserts a refusal — and each one carries its own
:func:`asyncio.wait_for`, because a broker bug is a hang and this suite
has no timeout plugin.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from omicsclaw.entry.approval import ABANDONED_REASON, TIMEOUT_REASON, ApprovalBroker
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.stream import TurnStream
from omicsclaw.tools.context import ApprovalDecision, ApprovalRequest

# Fast enough that a broken deadline fails the suite in a second rather
# than hanging it; long enough that a loaded machine does not expire one
# we meant to answer.
WAIT_S = 2.0

SECRET = "/data/subject-4821/genome.vcf"


def _stream() -> TurnStream:
    return TurnStream("s1", "t1")


def _frames(stream: TurnStream, kind: TurnEventType) -> tuple:
    return tuple(frame for frame in stream.retained() if frame.type is kind)


def _request(tool: str = "bash") -> ApprovalRequest:
    return ApprovalRequest(tool_name=tool, arguments=f'{{"path": "{SECRET}"}}')


# ---- the round trip ------------------------------------------------------


def test_a_question_becomes_a_frame_before_anybody_has_answered():
    """The whole point: the prompt is visible while the asker waits."""
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0)  # let the channel publish and suspend

        published = _frames(stream, TurnEventType.APPROVAL_REQUIRED)
        assert len(published) == 1
        assert published[0].approval.tool_name == "bash"
        assert broker.pending() == (published[0].request_id,)

        broker.settle(published[0].request_id, ApprovalDecision(approved=True))
        return await asyncio.wait_for(asking, WAIT_S)

    decision = asyncio.run(drive())

    assert decision.approved
    settled = _frames(stream, TurnEventType.APPROVAL_SETTLED)
    assert len(settled) == 1
    assert settled[0].decision.approved


def test_two_questions_outstanding_at_once_are_both_answerable():
    """Trap 1 in miniature, before the engine is anywhere near it.

    Two tools asking concurrently is the case a single-consumer design
    cannot serve: the second request is issued while the first is still
    suspended, so a broker that could only hold one would deadlock here.
    """
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        first = asyncio.create_task(broker(_request("bash")))
        second = asyncio.create_task(broker(_request("write_file")))
        await asyncio.sleep(0)

        ids = [frame.request_id for frame in _frames(
            stream, TurnEventType.APPROVAL_REQUIRED
        )]
        assert len(set(ids)) == 2, "each question needs its own id"

        broker.settle(ids[0], ApprovalDecision(approved=True))
        broker.settle(ids[1], ApprovalDecision(approved=False, reason="no"))
        return await asyncio.wait_for(asyncio.gather(first, second), WAIT_S)

    one, two = asyncio.run(drive())

    assert one.approved
    assert not two.approved
    assert two.reason == "no"


# ---- the races that are ordinary input (Q18, trap 11) --------------------


def test_an_unknown_request_id_is_a_no_op():
    broker = ApprovalBroker(_stream())

    assert broker.settle("never-issued", ApprovalDecision(approved=True)) is False


def test_answering_the_same_question_twice_is_a_no_op():
    """A person clicking twice is input, not a programming error."""
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0)
        request_id = _frames(stream, TurnEventType.APPROVAL_REQUIRED)[0].request_id

        assert broker.settle(request_id, ApprovalDecision(approved=True)) is True
        again = broker.settle(request_id, ApprovalDecision(approved=False))

        await asyncio.wait_for(asking, WAIT_S)
        return again

    assert asyncio.run(drive()) is False


def test_answering_after_the_exchange_gave_up_is_a_no_op():
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0)
        request_id = _frames(stream, TurnEventType.APPROVAL_REQUIRED)[0].request_id

        asking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asking, WAIT_S)

        return broker.settle(request_id, ApprovalDecision(approved=True))

    assert asyncio.run(drive()) is False


def test_a_cancelled_question_leaves_nothing_pending():
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0)
        asking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asking, WAIT_S)
        return broker.pending()

    assert asyncio.run(drive()) == ()


# ---- the deadline denies (Q12) ------------------------------------------


def test_the_deadline_denies_rather_than_waiting_for_ever():
    """Fail closed, and say which kind of "no" this was."""
    stream = _stream()
    broker = ApprovalBroker(stream, timeout_s=0.01)

    async def drive():
        return await asyncio.wait_for(broker(_request()), WAIT_S)

    decision = asyncio.run(drive())

    assert not decision.approved
    assert decision.reason == TIMEOUT_REASON
    assert _frames(stream, TurnEventType.APPROVAL_SETTLED)[0].decision.reason == (
        TIMEOUT_REASON
    )


def test_no_deadline_means_the_question_waits():
    """The CLI's shape: a person is present, so the prompt may sit."""
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0.02)
        assert not asking.done(), "a broker with no deadline must still be waiting"
        request_id = _frames(stream, TurnEventType.APPROVAL_REQUIRED)[0].request_id
        broker.settle(request_id, ApprovalDecision(approved=True))
        return await asyncio.wait_for(asking, WAIT_S)

    assert asyncio.run(drive()).approved


def test_a_non_positive_deadline_is_refused_at_construction():
    """Arithmetic that produced zero must not read as "deny everything"."""
    with pytest.raises(ValueError):
        ApprovalBroker(_stream(), timeout_s=0)


# ---- the exchange ending under an open question -------------------------


def test_abandoning_denies_what_is_outstanding_and_says_so():
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0)
        broker.abandon()
        return await asyncio.wait_for(asking, WAIT_S)

    decision = asyncio.run(drive())

    assert not decision.approved
    assert decision.reason == ABANDONED_REASON
    assert broker.pending() == ()


def test_one_question_never_produces_two_settlements():
    """A consumer correlating by ``request_id`` must not see it twice."""
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        asking = asyncio.create_task(broker(_request()))
        await asyncio.sleep(0)
        broker.abandon()
        await asyncio.wait_for(asking, WAIT_S)

    asyncio.run(drive())

    assert len(_frames(stream, TurnEventType.APPROVAL_SETTLED)) == 1


def test_abandoning_with_nothing_outstanding_says_nothing():
    stream = _stream()

    ApprovalBroker(stream).abandon()

    assert stream.retained() == ()


# ---- Q22: the logs never carry the payload ------------------------------


def test_no_tool_argument_ever_reaches_the_log(caplog):
    """``CLAUDE.md``'s first safety rule is one a log statement can break.

    An :class:`ApprovalRequest` carries the raw argument payload of the
    call about to run — the ``bash`` command line, the ``write_file``
    body — and those can name a subject. The tool's *name* is fine; its
    arguments are not.
    """
    stream = _stream()
    broker = ApprovalBroker(stream)

    async def drive():
        with caplog.at_level(logging.DEBUG, logger="omicsclaw.entry"):
            asking = asyncio.create_task(broker(_request()))
            await asyncio.sleep(0)
            request_id = _frames(stream, TurnEventType.APPROVAL_REQUIRED)[0].request_id
            broker.settle(request_id, ApprovalDecision(approved=True))
            await asyncio.wait_for(asking, WAIT_S)

    asyncio.run(drive())

    written = "\n".join(record.getMessage() for record in caplog.records)
    assert "approval requested" in written, "the probe must have logged something"
    assert SECRET not in written
