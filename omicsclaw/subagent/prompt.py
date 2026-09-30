"""The system prompt a delegated run opens with."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

__all__ = ["ChildPrompt", "SkillLoader"]

SkillLoader = Callable[[str], str]
"""Returns one skill's body by name. May raise; the caller skips it then."""


@dataclass(frozen=True, slots=True)
class ChildPrompt:
    """A sub-agent's instructions plus the facts about where it is running.

    Satisfies both halves of the engine's prompt seam: ``render()``
    returns the object itself and :attr:`system_prompt` is the text, so
    an engine can be handed one of these directly with no adapter.

    The text is assembled on every :attr:`system_prompt` read, which is
    once per delegated run.
    """

    instructions: str
    """The sub-agent's own system prompt."""

    workspace: str = ""
    """Absolute path the sub-agent works in. Omitted from the text when
    empty."""

    environment: str = ""
    """Where the tools actually execute — container, degraded host, or
    nothing at all. Must be the same description the parent was given:
    a sub-agent reuses the parent's ``bash``, so a wrong one here tells it
    the blast radius of every command is somewhere it is not."""

    skills: tuple[str, ...] = ()
    """Skill names to append in full, in this order."""

    loader: SkillLoader | None = field(default=None, compare=False)
    """Fetches the skill bodies. ``None`` skips :attr:`skills` entirely."""

    def render(self) -> "ChildPrompt":
        """Return this prompt as its own render."""
        return self

    @property
    def system_prompt(self) -> str:
        """The assembled text: instructions, workspace, environment, skills.

        A skill whose body cannot be loaded is left out rather than
        raising: a missing reference is worth less than the delegation it
        would otherwise cancel.
        """
        blocks = [self.instructions.strip()]
        if self.workspace:
            blocks.append(f"## Working directory\n\n{self.workspace}")
        if self.environment.strip():
            blocks.append(self.environment.strip())
        blocks.extend(self._skill_blocks())
        return "\n\n".join(block for block in blocks if block)

    def _skill_blocks(self) -> list[str]:
        """The preloaded skill bodies, skipping the ones that will not load."""
        if self.loader is None:
            return []
        blocks: list[str] = []
        for name in self.skills:
            try:
                body = self.loader(name)
            except Exception:  # noqa: BLE001 — see system_prompt
                continue
            if body.strip():
                blocks.append(f"## Skill: {name}\n\n{body.strip()}")
        return blocks
