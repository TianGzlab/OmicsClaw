"""The session-wide permission posture.

One setting, chosen at start-up, that shifts every gate decision at once. The
terminal's ``/auto`` can move it between :attr:`PermissionMode.DEFAULT` and
:attr:`PermissionMode.AUTO_APPROVE` mid-session (plan 0050); the other two are
deployment promises and only a start-up setting can make or break them.
It answers questions no per-call detail answers — "this is a throwaway
container", "I want to read this cohort and change nothing" are properties of
the session, not of a tool or an argument.

:meth:`omicsclaw.permission.PermissionGate.resolve` is where each value takes
effect.
"""

from __future__ import annotations

from enum import StrEnum


class PermissionMode(StrEnum):
    """How much this session is trusted.

    A :class:`~enum.StrEnum`, so a configuration file, a CLI flag and the code
    all spell a mode the same way and the value logged is the value written.
    """

    DEFAULT = "default"
    """Rules decide; an unmatched call falls back to the tool's own policy.

    The guarded value, and what a person at a terminal wants: the foundation
    tools' own ``ASK`` declarations still hold, and a rule file is how they get
    refined per argument rather than per tool."""

    AUTO_APPROVE = "auto-approve"
    """An unmatched call is allowed instead of consulting the tool's policy.

    ``deny`` rules and the dangerous-command patterns still apply, which is the
    difference from :attr:`BYPASS_ALL`: this stops the questions about ordinary
    work, it does not stop the checks."""

    READ_ONLY = "read-only"
    """Refuse every tool that does not declare ``read_only=True``.

    The claim is read in the refusing direction, so a tool that declared
    nothing is refused rather than trusted. Note two consequences: ``bash`` is
    refused outright, because it cannot honestly claim ``read_only``; and so is
    ``web_search``, because a query sent to a search engine writes nothing
    locally but is still an outbound disclosure. A deployment that wants
    reading plus searching wants :attr:`DEFAULT` and a rule file."""

    BYPASS_ALL = "bypass-all"
    """No checks at all: no rules, no danger patterns, no approval prompts.

    For a controlled environment with nobody attached, such as a benchmark
    runner. :meth:`~omicsclaw.permission.PermissionGate.resolve` puts the mode
    name in the reason it returns, so a transcript records that the session ran
    ungated."""


__all__ = ["PermissionMode"]
