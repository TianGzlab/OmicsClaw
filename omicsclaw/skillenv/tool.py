"""The ``install_skill_deps`` tool: add the packages a skill's method needs to an isolated overlay.

Only names under the skill's ``## Dependencies`` can be asked for, and each
installs the distributions its registry entry lists. Before asking the
person the tool only reads files and runs one local inventory of the
``python`` ``bash`` uses; nothing is downloaded or written until the
installation is approved. Packages come from this machine's pip
configuration, which the tool does not check.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from omicsclaw.skills import Skill, SkillIndex
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import pause_tool_timeout, report_progress, require_approval
from omicsclaw.tools.function_tool import FunctionTool, ToolArgumentError

from .overlay import OverlayBuilder, OverlayRequest, OverlayResult, base_distributions, overlay_key
from .probe import BaseInventory, ProbeError, ProbeRunner, run_inventory
from .registry import (
    DependencyFormatError,
    Resolution,
    normalise,
    parse_dependencies,
    probe_plan,
    pyproject_constraints,
    requirements,
    resolve,
)
from .sources import RequirementError, check_requirement

__all__ = [
    "INSTALL_SKILL_DEPS_POLICY",
    "INSTALL_SKILL_DEPS_SCHEMA",
    "INSTALL_SKILL_DEPS_TOOL_NAME",
    "install_skill_deps_tool",
]

INSTALL_SKILL_DEPS_TOOL_NAME = "install_skill_deps"

_DESCRIPTION = (
    "Install Python packages that the skills of one analysis module need into an isolated overlay "
    "environment built on the `python` bash runs, and return the overlay's interpreter. The base "
    "environment is never changed. List every skill the module's steps use, and name only the packages "
    "the methods you are about to run need, as the environment check that use_skill appends listed "
    "them; every name must be under the \"## Dependencies\" of at least one listed skill. Git-only and R "
    "packages are not installed. Depending on the session's permission settings, the person may be asked "
    "to approve the installation; nothing is downloaded before that decision. Afterwards, run the "
    "module's steps with the step runner under the interpreter the result gives, and keep using it for "
    "that module."
)

INSTALL_SKILL_DEPS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "the skills the module uses, names exactly as in the skill index",
        },
        "packages": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "the packages the methods you are about to run need, by the names the "
            "environment check listed",
        },
    },
    "required": ["skills", "packages"],
    "additionalProperties": False,
}

INSTALL_SKILL_DEPS_POLICY = ToolPolicy(
    risk_level=RiskLevel.HIGH,
    approval_mode=ApprovalMode.ASK,
    read_only=False,
    concurrency_safe=False,
    writes_workspace=False,
    writes_config=False,
    touches_network=True,
    prompts_for_itself=True,
    allowed_in_background=False,
    rule_argument="skills",
    tags=frozenset({"skills", "environment", "network"}),
)
"""Declared rather than defaulted: the tool asks for itself, with a card describing the installation.

