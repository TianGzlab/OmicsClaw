"""
What every OmicsClaw chat adapter shares, and deliberately little else.

Seven adapters answer seven platforms, and what is common between them is
not a way of sending: it is text chunking that respects a code fence,
per-sender rate limiting, a two-step de-duplication cache, a typing
indicator, and the owner check plus assembly a slash command needs. Each
adapter owns its own transport, its own attribution rule and its own
single-attempt delivery adapter, because those are the places where the
platforms genuinely differ.

**Nothing here sends an answer.** A message becomes an exchange through
:meth:`Channel.inbound` and
:meth:`~omicsclaw.entry.channel.runtime.ChannelRuntime.submit`, and the
answer leaves through that runtime's delivery pump — the one path that
classifies whether a send was accepted. What consistency the adapters have
beyond this module is held by a shared **test**, not by a shared base
class: see ``tests/entry/test_channel_cutover_conformance.py``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from .capabilities import ChannelCapabilities
from .config import BaseChannelConfig

if TYPE_CHECKING:  # pragma: no cover - a type-only import
    from .commands import SlashCommandContext

_logger = logging.getLogger(__name__)


# ─ Text chunking ──────────────────────


def chunk_text(text: str, limit: int) -> list[str]:
    """Split text into chunks that respect logical boundaries and code fences.

    If a code block is split across chunks, each chunk is automatically
    wrapped in its own fences (three backticks) to keep the formatting.

    The per-chunk budget is clamped to at least one character. Without the
    clamp two inputs do not raise but **loop forever**: a limit of zero or
    less, and a limit at or below the twenty characters reserved for the
    fences once the text enters a code block. Both make the budget
    non-positive, the slice empty and the cursor stationary — and this is a
    synchronous loop, so :func:`asyncio.timeout` cannot interrupt it and the
    whole process stops answering, not just the one conversation.
    :class:`~omicsclaw.entry.channel.binding.ChannelSurfaceBinding` refuses
    such a limit outright; the clamp is for the callers that do not go
    through a binding.

    Args:
        text: The text to split.
        limit: Maximum characters per chunk.

    Returns:
        List of text chunks, each <= limit characters.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    in_code_block = False
    code_block_lang = ""

    while remaining:
        # Reserve space for fences if we're inside a code block
        effective_limit = max(1, limit - (20 if in_code_block else 0))

        if len(remaining) <= effective_limit:
            segment = remaining
            best = len(remaining)
        else:
            segment = remaining[:effective_limit]
            best = -1

            if not in_code_block:
                # Paragraph boundary
                pos = segment.rfind("\n\n")
                if pos > 0:
                    best = pos
                # Line boundary
                if best == -1:
                    pos = segment.rfind("\n")
                    if pos > 0:
                        best = pos
                # Word boundary
                if best == -1:
                    pos = segment.rfind(" ")
                    if pos > 0:
                        best = pos
            else:
                # Inside code block: only split at newlines
                pos = segment.rfind("\n")
                if pos > 0:
                    best = pos

            if best == -1:
                best = effective_limit

        chunk_raw = remaining[:best].rstrip()

        # Track code fence state transitions
        starts_in_code = in_code_block
        current_lang = code_block_lang

        fences = list(re.finditer(r"```(\w*)", chunk_raw))
        for f in fences:
            if not in_code_block:
                in_code_block = True
                code_block_lang = f.group(1) or ""
            else:
                in_code_block = False
                code_block_lang = ""

        ends_in_code = in_code_block

        # Add fences if split mid-code-block
        prefix = f"```{current_lang}\n" if starts_in_code else ""
        suffix = "\n```" if ends_in_code else ""

        final_chunk = prefix + chunk_raw + suffix
        if final_chunk.strip():
            chunks.append(final_chunk)

        remaining = remaining[best:].lstrip("\n")

    return chunks


# ─ Dedup cache ───────────────────────


