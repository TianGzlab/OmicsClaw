"""``omicsclaw/engine`` — the model call that survives a bad minute.

Plan 0027 §3, and trap 12. A vendor SDK retries what fails before the
first byte; everything after it — a proxy that drops a half-streamed
response, a 5xx that arrives once the headers are already out — escapes
to this layer, which is where the legacy loop killed the run and threw
the trajectory away. One transient hiccup should not cost an agent its
work.

**Two budgets, and neither ever borrows from the other.** Transport
failures (TLS, DNS, connection establishment) are far more intermittent
than a 5xx, and the reference harness found that one budget could not
absorb both: three benchmark tasks hit the same x509 error on turn 1 and
abandoned the turn once ~3s of backoff was spent. So a transport failure
draws on ``network_retries`` and anything else on ``generate_retries``,
and exhausting one leaves the other untouched. (That failure reaches
*this* runtime spelled differently — see :data:`_TRANSPORT_MARKERS`,
where believing otherwise is what once made the wider budget
unreachable.)

**Classification is structural here, and textual in the harness it comes
from.** That harness matches substrings of the error message because
Go's SDK wrappers lose the concrete type. We have
:attr:`~omicsclaw.provider.ProviderError.status_code` instead: 429 and
5xx are worth another attempt, while any other 4xx is a request the model
must *fix* rather than one worth repeating. The substring check survives
only as the fallback for ``status_code is None`` — which is exactly the
"never reached the wire" case step 2 designed that ``None`` to mean, and
the strings it looks for have to be the ones our own adapters produce
rather than the ones that harness was reading.

**Leaf-adjacent.** ``omicsclaw.provider`` and the standard library.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass

from omicsclaw.provider import ProviderDeadlineExceeded, ProviderError

from .config import EngineConfig
from .types import EngineEvent

_GENERATE_DELAY_CAP = 30.0
"""Seconds one server-side retry may wait for. Past this, waiting longer
buys nothing that the attempt budget has not already paid for."""

_NETWORK_DELAY_CAP = 60.0
"""The transport cap, deliberately looser than its sibling: a route that
is flapping is worth waiting out rather than giving the turn up for."""

_MAX_BACKOFF_SHIFT = 32
"""Doublings past which the cap is returned without computing anything.

Ported from the reference harness, where it guards a genuine hazard: in
Go a shift at or beyond the type width yields **zero**, collapsing
bounded backoff into an uninterrupted hammering of the endpoint that is
already rate-limiting us. Python's ``**`` cannot overflow — it would
instead compute an astronomically large float or raise — so the guard is
kept for the other half of its value: the cap is what makes the backoff
bounded, and a delay nobody would ever wait out is its own bug.
"""

_TRANSPORT_MARKERS = (
    "connection error",
    "apiconnectionerror",
    "apitimeouterror",
    "timed out",
    "certificate_verify_failed",
    "ssl",
    "getaddrinfo",
    "name or service not known",
    "[errno 111]",
    "connection reset",
    "connection refused",
)
"""Substrings that name a failure to reach the endpoint at all.

Consulted only when no status code was reported, because a failure that
carries one demonstrably reached the wire.

**These are the strings this system can actually receive.** The first
draft carried the reference harness's Go vocabulary verbatim — ``x509:``,
``dial tcp``, ``i/o timeout``, ``no such host`` — which is what Go's
``net`` package prints and what no Python SDK has ever printed. Combined
with the rule above it was unreachable by construction: the substrings
are read only when ``status_code is None``, and a ``None`` status here
means the *local* Python SDK failed before the wire, so Go text could not
be in the message even in principle. The wider budget was therefore dead
configuration, and every transport failure quietly drew on the narrow
one — the exact failure ``network_retries`` was added to prevent.

What the two shipped adapters hand us instead: ``openai`` and
``anthropic`` v1.x collapse a refused TCP connection, a DNS failure and a
TLS failure into one ``APIConnectionError`` whose message is the
hard-coded ``"Connection error."``, plus ``APITimeoutError``
(``"Request timed out."``); both carry no ``status_code``, and each
adapter's ``_wrap`` turns them into a ``ProviderError``. The class names
appear too, because ``OpenAIProvider._wrap`` prefixes
``type(exc).__name__``. The remaining markers name what an adapter that
lets a lower-level exception through would say: ``ssl`` /
``certificate_verify_failed`` for a rejected certificate, ``getaddrinfo``
/ ``name or service not known`` for DNS, ``[errno 111]`` /
``connection refused`` / ``connection reset`` for the TCP layer.

