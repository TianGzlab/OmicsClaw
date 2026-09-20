"""``omicsclaw/context`` — what a conversation costs, in tokens.

Plan 0030 task A. Every budget decision in this package divides by a
number produced here, so the counting rule is written once, in this
module, and nowhere else: :mod:`~omicsclaw.context.budget`,
:mod:`~omicsclaw.context.prompt` and
:mod:`~omicsclaw.context.compaction` call these functions instead of
growing a second ``len(text) // 4``. The layer this one replaces had
three estimators living side by side, in two different units.

**The rule, and why it is not the reference harness's.** The harness
counts ``len(m.Content) / 4`` (``internal/memory/token.go:15,19-29``),
and Go's ``len`` on a string counts **bytes**. Python's ``len`` counts
code points, so the literal translation is not the same function::

    s = '这是一个中文句子，用于测试 token 估算。'
    len(s)          == 23      # code points — what a naive port counts
    len(s.encode()) == 55      # bytes — what the harness counts
    55 // 4 == 13   vs   23 // 4 == 5

A naive port under-counts Chinese two to three fold, and this
repository's prompts (``SOUL.md``, ``CLAUDE.md``, every ``SKILL.md``)
are Chinese. Under-counting is the dangerous direction: it means
believing there is room, sending the request, and being truncated or
refused by the API. So the harness's *intent* — roughly four ASCII
characters to a token — is re-derived here rather than transliterated::

    tokens(text) = ceil(ascii_chars / 4) + non_ascii_chars

Pure ASCII agrees with the harness to within the rounding, and errs
*above* it where they differ: ``token.go:29`` divides a running total
once, which floors, while this rounds each field up. ``"hello"`` is one
token there and two here. Anything outside ASCII is billed a whole
token per character, which is deliberately pessimistic in the same
direction: a CJK character is usually somewhat less than one token, and
erring above the truth is the only safe error here.

**Accuracy is not claimed. This estimator is UNCALIBRATED.** No
tokenizer was available to measure against (``tiktoken`` is not
installed on the machine this was written on and cannot be installed —
there is no network), so no error figure appears anywhere in this
package. Plan 0030 §11.A-8 carries the debt. A deployment that has a
real tokenizer injects one through :class:`TokenCounter`; nothing here
reaches for ``tiktoken`` on its own, and nothing here changes behaviour
because ``tiktoken`` happens to be installed — a local budget that
silently moves when an optional package appears is not a budget.

**What is counted, per message.** Content, ``reasoning_content``,
``tool_call_id``, ``name``, and for every tool call its id, name and
raw ``arguments``. ``token.go:19-29`` counts content, ``tool_call_id``
and the three parts of a tool call — the two it leaves out are
``reasoning_content`` and ``name``, and it leaves them out because
``internal/schema/message.go:33-63`` has no field for either. This
repository's :class:`~omicsclaw.schema.Message` has both, and ADR 0077
added ``reasoning_content`` on purpose (thinking endpoints reject a
history that has lost it), so copying the harness's field list would
systematically under-count exactly the field this repository went out of
its way to keep.

Each field is estimated and rounded up **separately**, where the harness
sums raw lengths and divides once at the end. Many short fields
therefore cost slightly more here than there — again the safe direction,
and it is what makes "add a field, the estimate grows" true rather than
true-above-four-characters.

**No separate prompt estimator.** The layer this replaces had
``estimate_prompt_tokens(system, messages)``. It is not missing, it is
an addition::

    estimate_text_tokens(system_prompt) + estimate_messages_tokens(msgs)

**Known blind spot: images cost zero.** ``Message.content`` is a
``str`` — ADR 0077 deliberately left multimodal content parts out — so
an image reaching this layer has no representation to count and is
billed nothing. ``CLAUDE.md`` has the Channel Surface routing photos
into tissue-section analysis, so this is reachable, and until the schema
carries image parts the budget is optimistic by roughly a thousand
tokens per picture. **Do not paper over it with a heuristic**: "looks
like base64, add 1300" misfires on ordinary text, which is a worse
failure than the one it treats. Plan 0030 §11.B-11.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message, ToolDefinition

__all__ = [
    "TokenCounter",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_text_tokens",
    "estimate_tool_tokens",
    "format_token_count",
]


@runtime_checkable
class TokenCounter(Protocol):
    """An exact tokenizer, supplied by whoever has one.

    The one seam through which this package will accept a better number
    than it can compute itself. A deployment with ``tiktoken`` or a
    vendor endpoint wraps it in five lines and passes the result to
    every ``counter=`` parameter here; this package never names such a
    package, so installing one changes nothing until a caller decides
    it should.
    """

    def count_text(self, text: str) -> int:
        """Tokens in *text*.

        Must be deterministic: the same string has to return the same
        number every call, or prompt-prefix accounting and the pressure
        tiers both start drifting for no visible reason.
        """
        ...


_ASCII_CHARS_PER_TOKEN = 4
"""Characters to a token for the single-byte half of the text.

