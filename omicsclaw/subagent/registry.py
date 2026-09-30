"""The sub-agents one deployment offers, keyed by name."""

from __future__ import annotations

from typing import Iterable, Iterator

from .definition import SubAgentDefinition

__all__ = ["SubAgentRegistry"]


class SubAgentRegistry:
    """An ordered set of sub-agent definitions.

    Filled at start-up and read on every ``task`` call. Order is
    registration order and is what the tool's ``subagent_type`` enum is
    built from, so it is stable between turns.

    Not thread-safe: registration happens before any turn runs.
    """

    __slots__ = ("_definitions",)

    def __init__(self, definitions: Iterable[SubAgentDefinition] = ()) -> None:
        self._definitions: dict[str, SubAgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: SubAgentDefinition) -> None:
        """Mount *definition*, replacing any namesake **in place**.

        :raises ~omicsclaw.subagent.definition.InvalidDefinition: the
            definition does not validate.

        Replacing rather than refusing is what lets a file in the agents
        directory override a built-in of the same name; keeping the
        original position means doing so does not reorder the enum the
        model is shown.
        """
        definition.validate()
        self._definitions[definition.name] = definition

    def get(self, name: str) -> SubAgentDefinition | None:
        """The definition mounted under *name*, or ``None``."""
        return self._definitions.get(name)

    def list(self) -> tuple[SubAgentDefinition, ...]:
        """Every definition, in registration order."""
        return tuple(self._definitions.values())

    def names(self) -> tuple[str, ...]:
        """Every registered name, in registration order."""
        return tuple(self._definitions)

    def __contains__(self, name: object) -> bool:
        return name in self._definitions

    def __iter__(self) -> Iterator[SubAgentDefinition]:
        return iter(self._definitions.values())

    def __len__(self) -> int:
        return len(self._definitions)