Breadth is cheap here and narrowness is not. A false positive only buys a
failure that was going to be retried anyway the *wider* budget and the
longer backoff; a false negative is the bug above.
"""


@dataclass(frozen=True, slots=True)
class _Budget:
    """One retry allowance: how many attempts, how long between them."""

    attempts: int
    base_delay: float
    cap_delay: float


async def generate_with_retry(
    attempt: Callable[[], AsyncIterator[EngineEvent]],
    config: EngineConfig,
    *,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> AsyncIterator[EngineEvent]:
    """Drive one turn to a result, absorbing the failures worth absorbing.

    ``attempt`` is a factory rather than a coroutine because a retry has
    to start a *fresh* call: an async generator, once it has raised, is
    finished. It is a generator rather than a coroutine so that this one
    implementation covers both entry points — the streaming turn yields
    its deltas straight through, and the blocking turn yields nothing at
    all. A second retry loop written for the streaming path is how the
    two paths would start disagreeing about what counts as a failure.

    **A retried streaming turn replays.** Attempt 2 begins the model's
    answer again from nothing, so a consumer that already rendered half
    of attempt 1 sees the text restart. The reference harness behaves the
    same way, and the alternative — buffering every delta until the turn
    is known to have succeeded — would defeat the point of streaming.

    Only :class:`~omicsclaw.provider.ProviderError` is caught. A
    cancelled scope is not a failure and leaves untouched (trap 4), and
    an :class:`~omicsclaw.engine.types.EngineError` is this engine's own
    invariant breaking — retrying it would be a guess that the engine
    will contradict itself differently next time.

    That division is why a stream which ends without a ``DONE`` chunk
    reaches here as a ``ProviderError`` and gets its attempts: a provider
    that stopped mid-answer broke the *provider's* contract, and "a proxy
    that drops a half-streamed response" is the scenario named at the top
    of this module. Attributing it to the engine instead would have made
    the module's own headline case the one failure it could not absorb.

    ``sleep`` is injectable so a test can prove the backoff without
    paying it, and is resolved on each call rather than bound as a
    default so that patching :func:`asyncio.sleep` still works.

    Neither budget is floored at one attempt, and it needs no floor: the
    allowance is consulted only *after* a call has already failed, so a
    configured ``0`` and a configured ``1`` both buy exactly one call.
    The reference harness floors both and thereby changes nothing.
    """
    waiter = sleep if sleep is not None else asyncio.sleep
    default = _Budget(
        attempts=config.generate_retries,
        base_delay=_positive(config.generate_retry_base, 1.0),
        cap_delay=_GENERATE_DELAY_CAP,
    )
    network = _Budget(
        attempts=config.network_retries,
        base_delay=_positive(config.network_retry_base, 5.0),
        cap_delay=_NETWORK_DELAY_CAP,
    )

    attempt_number = 0
    while True:
        attempt_number += 1
        try:
            async with aclosing(attempt()) as events:
                async for event in events:
                    yield event
            return
        except ProviderError as error:
            budget = _budget_for(error, default, network)
            if budget is None or attempt_number >= budget.attempts:
                raise
            delay = backoff_delay(budget.base_delay, attempt_number, budget.cap_delay)
        await waiter(delay)


def backoff_delay(base: float, attempt: int, cap: float) -> float:
    """Seconds to wait after ``attempt`` failures: ``base * 2**(attempt-1)``.

    Capped, because an unbounded delay is indistinguishable from a hung
    run, and floored at ``base`` so that a caller passing the first
    attempt as ``0`` or ``1`` gets the same answer either way.
    """
    doublings = max(attempt - 1, 0)
    if doublings > _MAX_BACKOFF_SHIFT:
        return cap
    return min(base * 2.0**doublings, cap)


def _budget_for(
    error: ProviderError,
    default: _Budget,
    network: _Budget,
) -> _Budget | None:
    """Which allowance pays for this failure — or ``None`` to not retry.

    A 4xx that is not 429 is the one case where retrying is strictly
    wrong: a malformed request, a rejected key or a missing model will
    fail identically forever, so the attempts would buy nothing and the
    backoff would only delay telling the caller.

    With no status code there is nothing structural to read, so the
    substring check decides *which* budget rather than whether to spend
    one: a failure that never reached the wire is retried either way,
    generously when it names a transport fault and on the ordinary
    allowance when it does not.
    """
    if isinstance(error, ProviderDeadlineExceeded):
        return None
    status = error.status_code
    if status is None:
        return network if _looks_like_transport(str(error)) else default
    if status == 429 or status >= 500:
        return default
    return None


def _looks_like_transport(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _TRANSPORT_MARKERS)


def _positive(value: float, fallback: float) -> float:
    """A zero or negative base would turn backoff into a spin loop."""
    return value if value > 0 else fallback


__all__ = ["backoff_delay", "generate_with_retry"]
