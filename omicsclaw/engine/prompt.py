"""The seam through which the loop asks for the prompt it opens with.

Plan 0027 §12.4.1. The loop has never assembled a system prompt and
still does not: what changes is the direction of the arrow. Until now a
caller rendered one, spliced it in front of a conversation and handed the
result to :meth:`~omicsclaw.engine.loop.AgentEngine.run`; an engine given
a :class:`PromptSource` asks for the render itself, once per exchange,
and so owns the one ordering rule that matters — the system message is
message zero and there is exactly one of it.

**Two Protocols rather than one method returning ``str``.** The narrower
spelling — ``system_prompt() -> str`` — would force every renderer worth
using through an adapter, and the adapter would drop everything the
render carries besides the text: section statistics, token estimates, the
answer to "which block is eating the window". Those belong to whoever
rendered them, and a layer that cannot read them should also not be able
to destroy them. Returning the renderer's own object passes them through
untouched, and lets a structural implementation satisfy this seam with no
adapter at all.

This module imports :mod:`typing` and nothing else — not even
:mod:`omicsclaw.schema`. A prompt is text until the engine makes it a
message, and that conversion is the engine's business.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["PromptSource", "RenderedPrompt"]


@runtime_checkable
class RenderedPrompt(Protocol):
    """One render of a system prompt, as its renderer hands it over.

    The engine reads a single member and copies nothing else, so an
    implementation is free to carry as much diagnostic weight beside it
    as it likes — this Protocol is a floor, not a shape.

    Reachable afterwards as
    :attr:`~omicsclaw.engine.types.RunResult.prompt`, which is how a
    caller reads the statistics of the render its exchange actually used
    instead of rendering a second time and hoping the two agree.
    """

    @property
    def system_prompt(self) -> str:
        """The one string that becomes message zero of an exchange."""
        ...


@runtime_checkable
class PromptSource(Protocol):
    """Renders the system prompt an exchange opens with."""

    def render(self) -> RenderedPrompt:
        """Render the prompt as it stands *now*.

        Called **once per exchange**, before the first model call and
        never again inside it. Once per turn would let an edit to a
        prompt file change the persona halfway through a single exchange
        — and would re-read those files once per turn for the privilege.

        Synchronous, matching the renderers that exist: assembling a
        prompt is reading files and joining strings. An implementation
        that genuinely needs to await something should do that work
        before the exchange and render from what it already holds.

        :raises Exception: Propagates out of the exchange. A prompt that
            could not be rendered is not a prompt worth guessing at —
            the run would proceed under a persona nobody wrote.
        """
        ...