The reference harness's ``charsPerToken`` (``token.go:15``) applied to
the unit Python actually has. See the module docstring for why the
figure survives the port and the arithmetic around it does not.
"""


def _count_with(counter: TokenCounter | None) -> Callable[[str], int]:
    """The counting function to use: the injected one, or the estimate."""
    return estimate_text_tokens if counter is None else counter.count_text


def estimate_text_tokens(text: str) -> int:
    """Tokens in one string, by the rule in the module docstring."""
    if not text:
        return 0
    # ``ignore`` drops every character that is not single-byte ASCII, so
    # the length of what survives *is* the ASCII count — at C speed, and
    # without a per-character Python loop over a prompt-sized string.
    ascii_chars = len(text.encode("ascii", "ignore"))
    other_chars = len(text) - ascii_chars
    whole = (ascii_chars + _ASCII_CHARS_PER_TOKEN - 1) // _ASCII_CHARS_PER_TOKEN
    return whole + other_chars


def estimate_message_tokens(
    message: Message,
    *,
    counter: TokenCounter | None = None,
) -> int:
    """Tokens in one history entry, every billable field included.

    ``reasoning_content`` and ``name`` are counted although the
    reference harness counts neither; see the module docstring.
    """
    count = _count_with(counter)
    total = count(message.content) + count(message.reasoning_content)
    total += count(message.tool_call_id) + count(message.name)
    for call in message.tool_calls:
        total += count(call.id) + count(call.name) + count(call.arguments)
    return total


def estimate_messages_tokens(
    messages: Sequence[Message],
    *,
    counter: TokenCounter | None = None,
) -> int:
    """Tokens in a whole conversation: the sum over its messages."""
    return sum(estimate_message_tokens(m, counter=counter) for m in messages)


def _schema_text(input_schema: dict[str, Any]) -> str:
    """One tool's JSON Schema, serialized the same way every call.

    ``sort_keys`` is the point. Python dictionaries keep insertion
    order, so two registries that built the same schema by different
    routes would serialize to different bytes and estimate differently —
    a difference with no cause a reader could ever find. Separators are
    pinned for the same reason and because they are what the harness's
    ``json.Marshal`` emits (``token.go:38``).

    ``ensure_ascii`` is off so a Chinese description is counted by the
    rule at the top of this module rather than inflated into ``\\uXXXX``
    escapes. ``default=str`` keeps an exotic value countable: the
    harness drops a schema it cannot marshal (``token.go:41``, "rather
    under-count than interrupt"), and under-counting is the direction
    this layer refuses to take.
    """
    return json.dumps(
        input_schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def estimate_tool_tokens(
    tools: Sequence[ToolDefinition],
    *,
    counter: TokenCounter | None = None,
) -> int:
    """Tokens the tool definitions cost, before a word is said.

    Ported from ``token.go:33-45``, comment included: tool schemas run
    to 20-30K tokens once there are enough tools, so a preflight that
    ignores them is not a preflight. This repository has 50+ tools
    awaiting migration, which makes this the largest single line in the
    budget rather than a rounding error.
    """
    count = _count_with(counter)
    total = 0
    for tool in tools:
        total += count(tool.name) + count(tool.description)
        total += count(_schema_text(tool.input_schema))
    return total


def format_token_count(n: int) -> str:
    """``45200`` → ``"45.2K"``, ``1200000`` → ``"1.2M"``, ``500`` → ``"500"``.

    Behaviour ported from ``token.go:49-58``; its three-branch ``switch``
    is not, because a ``switch`` is what Go writes an ``if`` chain with.
    """
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
