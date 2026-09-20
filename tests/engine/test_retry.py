"""Contract tests for ``omicsclaw.engine.retry`` (plan 0027 §7, trap 12).

Retrying is only worth having if it refuses to retry the wrong things, so
most of this file is about the failures that must reach the caller
immediately: a 400 that will fail identically forever, a cancelled scope,
an exception that is not the provider's at all.

The rest is about the two budgets. They are independent by design — the
reference harness found one allowance could not cover both a 5xx and a
flapping TLS route — and independence is only observable through *which*
backoff a failure draws on, which is why the tests below read the
recorded waits rather than the attempt count alone.

Nothing here sleeps. The waiter is injected (and, for the one test that
proves the default, patched), so a 30-second cap costs nothing to assert.

One rule the last section of this file exists to enforce: **a
classification test must not invent the string it classifies.** The first
version of these tests hand-built ``ProviderError(None, "<some error
text>")`` out of the same source the classifier's markers were ported
from, so fixture and implementation agreed with each other and with
nothing a Python SDK has ever raised. The final section therefore starts
from the vendor exception, pushes it through the shipped adapter's own
``_wrap``, and only then asks which budget pays.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine, Sequence
from typing import Any, TypeVar

import pytest

from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.retry import (
    _Budget,
    _budget_for,
    backoff_delay,
    generate_with_retry,
)
from omicsclaw.engine.types import EngineError, EngineEvent, EngineEventType
from omicsclaw.provider import (
    AnthropicProvider,
    OpenAIProvider,
    ProviderConfig,
    ProviderError,
)

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds any one scenario may take. A hang guard, not a measurement.

A retry loop that forgets to stop does not fail, it spins, and a spin
wedges the whole suite instead of naming the test that caught it.
"""


