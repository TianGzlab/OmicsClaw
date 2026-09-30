"""What a skill declares it needs, and what the dependency registry says about each name.

Two files are read, never imported: a skill's ``SKILL.md`` (its
``## Dependencies`` package-name line) and ``<skills root>/_sdk/deps.py``
(the literal ``DEPENDENCIES`` table). Names resolve against the table by
exact key, then PEP 503-normalised key, then exact ``module``; a name none
of those match is treated as a pip project whose import name is derived here.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DependencyFormatError",
    "ProbePlan",
    "RegistryFormatError",
    "Resolution",
    "normalise",
    "parse_dependencies",
    "probe_plan",
    "pyproject_constraints",
    "read_registry",
    "requirements",
    "resolve",
]

KINDS = frozenset({"pip", "git", "r"})
_REQUIRED = ("module", "kind", "install", "description")
_OPTIONAL = frozenset({"also", "alt_env"})

_NAME = r"`[A-Za-z0-9][A-Za-z0-9._-]*`"
_PACKAGE_LINE = re.compile(rf"^\s*{_NAME}(\s*,\s*{_NAME})*\s*$")
_HEADING = re.compile(r"^##\s")

_FALLBACK_IMPORT_NAMES = {"pyyaml": "yaml", "scikit-learn": "sklearn"}
"""Unregistered projects whose import name cannot be derived from the project name."""


class DependencyFormatError(ValueError):
    """A ``## Dependencies`` section without exactly one package-name line."""


class RegistryFormatError(ValueError):
    """A dependency registry file that is missing, not a literal, or breaks the field contract."""


def normalise(name: str) -> str:
    """The PEP 503 normalised form of a project name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_dependencies(text: str, *, source: str | Path) -> tuple[str, ...]:
    """The names on the package-name line of *text*'s ``## Dependencies`` section.

    The section runs from its heading to the next ``## `` heading. Prose in
    it is ignored; exactly one line must consist of back-quoted,
    comma-separated names made of letters, digits, ``.``, ``_`` and ``-``.

    :param source: Where *text* came from, named in errors.
    :raises DependencyFormatError: No section, or not exactly one such line.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Dependencies"), None)
    if start is None:
        raise DependencyFormatError(f"{source}: no `## Dependencies` section")
    found: list[tuple[int, str]] = []
    for number in range(start + 1, len(lines)):
        line = lines[number]
        if _HEADING.match(line):
            break
        if _PACKAGE_LINE.match(line):
            found.append((number + 1, line))
    if not found:
        raise DependencyFormatError(
            f"{source}:{start + 1}: `## Dependencies` has no package-name line "
            "(one line of `name`, `name`, … using letters, digits, '.', '_' and '-')"
        )
    if len(found) > 1:
        where = ", ".join(str(number) for number, _ in found)
        raise DependencyFormatError(f"{source}: `## Dependencies` has {len(found)} package-name lines (lines {where})")
    return tuple(re.findall(r"`([^`]+)`", found[0][1]))


def read_registry(path: str | Path) -> dict[str, dict[str, Any]]:
    """Read the module-level ``DEPENDENCIES`` literal from *path* without importing it.

    :returns: The table, checked against the field contract.
    :raises RegistryFormatError: The file is missing, has no module-level
        ``DEPENDENCIES`` assignment, the value is not a literal, or an entry
        breaks the contract. The message names the file and, where there is
        one, the line.
    """
    path = Path(path)
    if not path.is_file():
        raise RegistryFormatError(
            f"{path} not found: the configured skills_dir is not an OmicsClaw skills tree "
            "with `_sdk/`, so there is no dependency registry to read"
        )
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise RegistryFormatError(f"{path}: cannot be parsed: {exc}") from exc
    node = _assignment(tree)
    if node is None:
        raise RegistryFormatError(f"{path}: no module-level DEPENDENCIES assignment")
    where = f"{path}:{node.lineno}"
    try:
        table = ast.literal_eval(node.value)
    except ValueError as exc:
        raise RegistryFormatError(f"{where}: DEPENDENCIES is not a literal ({exc})") from exc
    _check(table, where)
    return table


def _assignment(tree: ast.Module) -> ast.Assign | ast.AnnAssign | None:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "DEPENDENCIES" and node.value is not None:
                return node
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "DEPENDENCIES" for t in node.targets):
                return node
    return None


def _check(table: object, where: str) -> None:
    if not isinstance(table, dict):
        raise RegistryFormatError(f"{where}: DEPENDENCIES must be a dict, not {type(table).__name__}")
    by_normalised: dict[str, str] = {}
    by_module: dict[str, str] = {}
    for key, entry in table.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            raise RegistryFormatError(f"{where}: entry {key!r} must map a string to a dict")
        missing = [field for field in _REQUIRED if not isinstance(entry.get(field), str) or not entry.get(field)]
        if missing:
            raise RegistryFormatError(f"{where}: entry {key!r} is missing {', '.join(missing)}")
        unknown = set(entry) - set(_REQUIRED) - _OPTIONAL
        if unknown:
            raise RegistryFormatError(f"{where}: entry {key!r} has unknown fields {sorted(unknown)}")
        if entry["kind"] not in KINDS:
            raise RegistryFormatError(f"{where}: entry {key!r} has kind {entry['kind']!r}, not one of {sorted(KINDS)}")
        also = entry.get("also", [])
        if not isinstance(also, list) or not all(isinstance(item, str) and item for item in also):
            raise RegistryFormatError(f"{where}: entry {key!r} field also must be a list of strings")
        if "alt_env" in entry and (not isinstance(entry["alt_env"], str) or not entry["alt_env"]):
            raise RegistryFormatError(f"{where}: entry {key!r} field alt_env must be a non-empty string")
        normalised = normalise(key)
        if normalised in by_normalised:
            raise RegistryFormatError(
                f"{where}: keys {by_normalised[normalised]!r} and {key!r} normalise to the same name"
            )
        by_normalised[normalised] = key
        if entry["module"] in by_module:
            raise RegistryFormatError(
                f"{where}: entries {by_module[entry['module']]!r} and {key!r} share module {entry['module']!r}"
            )
        by_module[entry["module"]] = key
    for module, owner in by_module.items():
        other = by_normalised.get(normalise(module))
        if other is not None and other != owner:
            raise RegistryFormatError(
                f"{where}: {module!r} is ambiguous — the module of {owner!r} and a spelling of key {other!r}"
            )


