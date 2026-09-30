"""Model calls of the tuning pipeline: the K decision and stage-1 proposals.

The model is any object with ``name`` and ``async generate(messages,
tools=None)`` returning something with ``.message`` (a
:class:`~omicsclaw.schema.Message`) and ``.usage``
(:class:`~omicsclaw.schema.Usage`). A model that also has
``generate_for(purpose, messages)`` is called through that instead, which is
how the scripted and replaying models know what a call is for.

Every call is written in full to the ledger's ``llm/`` directory and
summarised as an ``llm_call`` event. A decision may be retried at most
:data:`RETRIES` times after invalid replies; a model error ends it at once.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from omicsclaw.ensemble.tuning.ledger import Ledger, utc_now
from omicsclaw.ensemble.tuning.prompts import (
    KDecision,
    KDecisionInput,
    ProposeInput,
    ReplyError,
    marker_catalogue,
    parse_json_reply,
    render_k_decision,
    render_k_followup,
    render_propose,
    template_sha256,
    validate_k_reply,
    validate_proposal_batch,
)
from omicsclaw.schema import Message, Role, Usage

__all__ = [
    "CassetteChatModel",
    "CassetteMiss",
    "ChatModel",
    "KOutcome",
    "LLMSettings",
    "ProposeOutcome",
    "RETRIES",
    "ScriptedChatModel",
    "decide_k",
    "prompt_sha256",
    "propose",
]

RETRIES = 2
"""Invalid replies a decision may retry after."""


class ChatModel(Protocol):
    """The part of a provider the tuning pipeline uses."""

    @property
    def name(self) -> str: ...

    async def generate(self, messages: Sequence[Message], tools: Any = None) -> Any: ...


@dataclass(frozen=True)
class LLMSettings:
    """What is recorded about the model with every call."""

    model: str
    provider: str
    temperature: float | None = None
    max_tokens: int | None = None
    thinking_budget: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": self.provider,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "thinking_budget": self.thinking_budget,
        }


def prompt_sha256(messages: Sequence[Message]) -> str:
    """sha256 over the roles and contents of *messages*."""
    payload = json.dumps([[str(m.role), m.content] for m in messages], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _usage(value: Any) -> dict[str, int]:
    usage = value if isinstance(value, Usage) else Usage()
    return {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_read": usage.cache_read_tokens,
        "cache_write": usage.cache_write_tokens,
    }


async def _generate(model: Any, purpose: str, messages: Sequence[Message]) -> Any:
    special = getattr(model, "generate_for", None)
    if special is not None:
        return await special(purpose, list(messages))
    return await model.generate(list(messages))


@dataclass
class _Call:
    reply: Message | None
    text: str
    error: str
    path: str


async def _ask(
    model: Any,
    messages: Sequence[Message],
    *,
    purpose: str,
    template: str,
    attempt: int,
    settings: LLMSettings,
    ledger: Ledger,
    check: Callable[[str], str],
) -> _Call:
    """One model call, validated by *check* (returns ``""`` or an error), recorded."""
    started = utc_now()
    began = time.monotonic()
    error = ""
    reply: Message | None = None
    usage: dict[str, int] = _usage(None)
    try:
        completion = await _generate(model, purpose, messages)
        reply = completion.message
        usage = _usage(getattr(completion, "usage", None))
    except CassetteMiss:
        raise
    except Exception as exc:  # noqa: BLE001 - any model failure ends the decision
        error = f"{type(exc).__name__}: {exc}"
    latency = round(time.monotonic() - began, 3)
    text = reply.content if reply is not None else ""
    validation = "" if error else check(text)
    record = {
        "purpose": purpose,
        "attempt": attempt,
        "settings": settings.to_json(),
        "started_at": started,
        "latency_s": latency,
        "usage": usage,
        "template": template,
        "template_sha256": template_sha256().get(template),
        "prompt_sha256": prompt_sha256(messages),
        "messages": [{"role": str(m.role), "content": m.content} for m in messages],
        "reply": text,
        "reasoning": reply.reasoning_content if reply is not None else "",
        "reply_sha256": _sha(text),
        "provider_error": error,
        "validation": validation or "ok",
    }
    path = ledger.record_llm(record)
    ledger.append(
        "llm_call",
        purpose=purpose,
        attempt=attempt,
        path=path,
        provider_error=error,
        validation=validation or ("ok" if not error else "provider_error"),
        latency_s=latency,
        usage=usage,
        prompt_sha256=record["prompt_sha256"],
        reply_sha256=record["reply_sha256"],
        template_sha256=record["template_sha256"],
        **settings.to_json(),
    )
    return _Call(reply=reply, text=text, error=error or validation, path=path)


# ---- the K decision -------------------------------------------------------------------------


@dataclass
class KOutcome:
    """How the K decision ended.

    ``decision`` is ``None`` when the model failed or ran out of retries;
    the caller then falls back.
    """

    decision: KDecision | None
    requested: list[int] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    retries: int = 0
    failure: str = ""
    followup_markers: Mapping[str, Any] | None = None


async def decide_k(
    model: Any,
    inp: KDecisionInput,
    *,
    settings: LLMSettings,
    ledger: Ledger,
    fetch_markers: Callable[[list[int]], Awaitable[Mapping[str, Any]]],
    retries: int = RETRIES,
) -> KOutcome:
    """Ask for K, with at most one marker request and *retries* retries over both steps.

    :param fetch_markers: Given the requested K, returns a markers document
        with their full blocks and the nesting over the stable peaks and them.
    :raises LeakError: An injected field states a count of regions (before any call).
    """
    first = render_k_decision(inp)
    messages: list[Message] = [Message.user(first)]
    shown = marker_catalogue(inp.markers, inp.evidence.stable_peaks)
    skill_text = inp.skill.text
    outcome = KOutcome(decision=None)
    may_request = True
    parsed: dict[str, Any] = {}

    def check(text: str) -> str:
        parsed.clear()
        try:
            value = validate_k_reply(
                parse_json_reply(text), grid=inp.grid, stable_peaks=inp.evidence.stable_peaks,
                shown=shown, skill_text=skill_text, may_request=may_request,
            )
        except ReplyError as exc:
            return str(exc)
        parsed["value"] = value
        return ""

    attempt = 0
    while True:
        call = await _ask(model, messages, purpose="k_decision", template="k_decision.txt", attempt=attempt,
                          settings=settings, ledger=ledger, check=check)
        outcome.calls.append(call.path)
        if call.reply is None:
            outcome.failure = call.error
            return outcome
        value = parsed.get("value")
        if value is None:
            outcome.retries += 1
            if outcome.retries > retries:
                outcome.failure = f"no valid decision after {retries} retries: {call.error}"
                return outcome
            messages += [call.reply, Message.user(
                f"Your reply was not valid: {call.error}. Reply again with one JSON object."
            )]
            attempt += 1
            continue
        if isinstance(value, list):
            outcome.requested = value
            may_request = False
            extra = await fetch_markers(value)
            outcome.followup_markers = extra
            shown.update(marker_catalogue(extra, value))
            messages += [call.reply, Message.user(render_k_followup(inp, value, extra))]
            attempt += 1
            continue
        outcome.decision = value
        return outcome


# ---- stage-1 proposals ----------------------------------------------------------------------------


@dataclass
class ProposeOutcome:
    """The proposals that passed, and what happened to the rest.

    ``accepted`` holds ``(params, why)``; ``dropped`` ``(params, reason)``.
    ``failure`` is set when no batch could be read at all.
    """

    accepted: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    dropped: list[tuple[Any, str]] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    retries: int = 0
    failure: str = ""


async def propose(
    model: Any,
    inp: ProposeInput,
    *,
    settings: LLMSettings,
    ledger: Ledger,
    accept: Callable[[Any], tuple[dict[str, Any] | None, str]],
    count: int = 3,
    retries: int = RETRIES,
) -> ProposeOutcome:
    """Ask for *count* parameter settings.

    Each proposed setting goes through *accept*, which returns the setting to
    run or ``None`` and a reason; a refused setting is dropped without a
    retry. Only a reply that cannot be read as a batch is retried.

    :raises LeakError: An injected field states a count of regions (before any call).
    """
    text = render_propose(inp)
    messages: list[Message] = [Message.user(text)]
    outcome = ProposeOutcome()
    batch: list[tuple[Any, str]] = []

    def check(reply_text: str) -> str:
        batch.clear()
        try:
            batch.extend(validate_proposal_batch(parse_json_reply(reply_text)))
        except ReplyError as exc:
            return str(exc)
        return ""

    attempt = 0
    while True:
        call = await _ask(model, messages, purpose=f"propose:{inp.method}", template="propose.txt",
                          attempt=attempt, settings=settings, ledger=ledger, check=check)
        outcome.calls.append(call.path)
        if call.reply is None:
            outcome.failure = call.error
            return outcome
        if call.error:
            outcome.retries += 1
            if outcome.retries > retries:
                outcome.failure = f"no readable batch after {retries} retries: {call.error}"
                return outcome
            messages += [call.reply, Message.user(
                f"Your reply was not valid: {call.error}. Reply again with one JSON object."
            )]
            attempt += 1
            continue
        for params, why in batch[:count]:
            accepted, reason = accept(params)
            if accepted is None:
                outcome.dropped.append((params, reason))
            else:
                outcome.accepted.append((accepted, why))
        for params, _ in batch[count:]:
            outcome.dropped.append((params, f"more than {count} settings"))
        return outcome


# ---- test and replay models -------------------------------------------------------------------------


@dataclass
class _Completion:
    message: Message
    usage: Usage = field(default_factory=Usage)


class ScriptedChatModel:
    """Replies from per-purpose queues; records every prompt it receives.

    :param replies: ``{purpose: [text or Exception, ...]}``; a purpose
        ``"propose:*"`` serves any proposal purpose without its own queue.
    """

    def __init__(self, replies: Mapping[str, Sequence[Any]], *, name: str = "scripted") -> None:
        self._queues = {purpose: list(items) for purpose, items in replies.items()}
        self._name = name
        self.calls: list[tuple[str, list[Message]]] = []

    @property
    def name(self) -> str:
        return self._name

    async def generate(self, messages: Sequence[Message], tools: Any = None) -> Any:
        return await self.generate_for("", messages)

    async def generate_for(self, purpose: str, messages: Sequence[Message]) -> Any:
        self.calls.append((purpose, list(messages)))
        queue = self._queues.get(purpose)
        if queue is None and purpose.startswith("propose:"):
            queue = self._queues.get("propose:*")
        if not queue:
            raise RuntimeError(f"no scripted reply left for {purpose!r}")
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Completion(Message(role=Role.ASSISTANT, content=str(item)), Usage(input_tokens=10, output_tokens=5))

    def count(self, purpose: str) -> int:
        return sum(1 for p, _ in self.calls if p == purpose or (purpose.endswith("*") and p.startswith(purpose[:-1])))


class CassetteMiss(LookupError):
    """A replayed call whose purpose and prompt were not recorded."""


class CassetteChatModel:
    """Replays recorded replies by purpose and prompt sha256.

    Built from the ``llm/`` records of an earlier run (:meth:`from_ledger`),
    so a run can be replayed from its own ledger.
    """

    def __init__(self, entries: Mapping[tuple[str, str], str], *, name: str = "cassette") -> None:
        self._entries = dict(entries)
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @classmethod
    def from_ledger(cls, directory: Path) -> "CassetteChatModel":
        entries: dict[tuple[str, str], str] = {}
        for path in sorted((Path(directory) / "llm").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("provider_error"):
                continue
            entries[(record["purpose"], record["prompt_sha256"])] = record["reply"]
        return cls(entries)

    async def generate(self, messages: Sequence[Message], tools: Any = None) -> Any:
        raise CassetteMiss("a cassette replays only calls with a purpose")

    async def generate_for(self, purpose: str, messages: Sequence[Message]) -> Any:
        key = (purpose, prompt_sha256(messages))
        if key not in self._entries:
            raise CassetteMiss(f"no recorded reply for {purpose!r} with prompt {key[1][:12]}")
        return _Completion(Message(role=Role.ASSISTANT, content=self._entries[key]))