class Attempts:
    """A turn that fails the way it was told to, then succeeds.

    Each outcome is either an exception to raise or a sequence of events
    to yield — and an exception inside that sequence raises where it
    sits, which is how a turn that failed *after* streaming half an
    answer gets written. The last outcome repeats forever, so "always
    fails" and "fails twice then works" are both one line to express.
    """

    def __init__(
        self,
        *outcomes: BaseException | Sequence[EngineEvent | BaseException],
    ) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self) -> AsyncIterator[EngineEvent]:
        return self._attempt()

    async def _attempt(self) -> AsyncIterator[EngineEvent]:
        self.calls += 1
        outcome = self._outcomes[min(self.calls - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        for item in outcome:
            if isinstance(item, BaseException):
                raise item
            yield item


class Clock:
    """A waiter that records what it was asked to wait for, and returns."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.waits.append(delay)


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; ``tests/provider/`` drives
    async tests with :func:`asyncio.run` and so does this."""

    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


def _drive(
    attempts: Attempts,
    config: EngineConfig,
    clock: Clock | None = None,
) -> tuple[list[EngineEvent], Clock]:
    waiter = clock or Clock()

    async def scenario() -> list[EngineEvent]:
        return [
            event
            async for event in generate_with_retry(attempts, config, sleep=waiter)
        ]

    return _run(scenario()), waiter


def _failed(status: int | None, message: str = "backend said no") -> ProviderError:
    return ProviderError(message, provider="fake", status_code=status)


def _ok(text: str) -> tuple[EngineEvent, ...]:
    return (EngineEvent.text(text, turn=1),)


# --- the happy path -------------------------------------------------------


def test_a_call_that_works_first_time_is_never_retried():
    attempts = Attempts(_ok("hello"))

    events, clock = _drive(attempts, EngineConfig())

    assert attempts.calls == 1
    assert clock.waits == []
    assert [event.delta for event in events] == ["hello"]


def test_a_transient_failure_is_retried_until_it_succeeds():
    attempts = Attempts(_failed(503), _failed(503), _ok("third time"))

    events, clock = _drive(attempts, EngineConfig())

    assert attempts.calls == 3
    assert clock.waits == [1.0, 2.0]
    assert [event.delta for event in events] == ["third time"]


def test_every_event_of_the_failed_attempt_still_reached_the_consumer():
    """A stream that dies mid-answer has already shown half an answer.

    The deltas of attempt 1 are gone from nobody's screen, so attempt 2
    replays from the beginning — the reference harness does the same, and
    buffering everything until a turn is known to have succeeded would
    defeat the point of streaming.
    """
    attempts = Attempts([EngineEvent.text("par"), _failed(500)], _ok("whole answer"))

    events, _ = _drive(attempts, EngineConfig())

    assert attempts.calls == 2
    assert [event.delta for event in events] == ["par", "whole answer"]
    assert all(e.type is EngineEventType.TEXT_DELTA for e in events)


# --- the attempt budget ---------------------------------------------------


def test_the_budget_counts_attempts_rather_than_retries_on_top_of_one():
    """``generate_retries=3`` means three calls, not four."""
    attempts = Attempts(_failed(500))

    with pytest.raises(ProviderError):
        _drive(attempts, EngineConfig(generate_retries=3))

    assert attempts.calls == 3


def test_a_budget_of_one_disables_retrying_altogether():
    attempts = Attempts(_failed(500))

    with pytest.raises(ProviderError):
        _drive(attempts, EngineConfig(generate_retries=1))

    assert attempts.calls == 1


def test_a_budget_below_one_still_buys_a_single_attempt():
    """A misconfigured zero must not mean "never call the model".

    It cannot, and that is worth pinning rather than guarding: the
    allowance is read only after a call has already failed, so ``0`` and
    ``1`` both buy exactly one call and neither buys none.
    """
    attempts = Attempts(_failed(500))
    clock = Clock()

    with pytest.raises(ProviderError):
        _drive(attempts, EngineConfig(generate_retries=0), clock)

    assert attempts.calls == 1
    assert clock.waits == []


def test_the_failure_that_reaches_the_caller_is_the_last_one():
    attempts = Attempts(_failed(500, "first"), _failed(503, "last"))

    with pytest.raises(ProviderError) as raised:
        _drive(attempts, EngineConfig(generate_retries=2))

    assert "last" in str(raised.value)
    assert raised.value.status_code == 503


# --- classification: what deserves another attempt ------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_rate_limit_or_a_server_error_is_worth_another_attempt(status: int):
    attempts = Attempts(_failed(status), _ok("recovered"))

    events, _ = _drive(attempts, EngineConfig())

    assert attempts.calls == 2
    assert [event.delta for event in events] == ["recovered"]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_a_client_error_other_than_a_rate_limit_is_never_retried(status: int):
    """It will fail identically forever, so the attempts buy nothing and
    the backoff only delays telling the caller."""
    attempts = Attempts(_failed(status))

    with pytest.raises(ProviderError):
        _drive(attempts, EngineConfig(generate_retries=5))

    assert attempts.calls == 1


def test_a_failure_that_never_reached_the_wire_falls_back_to_its_text():
    """``status_code is None`` is exactly the case step 2 designed it for.

    There is no structural signal left, so the substring check decides
    which budget pays — and a transport fault draws on the wider one.
    """
    text = "chat completion failed: APIConnectionError: Connection error."
    attempts = Attempts(_failed(None, text))
    config = EngineConfig(generate_retries=2, network_retries=3)

    with pytest.raises(ProviderError):
        _drive(attempts, config)

    assert attempts.calls == 3


def test_a_status_less_failure_that_names_no_transport_fault_still_retries():
    """The ordinary allowance, not the wide one.

    The reference harness retries every non-cancelled failure; refusing
    here would be a regression on the one class of error it was built to
    survive, so the substring check chooses a budget rather than a
    verdict.
    """
    attempts = Attempts(_failed(None, "the model is overloaded"))
    config = EngineConfig(generate_retries=2, network_retries=6)
    clock = Clock()

    with pytest.raises(ProviderError):
        _drive(attempts, config, clock)

    assert attempts.calls == 2
    assert clock.waits == [1.0]


def test_a_transport_marker_is_recognised_whatever_its_case():
    text = "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
    attempts = Attempts(_failed(None, text), _ok("fine"))
    clock = Clock()

    _drive(attempts, EngineConfig(), clock)

    assert clock.waits == [5.0]


def test_a_status_code_is_believed_over_the_error_text():
    """A failure carrying a status demonstrably reached the wire, so the
    substring check has nothing left to add — a 400 whose message happens
    to read ``Connection error.`` is still a 400."""
    attempts = Attempts(_failed(400, "Connection error. (said the gateway)"))

    with pytest.raises(ProviderError):
        _drive(attempts, EngineConfig(generate_retries=5))

    assert attempts.calls == 1


@pytest.mark.parametrize(
    "error",
    [
        EngineError("the kernel ended without a DONE event"),
        RuntimeError("an adapter bug"),
        ValueError("a malformed argument"),
    ],
)
def test_a_failure_that_is_not_the_providers_is_not_retried(error: Exception):
    """``except ProviderError``, not ``except Exception``.

    An ``EngineError`` is this engine's own invariant breaking; retrying
    it would be a guess that the engine will contradict itself
    differently next time. Note which failure is *not* on this list any
    more: a stream that ended without a ``DONE`` chunk is the provider's
    contract breaking, is raised as a ``ProviderError``, and is retried —
    see ``test_loop_stream.py``.
    """
    attempts = Attempts(error)

    with pytest.raises(type(error)):
        _drive(attempts, EngineConfig(generate_retries=5))

    assert attempts.calls == 1


# --- two budgets, and neither borrows from the other ----------------------


def test_the_transport_budget_survives_a_starved_default_budget():
    """``generate_retries=1`` disables ordinary retrying; a transport
    failure must still get its own, wider allowance."""
    text = "Anthropic Messages request failed: Connection error."
    attempts = Attempts(_failed(None, text))
    config = EngineConfig(generate_retries=1, network_retries=4)
    clock = Clock()

    with pytest.raises(ProviderError):
        _drive(attempts, config, clock)

    assert attempts.calls == 4
    assert clock.waits == [5.0, 10.0, 20.0]


def test_the_default_budget_survives_a_starved_transport_budget():
    """And the other direction, which is what makes the pair independent
    rather than merely ordered."""
    attempts = Attempts(_failed(500))
    config = EngineConfig(generate_retries=4, network_retries=1)
    clock = Clock()

    with pytest.raises(ProviderError):
        _drive(attempts, config, clock)

    assert attempts.calls == 4
    assert clock.waits == [1.0, 2.0, 4.0]


def test_each_budget_backs_off_from_its_own_base():
    transport = Attempts(_failed(None, "connection refused"), _ok("ok"))
    server = Attempts(_failed(500), _ok("ok"))
    config = EngineConfig(generate_retry_base=0.25, network_retry_base=7.0)
    transport_clock = Clock()
    server_clock = Clock()

    _drive(transport, config, transport_clock)
    _drive(server, config, server_clock)

    assert transport_clock.waits == [7.0]
    assert server_clock.waits == [0.25]


def test_a_base_delay_of_zero_falls_back_to_a_sane_one():
    """A zero base would turn bounded backoff into a spin loop.

    Also pins how the exponent is counted: the second wait is ``5 * 2``
    and not ``5``, because the doubling counts how many times *this turn*
    has failed rather than how often this particular budget has paid. A
    turn that alternated failure kinds would otherwise reset its own
    backoff and hammer an endpoint that is failing in two ways at once.
    """
    attempts = Attempts(_failed(500), _failed(None, "Connection error."), _ok("ok"))
    config = EngineConfig(generate_retry_base=0.0, network_retry_base=0.0)
    clock = Clock()

    _drive(attempts, config, clock)

    assert clock.waits == [1.0, 10.0]


# --- the backoff itself ---------------------------------------------------


def test_the_first_attempt_waits_exactly_the_base_delay():
    assert backoff_delay(1.5, 1, 30.0) == 1.5


def test_an_attempt_number_below_one_is_treated_as_the_first():
    """``base >> -1`` is not a delay anyone asked for."""
    assert backoff_delay(1.5, 0, 30.0) == 1.5
    assert backoff_delay(1.5, -3, 30.0) == 1.5


def test_the_delay_doubles_with_every_further_attempt():
    assert [backoff_delay(1.0, n, 100.0) for n in (1, 2, 3, 4)] == [
        1.0,
        2.0,
        4.0,
        8.0,
    ]


def test_the_delay_is_capped_however_large_the_base():
    assert backoff_delay(1000.0, 1, 30.0) == 30.0


def test_the_delay_is_capped_however_many_attempts_have_failed():
    assert backoff_delay(1.0, 12, 30.0) == 30.0


def test_an_absurd_attempt_number_returns_the_cap_rather_than_computing_it():
    """The shift guard, ported for the opposite reason it exists in Go.

    There a shift at or beyond the type width yields **zero**, collapsing
    bounded backoff into an uninterrupted hammering of the endpoint that
    is already rate-limiting us. Python instead computes ``2.0 **
    999_999`` and raises :exc:`OverflowError`, so the guard earns its
    keep either way — and the cap is the answer in both languages.
    """
    assert backoff_delay(1.0, 1_000_000, 30.0) == 30.0
    assert backoff_delay(1.0, 1_000_000, 60.0) == 60.0


def test_the_two_caps_differ_so_a_flapping_route_is_waited_out_longer():
    transport = Attempts(_failed(None, "[Errno -2] Name or service not known"))
    server = Attempts(_failed(500))
    config = EngineConfig(
        generate_retries=9,
        generate_retry_base=1000.0,
        network_retries=9,
        network_retry_base=1000.0,
    )
    transport_clock = Clock()
    server_clock = Clock()

    with pytest.raises(ProviderError):
        _drive(transport, config, transport_clock)
    with pytest.raises(ProviderError):
        _drive(server, config, server_clock)

    assert set(transport_clock.waits) == {60.0}
    assert set(server_clock.waits) == {30.0}


# --- trap 4: cancellation is not a failure --------------------------------


def test_a_cancelled_attempt_is_never_retried():
    """A cancelled scope says somebody stopped the work, not that the
    work failed. Retrying one would restart work the caller asked to
    end."""
    attempts = Attempts(asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        _drive(attempts, EngineConfig(generate_retries=5))

    assert attempts.calls == 1


def test_a_cancellation_arriving_during_the_backoff_is_not_absorbed():
    """The wait between attempts is the longest the loop ever blocks, so
    it is where a cancellation is most likely to land."""

    async def scenario() -> tuple[bool, BaseException, int]:
        attempts = Attempts(_failed(500))
        waiting = asyncio.Event()

        async def sleep_forever(delay: float) -> None:
            waiting.set()
            await asyncio.Event().wait()

        async def consume() -> None:
            async for _event in generate_with_retry(
                attempts, EngineConfig(generate_retries=5), sleep=sleep_forever
            ):
                pass

        task = asyncio.ensure_future(consume())
        await waiting.wait()
        task.cancel()
        outcome = (await asyncio.gather(task, return_exceptions=True))[0]
        return task.cancelled(), outcome, attempts.calls

    cancelled, outcome, calls = _run(scenario())

    assert cancelled
    assert isinstance(outcome, asyncio.CancelledError)
    assert calls == 1


# --- the injected waiter --------------------------------------------------


def test_the_waiter_defaults_to_asyncio_sleep_and_is_resolved_late(monkeypatch):
    """Binding :func:`asyncio.sleep` as a default argument would freeze it
    at import time, and every test above would then be asserting about a
    function nobody could replace."""
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    attempts = Attempts(_failed(500), _ok("recovered"))

    async def scenario() -> list[EngineEvent]:
        return [event async for event in generate_with_retry(attempts, EngineConfig())]

    events = _run(scenario())

    assert slept == [1.0]
    assert [event.delta for event in events] == ["recovered"]


# --- the failures the shipped adapters can actually deliver ---------------
#
# Everything above builds its own ``ProviderError``. This section refuses
# to: it starts from an exception shaped like the vendor SDK's, pushes it
# through the adapter's real ``_wrap``, and classifies what comes out.
# The distinction is not academic — the markers this replaced were Go
# ``net``-package strings, agreed with by every hand-built fixture in the
# file and reachable by nothing.


class FakeAPIError(Exception):
    """The shape of ``openai.APIError`` / ``anthropic.APIError``.

    Neither SDK is installed here, and installing one to assert on the
    *shape* of its exceptions would buy nothing: the two things the
    adapters read are reproduced exactly — ``str(exc)``, and the fact
    that this base class carries no ``status_code`` attribute at all,
    which is what makes ``getattr(exc, "status_code", None)`` come back
    ``None`` and hand the question to the substring check.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class FakeAPIStatusError(FakeAPIError):
    """``APIStatusError``, the subclass that does carry one."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeAPIConnectionError(FakeAPIError):
    """``APIConnectionError``, whose message the SDKs hard-code.

    A refused TCP connection, a DNS failure and a TLS failure all arrive
    as this one class carrying this one string, which is why the
    classifier cannot hope to tell them apart and does not try.
    """

    def __init__(self, message: str = "Connection error.") -> None:
        super().__init__(message)


class FakeAPITimeoutError(FakeAPIConnectionError):
    """``APITimeoutError``, a subclass of the above in both SDKs."""

    def __init__(self) -> None:
        super().__init__("Request timed out.")


_DEFAULT_BUDGET = _Budget(attempts=3, base_delay=1.0, cap_delay=30.0)
_NETWORK_BUDGET = _Budget(attempts=6, base_delay=5.0, cap_delay=60.0)


def _through_openai(exc: Exception) -> ProviderError:
    provider = OpenAIProvider(ProviderConfig(provider="openai", model="gpt-5.5"))
    return provider._wrap(exc, "chat completion failed")


def _through_anthropic(exc: Exception) -> ProviderError:
    provider = AnthropicProvider(
        ProviderConfig(provider="anthropic", model="claude-sonnet-4-5")
    )
    return provider._wrap(exc)


_WRAPPERS = [_through_openai, _through_anthropic]


def _budget_name(error: ProviderError) -> str:
    budget = _budget_for(error, _DEFAULT_BUDGET, _NETWORK_BUDGET)
    if budget is None:
        return "none"
    return "network" if budget is _NETWORK_BUDGET else "default"


def test_the_sdk_doubles_reproduce_the_shape_the_adapters_read():
    """Pins the fidelity the rest of this section rests on.

    If ``APIError`` grew a ``status_code`` the adapters would report it
    and the substring check would never run, so "the base class has none"
    is a premise worth asserting rather than assuming.
    """
    assert not hasattr(FakeAPIConnectionError(), "status_code")
    assert not hasattr(FakeAPITimeoutError(), "status_code")
    assert FakeAPIStatusError("nope", 400).status_code == 400
    assert str(FakeAPIConnectionError()) == "Connection error."
    assert str(FakeAPITimeoutError()) == "Request timed out."


@pytest.mark.parametrize("wrap", _WRAPPERS, ids=["openai", "anthropic"])
def test_a_connection_error_from_a_shipped_adapter_draws_on_the_transport_budget(
    wrap,
):
    """The failure the wide budget was added for, as it really arrives.

    Both adapters wrap ``APIConnectionError`` into a ``ProviderError``
    with ``status_code=None`` and the SDK's hard-coded ``"Connection
    error."`` in the text. Under the Go markers this matched nothing and
    fell to the narrow budget — three attempts and 3s of backoff, which
    is precisely the exhaustion ``network_retries`` exists to prevent.
    """
    wrapped = wrap(FakeAPIConnectionError())

    assert wrapped.status_code is None
    assert _budget_name(wrapped) == "network"


@pytest.mark.parametrize("wrap", _WRAPPERS, ids=["openai", "anthropic"])
def test_a_timeout_error_from_a_shipped_adapter_draws_on_the_transport_budget(wrap):
    """``APITimeoutError`` never reached the wire either: the SDK gave up
    before an answer, so it is the transport that is flapping."""
    wrapped = wrap(FakeAPITimeoutError())

    assert wrapped.status_code is None
    assert _budget_name(wrapped) == "network"


@pytest.mark.parametrize(
    "text",
    [
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        "[Errno -2] Name or service not known",
        "[Errno 111] Connection refused",
        "Connection reset by peer",
        "socket.gaierror: getaddrinfo failed",
    ],
    ids=["tls", "dns", "refused", "reset", "getaddrinfo"],
)
def test_a_lower_level_exception_an_adapter_let_through_is_transport_too(text: str):
    """Not every failure is pre-digested into ``APIConnectionError``.

    An adapter that raises before the SDK call — or a third-party one
    satisfying the Protocol — can hand up the underlying ``OSError`` or
    ``SSLError`` verbatim, and these are the strings CPython prints for
    them.
    """
    assert _budget_name(_through_openai(FakeAPIError(text))) == "network"


@pytest.mark.parametrize(
    ("status", "expected"),
    [(429, "default"), (503, "default"), (400, "none"), (401, "none")],
)
def test_a_wrapped_status_error_is_classified_by_its_status_not_its_text(
    status: int, expected: str
):
    """The structural signal wins wherever there is one. The text here is
    deliberately the transport wording, so a classifier that consulted it
    first would be caught."""
    wrapped = _through_openai(FakeAPIStatusError("Connection error.", status))

    assert wrapped.status_code == status
    assert _budget_name(wrapped) == expected


def test_a_real_connection_error_gets_six_attempts_on_the_default_config():
    """The end-to-end reproduction, with the budgets a deployment ships.

    The whole point of ``network_retries=6`` is that this exact failure
    gets six attempts and ~95s of patience instead of three and 3s. Read
    as a behaviour rather than as a classification: it is what the
    classification is *for*.
    """
    wrapped = _through_openai(FakeAPIConnectionError())
    attempts = Attempts(wrapped)
    clock = Clock()

    with pytest.raises(ProviderError):
        _drive(attempts, EngineConfig(), clock)

    assert attempts.calls == 6
    assert clock.waits == [5.0, 10.0, 20.0, 40.0, 60.0]
