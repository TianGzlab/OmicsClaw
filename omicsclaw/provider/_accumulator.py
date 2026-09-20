"""Streaming tool-call reassembly, shared by every adapter.

Both OpenAI and Anthropic split a single tool call across several stream
chunks::

    first chunk      — id and name arrive (the call begins)
    later chunks     — fragments of the arguments JSON

The adapter has to stitch those back into one
:class:`~omicsclaw.schema.ToolCall`. The logic is identical for both
vendors, so it lives here once rather than being written twice and
drifting.

Nothing accumulated here is observable until :meth:`ToolCallAccumulators.finalize`
runs. That is deliberate: a half-arrived arguments string is not valid
JSON, and exposing it would let a consumer act on a call the model has
not finished asking for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from omicsclaw.schema import ToolCall


@dataclass(slots=True)
class _Accumulator:
    """Fragments of one in-flight tool call."""

    id: str = ""
    name: str = ""
    fragments: list[str] = field(default_factory=list)

    def arguments(self) -> str:
        """Join once at the end rather than concatenating per fragment."""
        return "".join(self.fragments)


class ToolCallAccumulators:
    """Per-index accumulators for one stream.

    A turn may request several tools at once, so each is isolated by the
    stream index the vendor assigns it.
    """

    __slots__ = ("_by_index",)

    def __init__(self) -> None:
        self._by_index: dict[int, _Accumulator] = {}

    def __len__(self) -> int:
        return len(self._by_index)

    def __bool__(self) -> bool:
        return bool(self._by_index)

    def _get(self, index: int) -> _Accumulator:
        accumulator = self._by_index.get(index)
        if accumulator is None:
            accumulator = _Accumulator()
            self._by_index[index] = accumulator
        return accumulator

    def start(self, index: int, call_id: str, name: str) -> None:
        """Record the id and name that open a tool call.

        Tolerates being called more than once for an index — some
        backends repeat the id on continuation chunks — and ignores empty
        values so a repeat cannot blank out what the opening chunk set.
        """
        accumulator = self._get(index)
        if call_id:
            accumulator.id = call_id
        if name:
            accumulator.name = name

    def append_arguments(self, index: int, fragment: str) -> None:
        """Append one fragment of the arguments JSON."""
        if fragment:
            self._get(index).fragments.append(fragment)

    def finalize(self) -> tuple[ToolCall, ...]:
        """Reassemble every accumulated call, ordered by stream index.

        **Iterate the actual keys — never ``range(len(self))``.** Vendor
        indices are not guaranteed to start at 0 or be contiguous: in an
        Anthropic stream the index is the *content block* position, so
        with extended thinking enabled (or any leading text) the
        ``thinking`` / ``text`` block takes index 0 and ``tool_use``
        blocks begin at 1. The key set is then ``{1, 2, 3}``, and a
        positional loop finds nothing at 0, stops early, and **silently
        drops the model's last tool call** — the run continues, minus an
        action nobody knows was requested. The reference harness carries
        an explicit fix note for exactly this bug.

        Empty arguments become ``"{}"`` so the schema's invariant — that
        ``arguments`` is always parseable JSON text — holds even for a
        no-argument tool.
        """
        return tuple(
            ToolCall(
                id=accumulator.id,
                name=accumulator.name,
                arguments=accumulator.arguments() or "{}",
            )
            for _, accumulator in sorted(self._by_index.items())
        )


__all__ = ["ToolCallAccumulators"]