@dataclass(frozen=True, slots=True)
class Resolution:
    """One declared or called name, resolved against the registry.

    ``key`` is ``None`` when no entry matched and the fallback applied.
    ``module`` is the import name probed for ``pip``/``git`` entries and the
    R package name for ``r`` entries.
    """

    name: str
    key: str | None
    module: str
    kind: str
    install: str
    also: tuple[str, ...] = ()
    alt_env: str | None = None

    @property
    def distributions(self) -> tuple[str, ...]:
        """The PyPI projects installing this name would install: the key (or name) and ``also``."""
        return (self.key or self.name, *self.also)


def resolve(name: str, entries: Mapping[str, Mapping[str, Any]]) -> Resolution:
    """Resolve *name*: exact key, normalised key, exact ``module``, then the fallback.

    The fallback is a ``pip`` project called *name* whose import name comes
    from a small table of irregular names, or is *name* with ``-`` turned
    into ``_``.
    """
    key = _match(name, entries)
    if key is None:
        module = _FALLBACK_IMPORT_NAMES.get(normalise(name), name.replace("-", "_"))
        return Resolution(name=name, key=None, module=module, kind="pip", install=f"pip install {name}")
    entry = entries[key]
    return Resolution(
        name=name,
        key=key,
        module=entry["module"],
        kind=entry["kind"],
        install=entry["install"],
        also=tuple(entry.get("also", ())),
        alt_env=entry.get("alt_env"),
    )


def _match(name: str, entries: Mapping[str, Mapping[str, Any]]) -> str | None:
    if name in entries:
        return name
    wanted = normalise(name)
    for key in entries:
        if normalise(key) == wanted:
            return key
    for key, entry in entries.items():
        if entry.get("module") == name:
            return key
    return None


@dataclass(frozen=True, slots=True)
class ProbePlan:
    """The names a skill declares, resolved, and what the probe should import for them."""

    resolved: tuple[Resolution, ...]
    imports: tuple[str, ...]
    """Import names to probe: every ``pip`` and ``git`` resolution's module, in declaration order."""

    @property
    def r_packages(self) -> tuple[Resolution, ...]:
        """The ``r`` resolutions, which are never probed."""
        return tuple(r for r in self.resolved if r.kind == "r")

    @property
    def probed(self) -> tuple[Resolution, ...]:
        """The resolutions whose module is probed."""
        return tuple(r for r in self.resolved if r.kind != "r")


def probe_plan(names: Iterable[str], entries: Mapping[str, Mapping[str, Any]]) -> ProbePlan:
    """Resolve *names* and list the modules to probe, leaving out R packages."""
    resolved = tuple(resolve(name, entries) for name in names)
    imports = tuple(dict.fromkeys(r.module for r in resolved if r.kind != "r"))
    return ProbePlan(resolved=resolved, imports=imports)



_LEADING_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def pyproject_constraints(path: str | Path | None) -> dict[str, tuple[str, str]]:
    """Requirement strings by normalised name, from ``[project.optional-dependencies]`` of *path*.

    The first entry for a name wins; the project's references to itself are
    skipped. A missing or unreadable file gives an empty table.

    :returns: Normalised name to ``(requirement, where it was found)``.
    """
    if path is None:
        return {}
    path = Path(path)
    try:
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}
    own = normalise(str(project.get("name", "")))
    found: dict[str, tuple[str, str]] = {}
    for extra, specs in (project.get("optional-dependencies") or {}).items():
        for spec in specs if isinstance(specs, list) else ():
            head = _LEADING_NAME.match(str(spec))
            if head is None or normalise(head.group(1)) == own:
                continue
            found.setdefault(normalise(head.group(1)), (str(spec), f"{path.name} [project.optional-dependencies] {extra}"))
    return found


def requirements(
    resolution: Resolution,
    constraints: Mapping[str, tuple[str, str]],
    *,
    registry_file: str,
    declared_in: str,
) -> tuple[tuple[str, str], ...]:
    """What pip should be asked for to install *resolution*: ``(requirement, where it came from)`` pairs.

    One pair per distribution in :attr:`Resolution.distributions`. A
    distribution with a constraint in *constraints* is asked for with it;
    otherwise the distribution string itself is used, unchecked.

    :param registry_file: How to name the registry file in the source of an ``also`` entry.
    :param declared_in: How to name the skill's ``## Dependencies`` for an unregistered name.
    """
    found = []
    for index, distribution in enumerate(resolution.distributions):
        head = _LEADING_NAME.match(distribution)
        constraint = constraints.get(normalise(head.group(1))) if head else None
        if constraint is not None and head is not None and head.group(0).strip() == distribution.strip():
            found.append(constraint)
        elif index == 0 and resolution.key is None:
            found.append((distribution, declared_in))
        elif index == 0:
            found.append((distribution, f"{registry_file}: entry {resolution.key!r}"))
        else:
            found.append((distribution, f"{registry_file}: entry {resolution.key!r} field also"))
    return tuple(found)