``rule_argument="skills"`` makes "always allow" remember the sorted set of
skills and not the packages: the packages are already limited to what those
skills declare and go into an isolated overlay."""

_MINIMUM_PIP = (22, 2)
_REGISTRY_FILE = "skills/_sdk/deps.py"
_CANNOT_RUN = "the method that needs it cannot run here; report this rather than switching to another method"


def install_skill_deps_tool(
    skills_index: SkillIndex,
    *,
    registry: Mapping[str, Mapping[str, Any]],
    probe_runner: ProbeRunner,
    workspace: str,
    builder: OverlayBuilder,
    pyproject: Path | None = None,
    step_runner: str | None = None,
) -> FunctionTool:
    """Build ``install_skill_deps`` over *skills_index* and *registry*.

    :param probe_runner: Runs the inventory of the ``python`` ``bash`` uses, before approval.
    :param workspace: Working directory of that inventory.
    :param builder: Builds overlays after approval.
    :param pyproject: ``pyproject.toml`` whose optional dependencies give version constraints.
    :param step_runner: The step runner's path, named in the usage lines of the result.

    Invalid arguments raise :exc:`ToolArgumentError`. Everything else —
    nothing to install, a refusal, a failed installation — is an ordinary
    result; a refused approval raises
    :exc:`~omicsclaw.tools.context.ApprovalDenied` before anything is written.
    """
    constraints = pyproject_constraints(pyproject)

    async def run(skills: list[str], packages: list[str]) -> str:
        entries = _declared(skills_index, skills)
        declared = tuple(dict.fromkeys(name for _entry, names in entries for name in names))
        names = _requested(entries, packages)
        usage = _Usage([entry for entry, _names in entries], step_runner)
        resolved = [resolve(name, registry) for name in names]
        installable = [r for r in resolved if r.kind == "pip"]
        hints = [r for r in resolved if r.kind != "pip"]
        if not installable:
            return _nothing([], hints)
        first = entries[0][0]
        try:
            specs_of = {r.name: _specs(r, constraints, _owner(entries, r.name)) for r in installable}
        except RequirementError as exc:
            return f"install_skill_deps cannot install this: {exc}.\nNothing was run or downloaded."

        try:
            inventory = await run_inventory(
                probe_runner,
                [r.module for r in installable],
                str(first.directory),
                cwd=workspace,
                env={"PYTHONNOUSERSITE": "1"},
            )
        except ProbeError as exc:
            return f"install_skill_deps could not inspect the `python` bash runs: {exc}"
        refusal = _refusal(inventory)
        if refusal:
            return refusal
        missing = set(inventory.missing)
        wanted = [r for r in installable if r.module in missing]
        present = [r for r in installable if r.module not in missing]
        if not wanted:
            return _nothing(present, hints)
        specs = tuple(dict.fromkeys(spec for r in wanted for spec in specs_of[r.name]))
        base = base_distributions(inventory.records)
        key = overlay_key(inventory, base, specs)
        python = builder.python(key)
        if builder.finished(key):
            return _reused(usage, python, inventory, present, hints)

        await require_approval(
            INSTALL_SKILL_DEPS_TOOL_NAME,
            json.dumps({"skills": [entry.name for entry, _names in entries], "packages": list(packages)}),
            policy=INSTALL_SKILL_DEPS_POLICY,
            reason=_card(usage, specs, python, inventory),
            reason_shows_call=False,
        )
        plan = probe_plan(declared, registry)
        required = tuple(r.module for r in wanted)
        request = OverlayRequest(
            skills=tuple(entry.name for entry, _names in entries),
            names=tuple(r.name for r in wanted),
            specs=specs,
            required_imports=required,
            other_imports=tuple(m for m in plan.imports if m not in required),
        )
        with pause_tool_timeout():
            result = await builder.build(request, inventory, base, key, progress=_progress)
        if result.status == "reused":
            return _reused(usage, python, inventory, present, hints)
        if result.status == "installed":
            return _installed(usage, result, inventory, present, hints, required)
        return _failed(result, hints)

    return FunctionTool(
        INSTALL_SKILL_DEPS_TOOL_NAME,
        _DESCRIPTION,
        run,
        parameters=INSTALL_SKILL_DEPS_SCHEMA,
        policy=INSTALL_SKILL_DEPS_POLICY,
    )


async def _progress(message: str) -> None:
    await report_progress(message, tool_name=INSTALL_SKILL_DEPS_TOOL_NAME)


def _declared(skills: SkillIndex, names: Sequence[str]) -> list[tuple[Skill, tuple[str, ...]]]:
    """Each named skill with the packages its ``## Dependencies`` declares, in the order given."""
    if not names:
        raise ToolArgumentError("skills must name at least one skill")
    found: list[tuple[Skill, tuple[str, ...]]] = []
    for name in dict.fromkeys(str(n).strip() for n in names):
        entry = skills.get(name)
        if entry is None:
            raise ToolArgumentError(f"skill {name!r} is not in the skill index; use the `name` the index lists")
        try:
            declared = parse_dependencies(skills.get_full_content(entry.name), source=entry.path)
        except DependencyFormatError as exc:
            raise ToolArgumentError(str(exc)) from None
        found.append((entry, declared))
    return found


