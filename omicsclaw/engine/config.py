"""``omicsclaw/engine`` — how one run is budgeted.

Plan 0027 §3. The sibling of
:class:`~omicsclaw.provider.config.ProviderConfig`, and deliberately
disjoint from it: that record holds what a *model call* needs — model,
temperature, output ceiling, timeouts — while this one holds what a
*loop* needs, which is entirely a matter of budgets. Nothing here reaches
a prompt and nothing here names a vendor.

One difference from its sibling is load-bearing. ``ProviderConfig`` is
resolved from the ambient shell, because an API key has nowhere else to
live. :class:`EngineConfig` reads **nothing**: a caller constructs one
and passes it in. A turn ceiling that changed with whichever shell
launched the process would make two runs of the same benchmark task
incomparable, and the resulting failure — a task that stalls on one
machine and completes on another — looks like a model regression rather
than like configuration.

The reference harness spells this as sixteen ``With…`` functional
options mutating the engine in place. A frozen record plus
:meth:`EngineConfig.with_overrides` says the same thing without letting a
live engine's budget be edited underneath a running loop.

**Leaf-adjacent.** ``omicsclaw.schema`` and the standard library only —
and in this module, only the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """The whole of what one run's budget consists of.

    Frozen on purpose. An engine holds one for its lifetime, so two runs
    driven concurrently by the same engine cannot observe each other's
    limits being changed mid-flight — a race whose only symptom would be
    a turn ceiling that moved.
    """

    max_turns: int = 50
    """Model calls one run may make. ``<= 0`` means no ceiling.

    50 is chosen against two known points rather than picked. The
    reference harness uses 500, tuned for unattended long-horizon coding
    runs. The legacy OmicsClaw loop uses
    ``OMICSCLAW_MAX_TOOL_ITERATIONS=20``, and
    ``docs/evaluation/cross-agent-benchmark-guide.md`` records that 20 is
    too low: it stalls the 30-turn benchmark tasks outright. 50 clears
    that documented failure point without letting a first version run
    away for 500 turns.

    Counted in model calls, and checked *before* each one, so
    ``max_turns=1`` permits exactly one call.
    """

    tool_timeout: float = 60.0
    """Seconds one tool may run. ``<= 0`` means no per-tool limit.

    Per *call*, never per turn: a slow tool must degrade into a single
    ``is_error`` Observation the model can react to, not cancel the
    siblings that were running beside it. Seconds as a float rather than
    a duration object, matching ``ProviderConfig.timeout_seconds``.
    """

    max_concurrent_tools: int = 0
    """Tools one turn may run at once. ``0`` means unlimited.

    A ceiling on parallelism only — it never reorders anything. The
    Observations a turn produces must stay in the order their calls were
    requested regardless of what this is set to.
    """

    serialize_unsafe_tools: bool = True
    """Run a tool the executor reports as not concurrency-safe on its own.

    Such a call becomes a barrier: nothing else in the turn is in flight
    while it runs, and its safe neighbours still run beside each other.
    ``False`` starts every call at once, which is what this layer did
    before the barrier existed.

    Defaults to the guarded value, matching
    :class:`~omicsclaw.tools.base.ToolPolicy`, whose ``concurrency_safe``
    is ``False`` until a tool's author says otherwise. An executor that
    cannot answer the question makes this setting inert rather than
    pessimistic — see
    :class:`~omicsclaw.engine.executor.ConcurrencyAwareExecutor`.

    **What it costs is liveness, and it compounds with an approval
    pause.** A barrier holds up every later batch in the turn, so a
    barrier call blocked on a human blocks its siblings too — and a
    paused call has no engine-side deadline, so the turn can wait
    indefinitely where before the barrier the siblings would have
    finished. That is the price of not losing an update, and the bound on
    it belongs to whoever posts the approval prompt; see
    :func:`~omicsclaw.engine.executor._paused`.
    """

    generate_retries: int = 3
    """Attempts for one model call, **not** retries on top of one.

    ``1`` therefore disables retrying. This is an application-layer
    budget on top of the SDK's own: a vendor SDK retries only what fails
    before the first byte, so a stream that dies mid-flight — a proxy
    timeout, a 5xx after headers — escapes to this layer, where the
    legacy behaviour was to kill the run and discard the trajectory.
    """

    generate_retry_base: float = 1.0
    """Seconds before the first retry; exponential thereafter."""

    network_retries: int = 6
    """A separate, wider budget for transport-level failures.

    Deliberately not shared with :attr:`generate_retries`. TLS, DNS and
    connection-establishment errors are far more intermittent than a 4xx
    or a 5xx, and the reference harness found the narrow budget could not
    absorb them: three Terminal-Bench tasks hit the same x509 error on
    turn 1 and gave up the turn once ~3s of backoff was exhausted. The
    two budgets are independent — exhausting one does not borrow from the
    other.

    Which failures count as transport-level is
    :data:`~omicsclaw.engine.retry._TRANSPORT_MARKERS`'s to decide, and it
    reads what the *Python* SDKs raise: an ``x509`` error arrives here as
    an ``APIConnectionError`` saying ``Connection error.``, so a
    classifier that went looking for Go's wording would leave this
    setting doing nothing at all.
    """

    network_retry_base: float = 5.0
    """Seconds before the first transport-level retry; exponential after."""

    empty_output_placeholder: str = "[tool completed with no output]"
    """Stands in for a tool result that came back empty.

    Substituted inside the engine, before the message reaches an adapter,
    for two reasons the reference harness records: some backends reject a
    ``tool_result`` with empty content outright with a 400, and even
    where it is accepted, an Observation carrying no information spends a
    whole turn saying nothing. Configurable rather than hard-coded so a
    deployment can phrase it in the language its models are prompted in.
    """

    def with_overrides(self, **overrides: Any) -> EngineConfig:
        """Copy-on-write. The receiver is never mutated.

        Unknown field names raise :exc:`TypeError` rather than being
        dropped: a typo'd ``max_turn=`` that quietly did nothing would
        surface much later as an unexplained stall. ``TypeError`` — and
        not :class:`~omicsclaw.engine.types.EngineError` — because a
        misspelled keyword argument is a mistake at the call site, the
        same one ``EngineConfig(max_turn=1)`` already raises, and it must
        not be catchable alongside genuine run failures.
        """
        unknown = sorted(set(overrides) - set(EngineConfig.__dataclass_fields__))
        if unknown:
            known = ", ".join(sorted(EngineConfig.__dataclass_fields__))
            raise TypeError(
                f"unknown engine configuration field(s): {', '.join(unknown)}"
                f" — known fields are {known}"
            )
        return replace(self, **overrides)


__all__ = ["EngineConfig"]
