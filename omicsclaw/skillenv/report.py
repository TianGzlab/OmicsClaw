"""The environment-check note appended to ``use_skill``'s result."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .probe import ProbeResult
from .registry import ProbePlan, Resolution

__all__ = ["MAX_CHARS", "SandboxContext", "render_annotation"]

MAX_CHARS = 1500
"""Longest note rendered; past it, missing packages are listed by name only."""


@dataclass(frozen=True, slots=True)
class SandboxContext:
    """The sandbox ``bash`` runs in, for the note's wording."""

    image: str
    isolated: bool
    """``True`` when the container has no network."""
    network: str = "none"


def render_annotation(
    plan: ProbePlan,
    result: ProbeResult | None,
    *,
    error: str = "",
    registry_error: str = "",
    sandbox: SandboxContext | None = None,
    install_tool: bool = False,
    overlays: Sequence[str] = (),
) -> str:
    """Render the note for one skill.

    :param plan: The skill's declared names, resolved.
    :param result: The probe's report; ``None`` with *error* when it could not run.
    :param registry_error: Why the dependency registry could not be read, if it could not.
    :param sandbox: Where ``bash`` runs when that is a sandbox; ``None`` for this machine.
    :param install_tool: Whether ``install_skill_deps`` is mounted.
    :param overlays: Interpreters of existing overlays that cover missing
        packages; ignored in the sandbox, which cannot see them.
    :returns: Text starting with ``---``, at most :data:`MAX_CHARS` characters.
    """
    if result is None:
        head = f"---\ndependency registry unreadable: {registry_error}\n" if registry_error else "---\n"
        return _cap(f"{head}Environment check unavailable: {error or 'no result'}")
    full = _render(plan, result, registry_error, sandbox, install_tool, overlays, detailed=True)
    if len(full) <= MAX_CHARS:
        return full
    return _cap(_render(plan, result, registry_error, sandbox, install_tool, overlays, detailed=False))


def _render(
    plan: ProbePlan,
    result: ProbeResult,
    registry_error: str,
    sandbox: SandboxContext | None,
    install_tool: bool,
    overlays: Sequence[str],
    *,
    detailed: bool,
) -> str:
    where = "in the sandbox" if sandbox is not None else "here"
    lines = ["---"]
    if registry_error:
        lines.append(f"dependency registry unreadable: {registry_error}")
    lines.append(f"Environment check (the `python` bash runs {where}: {result.executable}, Python {result.version})")

    missing_modules = set(result.missing)
    probed = plan.probed
    missing = [r for r in probed if r.module in missing_modules]
    lines.append(
        f'- {len(probed) - len(missing)} of {len(probed)} packages under "## Dependencies" are importable.'
    )
    git_missing = [r for r in missing if r.kind == "git"]
    pip_missing = [r for r in missing if r.kind != "git"]
    if git_missing:
        lines.append(
            "- Missing, git-only (install_skill_deps cannot install these): "
            + "; ".join(_git(r, detailed) for r in git_missing)
        )
    if pip_missing:
        lines.append("- Missing: " + ", ".join(_pip(r, detailed) for r in pip_missing))
    if plan.r_packages:
        lines.append(
            "- R package, not checked here; the script's `validate_r_environment` reports it: "
            + ", ".join(r.name for r in plan.r_packages)
        )
    user = [r.name for r in probed if r.module in set(result.from_user_site)]
    if user:
        lines.append(
            "- found only in the user site (~/.local); an overlay command with PYTHONNOUSERSITE=1 "
            "will not see it: " + ", ".join(user)
        )
    if pip_missing and install_tool and sandbox is None:
        lines.append(
            "- install_skill_deps can add the ones your method needs to an isolated overlay; "
            "the base environment is never changed."
        )
    if missing and sandbox is None and overlays:
        lines.append("- An existing overlay covers some of these: " + ", ".join(overlays))
    if missing and sandbox is not None:
        if sandbox.isolated:
            lines.append(
                f"- This runs inside the sandbox image `{sandbox.image}`, which has no network: missing "
                "packages have to be added to the image by whoever maintains it."
            )
        else:
            lines.append(
                f"- The sandbox can reach network `{sandbox.network}`; install_skill_deps is not "
                "available inside the sandbox."
            )
    if missing:
        lines.append("- Methods that do not use a missing package are unaffected.")
    return "\n".join(lines)


def _git(r: Resolution, detailed: bool) -> str:
    if not detailed:
        return r.name
    text = f"{r.name} (import {r.module}) — {r.install}"
    if r.alt_env:
        text += f", or the conda env `{r.alt_env}`"
    return text


def _pip(r: Resolution, detailed: bool) -> str:
    return f"{r.name} (import {r.module})" if detailed else r.name


def _cap(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1] + "…"