def _requested(entries: Sequence[tuple[Skill, Sequence[str]]], packages: Sequence[str]) -> list[str]:
    if not packages:
        raise ToolArgumentError("packages must name at least one package")
    by_normalised = {normalise(name): name for _entry, declared in entries for name in declared}
    unknown = [p for p in packages if normalise(str(p)) not in by_normalised]
    if unknown:
        declared_lines = "; ".join(f"{entry.name} declares: {', '.join(declared)}" for entry, declared in entries)
        raise ToolArgumentError(
            f"{', '.join(map(str, unknown))} not under the \"## Dependencies\" of "
            f"{', '.join(entry.name for entry, _d in entries)}; {declared_lines}"
        )
    return list(dict.fromkeys(by_normalised[normalise(str(p))] for p in packages))


def _owner(entries: Sequence[tuple[Skill, Sequence[str]]], name: str) -> Skill:
    """The first listed skill that declares *name*."""
    wanted = normalise(name)
    return next(entry for entry, declared in entries if any(normalise(d) == wanted for d in declared))


def _specs(resolution: Resolution, constraints: Mapping[str, tuple[str, str]], entry: Skill) -> tuple[str, ...]:
    pairs = requirements(
        resolution,
        constraints,
        registry_file=_REGISTRY_FILE,
        declared_in=f"the \"## Dependencies\" of {entry.name}",
    )
    return tuple(check_requirement(spec, source=source) for spec, source in pairs)


def _refusal(inventory: BaseInventory) -> str:
    if inventory.is_venv:
        return (
            f"install_skill_deps refused: the `python` bash runs ({inventory.executable}) is itself a virtual "
            f"environment (prefix {inventory.prefix}, base_prefix {inventory.base_prefix}); an overlay built on "
            "it would not see that environment's packages. Put a conda or system interpreter first on PATH, "
            "or install into that environment with bash yourself."
        )
    if inventory.pip_version and _version_tuple(inventory.pip_version) < _MINIMUM_PIP:
        return (
            f"install_skill_deps refused: the base environment's pip is {inventory.pip_version}; planning an "
            "installation needs pip 22.2 or newer (`pip install --report`)."
        )
    return ""


def _version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for part in text.split(".")[:2]:
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


class _Usage:
    """Who an overlay is for, and the commands that use it."""

    def __init__(self, entries: Sequence[Skill], step_runner: str | None) -> None:
        self.entries = list(entries)
        self.step_runner = step_runner

    @property
    def names(self) -> str:
        return ", ".join(entry.name for entry in self.entries)

    def lines(self, python: Path) -> list[str]:
        lines = []
        if self.step_runner:
            lines += [
                "Run the module's steps with this interpreter:",
                f"  PYTHONNOUSERSITE=1 {python} {self.step_runner} run analysis/<NN_slug>",
            ]
        script = _script(self.entries[0])
        lines += [
            "or run a skill's CLI with it:" if self.step_runner else "Run the skill with the overlay's interpreter:",
            f"  PYTHONNOUSERSITE=1 {python} {script} …",
        ]
        return lines


def _card(usage: _Usage, specs: Sequence[str], python: Path, inventory: BaseInventory) -> str:
    overlay = python.parent.parent
    plural = "skills" if len(usage.entries) > 1 else "skill"
    return "\n".join(
        [
            "install into an isolated overlay environment (the base environment is not changed):",
            *(f"  {spec}" for spec in specs),
            f"for {plural} {usage.names}, wheels only, plus whatever missing dependencies it needs;",
            "packages the base environment already has are kept as they are.",
            "packages come from this machine's pip configuration, the same as running `pip install` yourself;",
            "OmicsClaw does not check where that points (index, proxy, certificates).",
            "exact versions are resolved after you approve; the result lists every wheel installed and where it "
            "came from.",
            "a package can name a dependency by direct URL; pip may run that dependency's build script while",
            "resolving, before this tool refuses to install it.",
            f"overlay: {overlay}  (base: {inventory.executable} {inventory.version})",
        ]
    )


def _script(entry: Skill) -> str:
    guess = entry.directory / f"{entry.name.replace('-', '_')}.py"
    return str(guess) if guess.is_file() else f"{entry.directory}{os.sep}<script>.py"