class DedupCache:
    """Bounded ordered cache with TTL for detecting duplicate message IDs."""

    def __init__(
        self,
        max_size: int = 1000,
        trim_to: int = 500,
        ttl_seconds: float = 3600.0,
    ) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._max = max_size
        self._trim = trim_to
        self._ttl = ttl_seconds

    def seen(self, msg_id: str) -> bool:
        """Whether *msg_id* has been recorded, **without recording it**.

        Half of the two-step an ingress needs. Marking a message as seen
        the moment it arrives loses it silently whenever the submission
        that follows fails: the platform redelivers inside the TTL, this
        cache calls the redelivery a duplicate, and the person's message
        is never answered while the log says nothing. Record with
        :meth:`remember` only once the runtime has accepted it.
        """
        if not msg_id:
            return False
        self._prune()
        return msg_id in self._seen

    def remember(self, msg_id: str) -> None:
        """Record *msg_id* as handled. The other half of the two-step."""
        if not msg_id:
            return
        self._prune()
        self._seen[msg_id] = time.monotonic()
        self._seen.move_to_end(msg_id)
        if len(self._seen) > self._max:
            while len(self._seen) > self._trim:
                self._seen.popitem(last=False)

    def is_duplicate(self, msg_id: str) -> bool:
        """Return True if msg_id has been seen before, and record it if not.

        The one-step form, kept for callers that have nothing to fail
        between the check and the record. An ingress is not one of them;
        see :meth:`seen`.
        """
        if self.seen(msg_id):
            self._seen.move_to_end(msg_id)
            self._seen[msg_id] = time.monotonic()
            return True
        self.remember(msg_id)
        return False

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._ttl
        while self._seen:
            key, ts = next(iter(self._seen.items()))
            if ts > cutoff:
                break
            self._seen.popitem(last=False)


# ─ Rate limiter ───────────────────────


class RateLimiter:
    """Per-sender sliding-window rate limiter."""

    def __init__(self, max_per_hour: int = 0):
        self.max_per_hour = max_per_hour
        self._buckets: dict[str, list[float]] = {}

    def check(self, sender_id: str) -> bool:
        """Return True if sender is within rate limits."""
        if self.max_per_hour <= 0:
            return True
        now = time.time()
        bucket = self._buckets.setdefault(sender_id, [])
        bucket[:] = [t for t in bucket if now - t < 3600]
        if len(bucket) >= self.max_per_hour:
            return False
        bucket.append(now)
        return True


# ─ Typing indicator manager ───────────────────