def _hint_lines(present: Sequence[Resolution], hints: Sequence[Resolution]) -> list[str]:
    lines = []
    if present:
        lines.append("Already importable in the base environment: " + ", ".join(r.name for r in present))
    for r in hints:
        if r.kind == "git":
            extra = f", or the conda env `{r.alt_env}`" if r.alt_env else ""
            lines.append(f"Not installed (git-only): {r.name} — {r.install}{extra}")
        else:
            lines.append(f"Not installed (R package; `0_setup_env.sh` installs R packages): {r.name}")
    return lines


def _nothing(present: Sequence[Resolution], hints: Sequence[Resolution]) -> str:
    return "\n".join(["Nothing to install into an overlay.", *_hint_lines(present, hints)])


def _reused(
    usage: _Usage,
    python: Path,
    inventory: BaseInventory,
    present: Sequence[Resolution],
    hints: Sequence[Resolution],
) -> str:
    return "\n".join(
        [
            f"An overlay with these packages already exists for this base ({inventory.executable} "
            f"{inventory.version}): {python}. Nothing was installed or downloaded.",
            *_hint_lines(present, hints),
            *usage.lines(python),
        ]
    )


def _wheel_line(artifact: Any) -> str:
    plain = " (plaintext)" if artifact.transport == "http" else ""
    return f"- {artifact.pin}  {artifact.wheel}  from {artifact.source}{plain}"


def _installed(
    usage: _Usage,
    result: OverlayResult,
    inventory: BaseInventory,
    present: Sequence[Resolution],
    hints: Sequence[Resolution],
    required: Sequence[str],
) -> str:
    lines = [
        f"Installed into the overlay {result.python} (base: {inventory.executable} {inventory.version}; "
        "the base environment was not changed):",
        *(_wheel_line(a) for a in result.installed),
    ]
    for kept in result.kept_from_base:
        lines.append(
            f"Kept as the base environment has it: {kept.name} — the index wanted {kept.wanted}; the base "
            f"records {', '.join(kept.base_versions)}" + (" (ambiguous metadata)" if kept.ambiguous else "")
            + " — kept as is"
        )
    if result.unknown_base_records:
        lines.append(f"Base metadata records without a readable name: {result.unknown_base_records}")
    lines.append("pip check: no new problems.")
    if result.namespaces:
        lines.append("Namespace directories shared with the base (reported, not a problem): "
                     + ", ".join(result.namespaces))
    if result.pth_files:
        lines.append("New .pth files (they run whenever the overlay's interpreter starts): "
                     + ", ".join(result.pth_files))
    lines.append("Imports in the overlay: " + ", ".join(f"{name} ok" for name in required))
    others = [name for name, error in result.imports.items() if error and name not in required]
    if others:
        lines.append("Other modules of the skill that do not import here (not requested): " + ", ".join(others))
    lines += _hint_lines(present, hints)
    lines += usage.lines(result.python)
    return "\n".join(lines)


def _failed(result: OverlayResult, hints: Sequence[Resolution]) -> str:
    lines = [f"install_skill_deps failed: {result.reason}"]
    if result.violations:
        lines.append("New `pip check` problems:")
        lines += [f"  {line}" for line in result.violations]
    if result.plan is not None and (result.plan.install or result.plan.kept_from_base):
        lines.append("The resolved plan (to install by hand with bash, or to add to 0_setup_env.sh):")
        lines += [f"  {a.pin}  {a.wheel}  from {a.source}" for a in result.plan.install]
        lines += [f"  kept from the base: {k.name} {', '.join(k.base_versions)} (wanted {k.wanted})"
                  for k in result.plan.kept_from_base]
    lines.append(f"The requested packages were not installed: {_CANNOT_RUN}.")
    if result.escaped:
        lines.append(
            "Files may have been written outside the overlay (see above), and removing the half-built overlay did "
            "not remove them: check the pip configuration and the places it names, which may include the base "
            "environment."
        )
    else:
        lines.append("Nothing was changed: the half-built overlay was removed.")
    lines += _hint_lines((), hints)
    if result.log_tail:
        lines += ["Log (end):", result.log_tail]
    return "\n".join(lines)