class TypingManager:
    """Manages background typing-indicator loops per chat_id."""

    def __init__(
        self,
        send_action,
        interval: float = 5.0,
    ) -> None:
        self._send_action = send_action
        self._interval = interval
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, chat_id: str) -> None:
        await self.stop(chat_id)

        async def _loop() -> None:
            while True:
                try:
                    await self._send_action(chat_id)
                except Exception:
                    pass
                await asyncio.sleep(self._interval)

        self._tasks[chat_id] = asyncio.create_task(_loop())

    async def stop(self, chat_id: str) -> None:
        task = self._tasks.pop(chat_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def stop_all(self) -> None:
        for cid in list(self._tasks):
            await self.stop(cid)


# ─ Channel ABC ───────────────────────


class Channel(ABC):
    """Abstract base class for OmicsClaw messaging channels.

    Subclasses must implement:
    - prepare_control_binding() — authenticate and describe the account
    - start()                   — begin receiving provider events
    - stop()                    — clean shutdown

    Subclasses may optionally override:
    - _send_typing()      — send a typing indicator
    - _is_admin()         — check admin status
    - _owner_subjects()   — add an owner source the shared config has no
      field for, or normalise the platform's spelling of an identity

    **There is one way in and one way out, and no class here provides
    either.** A message becomes an exchange by being normalised with
    :meth:`inbound` and handed to
    :meth:`~omicsclaw.entry.channel.runtime.ChannelRuntime.submit`; the
    answer leaves through that runtime's delivery pump, which is the only
    thing that classifies whether a send was accepted. A channel that grew
    a ``send`` of its own would be a second outbound path nothing could
    account for, which is why there is no longer one to override.

    The two exceptions are direct, unclassified provider calls that carry
    no answer: :meth:`send_command_output` for a slash command's listing,
    and a typing hint. Both are things a person can ask for again.

    **Outbound media is closed rather than missing.** Several adapters had
    a working ``send_media`` and none of them had a caller, because nothing
    in this layer names an artefact in a way an outbound path could
    resolve. Reopening it means answering "which file", not writing an
    upload.

    Subclasses should set ``name`` to a unique identifier (e.g. "telegram")
    and may set ``authoritative_ingress`` only after a verified
    ChannelRuntime plus single-attempt Delivery cutover.
    """

    name: str = "base"
    capabilities: ChannelCapabilities = ChannelCapabilities()
    authoritative_ingress: bool = False

    def __init__(self, config: BaseChannelConfig | None = None):
        self.config = config or BaseChannelConfig()
        self._running = False
        self._ingress_active = False
        # Set by `bind_control_runtime`; a cut-over Channel never composes its own.
        self._control_runtime = None
        self._control_loop = None
        # Makes each command's delivery item id unique within this process,
        # which is what keeps a platform that deduplicates by it (Feishu does,
        # for an hour) from swallowing the second `/skills` of a session.
        self._command_ordinal = 0
        self._dedup = DedupCache()
        self._rate_limiter = RateLimiter(
            max_per_hour=self.config.rate_limit_per_hour,
        )
        # Typing indicator manager (channels override _send_typing)
        self._typing_manager = TypingManager(
            self._send_typing,
            interval=5.0,
        )

    # ─ Lifecycle ──────────────────────

    @property
    def ingress_active(self) -> bool:
        """Whether provider callbacks may submit novel inbound Turns."""

        return self._ingress_active

    def activate_ingress(self) -> None:
        """Open ingress after the manager's all-Channel startup barrier."""

        if not self._running:
            raise RuntimeError(
                f"Channel '{self.name}' cannot activate ingress while stopped"
            )
        self._ingress_active = True

    def deactivate_ingress(self) -> None:
        """Close ingress synchronously before transport shutdown begins."""

        self._ingress_active = False

    async def prepare_control_binding(self):
        """Phase 1: connect to the provider and describe this Channel's binding.

        Several Channels in one process share one
        :class:`~omicsclaw.entry.session.SessionRegistry`, so the composition
        root must live above every Channel — two registries would be two sets
        of conversations for one person. Startup is therefore two-phase:

        1. every cut-over Channel authenticates far enough to name its account
           namespace and build its single-attempt Delivery Adapter, and returns
           a :class:`~omicsclaw.entry.channel.binding.ChannelSurfaceBinding`;
        2. the runner composes one shared
           :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime` from all
           bindings, starts it, calls :meth:`bind_control_runtime`, then calls
           :meth:`start`.

        A legacy Channel returns ``None`` and is rejected before this point.
        """

        return None

    def bind_control_runtime(self, runtime, *, loop=None) -> None:
        """Phase 1.5: adopt the shared runtime the runner composed and started.

        ``loop`` is the event loop the runtime lives on. A Channel whose
        provider SDK delivers events on its own thread must submit to THAT
        loop; asyncio primitives belong to the loop that created them.
        """

        self._control_runtime = runtime
        self._control_loop = loop

    @abstractmethod
    async def start(self) -> None:
        """Phase 2: begin receiving provider events.

        A cut-over Channel may assume :meth:`bind_control_runtime` already ran.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        ...

    async def run(self) -> None:
        """Start the channel and run until stopped.

        A cut-over Channel cannot be started this way: :meth:`start` requires
        a :class:`~omicsclaw.entry.channel.runtime.ChannelRuntime` that only
        the composition root can build, because every Channel in the process
        shares one. Calling this would fail deep inside :meth:`start` with a
        message about an unbound runtime, so it refuses up front and names
        what to do instead.
        """

        self.require_authoritative_ingress()
        raise RuntimeError(
            f"Channel '{self.name}' must be started by the runner that owns "
            "the shared ChannelRuntime: compose one with "
            "ChannelRuntime.for_channel_surfaces(app, bindings=...), bind it "
            "into every Channel, then start them through ChannelManager"
        )

    def require_authoritative_ingress(self) -> None:
        """Block legacy direct-dispatch Adapters from production startup."""

        if not self.authoritative_ingress:
            raise RuntimeError(
                f"Channel '{self.name}' is disabled until its ChannelRuntime "
                "and single-attempt Delivery Adapter cutover is implemented"
            )

    # ─ Sending ───────────────────────

    # ─ Formatting ──────────────────────

    @staticmethod
    def strip_markup(text: str) -> str:
        """Remove common markup for plain-text fallback."""
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        text = re.sub(r"_(.*?)_", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)
        return text

    # ─ Typing indicator ────────────────────

    async def _send_typing(self, chat_id: str) -> None:
        """Send a single typing indicator. Override in sub-classes."""
        pass

    async def start_typing(self, chat_id: str) -> None:
        """Start a background typing indicator loop."""
        if self.capabilities.typing:
            await self._typing_manager.start(chat_id)

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        await self._typing_manager.stop(chat_id)

    # ─ Dedup and rate limiting ──────────────────

    def is_duplicate(self, message_id: str) -> bool:
        """Check if a message ID is a duplicate."""
        return self._dedup.is_duplicate(message_id)

    def seen_before(self, message_id: str) -> bool:
        """Whether this message was already handled — a read, not a mark.

        An optimisation only. The authority on idempotency is the runtime's
        own ``source_request_id`` bookkeeping, which resolves a redelivery
        to the exchange it already started; this saves rebuilding an obvious
        repeat. It must stay a read: pair it with :meth:`remember_message`
        **after** the runtime has accepted, or a submission that fails plus
        a redelivery inside the cache's TTL loses the message with no trace.
        """
        return self._dedup.seen(message_id)

    def remember_message(self, message_id: str) -> None:
        """Record a message, once the runtime has accepted it."""
        self._dedup.remember(message_id)

    def check_rate_limit(self, sender_id: str) -> bool:
        """Check if sender is within rate limits."""
        return self._rate_limiter.check(sender_id)

    def _is_admin(self, sender_id: str) -> bool:
        """Check if sender is an admin (bypasses rate limits). Override as needed."""
        return False

    # ─ Who may drive this bot ──────────────────

    def _owner_subjects(self) -> frozenset[str]:
        """The sender ids this deployment admits, in the platform's spelling.

        The configured allowlist, trimmed, with blanks dropped so that a
        stray comma in ``*_ALLOWED_SENDERS`` cannot become an id that an
        empty sender matches.

        Defined once here because every adapter needs the same answer and an
        adapter that computed it differently would disagree with the
        :class:`~omicsclaw.entry.ingress.SenderPolicy` built from the same
        config. Override to add a source the config holds elsewhere — not to
        widen the set.
        """
        return frozenset(
            str(value).strip()
            for value in (self.config.allowed_senders or set())
            if str(value).strip()
        )

    def _is_owner(self, subject: str | None) -> bool:
        """Whether *subject* may drive this agent. Deny by default.

        The single way to ask, so that a gate cannot be written twice and
        get two answers. An empty allowlist admits nobody — matching
        :class:`~omicsclaw.entry.ingress.SenderPolicy`, which refuses to be
        constructed from one at all — and an empty or unknown sender is
        never an owner.

        Override alongside :meth:`_owner_subjects` when a platform's
        identities need normalising before they can be compared.
        """
        owners = self._owner_subjects()
        if not owners:
            return False
        candidate = str(subject or "").strip()
        return bool(candidate) and candidate in owners

    def session_id(self, chat_id: str, *, platform: str = "") -> str:
        """The conversation key one chat maps to. Stable, and per chat.

        Per *chat*, not per person: a group's history belongs to the group,
        and two people in one chat are continuing one conversation. The
        surface prefix keeps a Telegram chat ``42`` and a Feishu chat ``42``
        apart in one process, since the registry keys history by this string
        alone (plan 0031 Q6).
        """
        return f"{platform or self.name}:{chat_id}"

    async def answer_slash_command(
        self,
        reply_target: dict[str, Any],
        chat_id: str,
        user_id: str | None,
        text: str,
    ) -> bool:
        """Answer a registered slash command; report whether it was one.

        ``False`` means the text only looked like a command. An unregistered
        ``/verb`` is ordinary text and belongs to the model — that is
        :func:`~omicsclaw.entry.channel.commands.dispatch`'s own contract,
        and an adapter that answered "unknown command" instead would make a
        typo unanswerable.

        Shared across adapters because the failure of getting it wrong is
        invisible: a command that reaches the model produces a fluent
        paragraph about the word the person typed, and their conversation is
        still exactly where it was.

        **Only an owner is answered, and the check is here rather than in
        each adapter** because this path reaches neither the rate limiter
        nor the ingress gate that would otherwise apply it: a command is
        answered by a direct provider call, so an adapter that forgot the
        check would hand any stranger who can message the bot the workspace
        listings ``/files``, ``/outputs`` and ``/recent`` return.

        A refused command is logged and answered with nothing, which is what
        ingress does with a refused message: a reply would tell an unknown
        sender both that this bot exists and that their id was checked
        against a list. It still reports ``True`` — the text was a command
        and is finished with — so that a refusal cannot fall through to the
        model instead.
        """
        from .commands import dispatch

        if not self._is_owner(user_id):
            _logger.warning(
                "ignored a %s command from a sender outside the allowlist",
                self.name,
            )
            return True

        # The verb alone. An argument can carry a subject identifier, and a
        # traceback is written wherever an operator points this logger.
        verb = text.split(maxsplit=1)[0] if text.strip() else ""
        try:
            reply = await dispatch(self.command_context(chat_id, user_id, text))
        except Exception:
            _logger.exception("%s command %s failed", self.name, verb)
            await self.send_command_output(reply_target, "That command failed.")
            return True
        if reply is None:
            return False
        await self.send_command_output(reply_target, reply or "Nothing to show.")
        return True

    async def send_command_output(
        self,
        reply_target: dict[str, Any],
        text: str,
    ) -> None:
        """Put one slash command's answer in front of the person, and stop.

        A direct provider call per chunk, made through the same delivery
        adapter the reply pump uses, with **no retry and no acceptance
        classification**. Command output is a listing the person just asked
        for: if it does not arrive they ask again, which is not true of an
        analysis that took a minute to produce. That is the whole reason an
        answer may not travel this way.

        A failure is logged rather than raised: this runs inside a provider
        callback, where an exception reaches the platform's SDK and not the
        person.
        """
        runtime = self._control_runtime
        binding = runtime.binding(self.name) if runtime is not None else None
        if binding is None:
            _logger.warning("%s command output dropped: no binding", self.name)
            return
        from .delivery import DeliveryAttemptOutcome, DeliveryAttemptRequest

        self._command_ordinal += 1
        for index, chunk in enumerate(chunk_text(text, binding.text_chunk_limit)):
            if not chunk.strip():
                continue
            result = await binding.delivery_adapter(
                DeliveryAttemptRequest(
                    item_id=f"cmd-{self._command_ordinal}-{index}",
                    text=chunk,
                    reply_target=reply_target,
                )
            )
            if result.outcome is not DeliveryAttemptOutcome.ACCEPTED:
                _logger.warning(
                    "%s command output ended %s", self.name, result.outcome.value
                )
                return

    def command_context(
        self,
        chat_id: str,
        user_id: str | None,
        text: str,
    ) -> "SlashCommandContext":
        """Assemble the request-scoped half of a slash command.

        The deployment-scoped half — skills, tools, provider, workspace — is
        the app the bound runtime holds, so a channel that is not yet bound
        can still dispatch the static commands and every other handler
        answers that the deployment is unavailable.

        Shared rather than copied per adapter because of one field:
        ``session_id`` is what ``/clear`` and ``/compact`` act on, and
        omitting it raises nothing. It defaults to the empty string, which
        those two handlers read as "there is no conversation" — so an
        adapter that forgot it would report success at clearing nothing.

        This builds the context and no more. Whether the text *is* a command
        is :func:`~omicsclaw.entry.channel.commands.dispatch`'s question, and
        how the answer reaches the person is the adapter's: command output is
        a short direct send, not an exchange reply, so it does not travel
        through the delivery pump and needs no acceptance classification.
        """
        from .commands import SlashCommandContext

        runtime = self._control_runtime
        app = runtime.app if runtime is not None else None
        return SlashCommandContext(
            chat_id=chat_id,
            user_id=user_id,
            platform=self.name,
            user_text=text,
            workspace=str(app.config.workspace) if app is not None else "",
            app=app,
            session_id=self.session_id(chat_id),
        )

    def inbound(
        self,
        chat_id: str,
        user_id: str,
        text: str,
        *,
        source_request_id: str,
        platform: str = "",
        reply_target: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
    ) -> Any:
        """Normalise one platform message into the shape ingress admits.

        The single place a channel builds an
        :class:`~omicsclaw.entry.ingress.InboundMessage`, so that the fields
        the security gates read — ``sender``, ``surface``, and the chat kind
        and mentions under ``values`` — cannot be filled in three different
        ways by three adapters.

        ``source_request_id`` is required for the reason the field is:
        redelivery is the normal case on every IM platform, and a message
        without an idempotency key is answered twice the first time a
        provider retries.
        """
        from omicsclaw.entry.ingress import InboundMessage
        from .runtime import VALUE_REPLY_TARGET

        facts: dict[str, Any] = dict(values or {})
        if reply_target is not None:
            facts[VALUE_REPLY_TARGET] = reply_target
        return InboundMessage(
            text=text,
            session_id=self.session_id(chat_id, platform=platform),
            source_request_id=source_request_id,
            sender=str(user_id),
            surface=platform or self.name,
            values=facts,
        )
