"""Where a project's modules, steps and results live, and how they are named.

A project root holds ``analysis/<NN_slug>/`` (a module's code) and
``results/<NN_slug>/`` (its outputs). The names follow ``LAYOUT`` in
:mod:`skills._sdk.notebook.contract`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from skills._sdk.notebook.contract import LAYOUT

MODULE_RE = re.compile(LAYOUT["module_dir"])
STEP_RE = re.compile(LAYOUT["step_file"])
VALIDATE_RE = re.compile(LAYOUT["validate_step"])
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
NUMBERED_SLUG_RE = re.compile(r"^\d{2}_")
"""A slug that already carries a module number, which ``new`` would double (``01_01_qc``)."""

PROJECT_DIRS = (
    "analysis",
    "results",
    LAYOUT["archive_dir"],
    "data",
    "docs/analysis_strategy",
    "manifests",
    "scripts",
    "work",
)
"""Project folders ``new`` creates when they are missing."""

TEMPLATES = Path(__file__).resolve().parent / "templates"
CHECKOUT = Path(__file__).resolve().parents[3]
"""The directory holding the ``skills`` package this runner belongs to."""


class LayoutError(ValueError):
    """A path or name does not follow the project layout."""


@dataclass(frozen=True)
class Module:
    """One module: its number, slug, code directory and results directory."""

    root: Path
    number: int
    slug: str

    @property
    def name(self) -> str:
        return f"{self.number:02d}_{self.slug}"

    @property
    def analysis_dir(self) -> Path:
        return self.root / "analysis" / self.name

    @property
    def results_dir(self) -> Path:
        return self.root / "results" / self.name

    @property
    def manifest_path(self) -> Path:
        return self.results_dir / LAYOUT["manifest"]

    @property
    def runs_dir(self) -> Path:
        return self.results_dir / LAYOUT["runs"]

    @property
    def lock_path(self) -> Path:
        return self.results_dir / "provenance" / ".lock"

    @property
    def report_name(self) -> str:
        return LAYOUT["report"].format(nn=f"{self.number:02d}", slug=self.slug)

    def steps(self) -> list[Path]:
        """Step files in run order: by file name, the validate step last."""
        if not self.analysis_dir.is_dir():
            return []
        files = sorted(p for p in self.analysis_dir.iterdir() if p.is_file() and STEP_RE.match(p.name))
        return [p for p in files if not VALIDATE_RE.match(p.name)] + [
            p for p in files if VALIDATE_RE.match(p.name)
        ]

    def validate_steps(self) -> list[Path]:
        return [p for p in self.steps() if VALIDATE_RE.match(p.name)]

    def r_files(self) -> list[Path]:
        if not self.analysis_dir.is_dir():
            return []
        return sorted(p for p in self.analysis_dir.iterdir() if p.is_file() and p.suffix in {".R", ".r"})

    def ignored_files(self) -> list[Path]:
        """Python files in the module whose names are not step names."""
        if not self.analysis_dir.is_dir():
            return []
        return sorted(
            p for p in self.analysis_dir.iterdir()
            if p.is_file() and p.suffix == ".py" and not STEP_RE.match(p.name)
        )


def parse_module_name(name: str) -> tuple[int, str]:
    match = MODULE_RE.match(name)
    if match is None:
        raise LayoutError(f"{name!r} is not a module name: expected <NN>_<slug>, for example 03_clustering")
    return int(match.group(1)), match.group(2)


def module_from_name(root: Path, name: str) -> Module:
    number, slug = parse_module_name(name)
    return Module(root=root, number=number, slug=slug)


def project_root_of(path: str | os.PathLike) -> Path | None:
    """The project root for a path under ``analysis/`` or ``results/``, else ``None``."""
    absolute = Path(os.path.abspath(path))
    for parent in (absolute, *absolute.parents):
        if parent.name in {"analysis", "results"} and parent.parent != parent:
            return parent.parent
    return None


def resolve_target(root: Path, target: str) -> tuple[Module, Path | None]:
    """The module and, for a step file, the step that *target* names.

    *target* is a module directory (``analysis/03_clustering``), a step file
    in one, a results directory, or a bare module name.
    """
    raw = Path(target)
    path = raw if raw.is_absolute() else root / raw
    path = Path(os.path.abspath(path))
    if len(raw.parts) == 1 and MODULE_RE.match(raw.name) and not path.exists():
        return module_from_name(root, raw.name), None
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise LayoutError(f"{target} is not inside the project at {root}") from None
    parts = relative.parts
    if len(parts) == 1 and MODULE_RE.match(parts[0]):
        return module_from_name(root, parts[0]), None
    if len(parts) < 2 or parts[0] not in {"analysis", "results"}:
        raise LayoutError(f"{target} is not a module: give analysis/<NN_slug> or a step file in it")
    module = module_from_name(root, parts[1])
    if len(parts) == 2:
        return module, None
    if parts[0] == "analysis" and len(parts) == 3:
        if path.suffix in {".R", ".r"}:
            return module, path
        if not STEP_RE.match(path.name):
            raise LayoutError(
                f"{path.name} is not a step name: expected <k>_<name>.py, for example 02_cluster.py"
            )
        return module, path
    raise LayoutError(f"{target} is not a module directory or a step file")


def modules(root: Path) -> list[Module]:
    """Every module with a code or results directory, by number."""
    found: dict[str, Module] = {}
    for parent in (root / "analysis", root / "results"):
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if child.is_dir() and MODULE_RE.match(child.name):
                found.setdefault(child.name, module_from_name(root, child.name))
    return sorted(found.values(), key=lambda m: (m.number, m.slug))


def is_checkout(root: Path) -> bool:
    """Whether *root* is an OmicsClaw checkout rather than a separate project folder."""
    return (root / "skills" / "_sdk" / "__init__.py").is_file() and (root / "omicsclaw").is_dir()


def ensure_skeleton(root: Path, *, title: str | None = None) -> list[str]:
    """Create the missing project folders and the strategy template; return what was created.

    Existing files and folders are never moved, renamed or changed.
    """
    created: list[str] = []
    for relative in PROJECT_DIRS:
        target = root / relative
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(relative + "/")
    strategy = root / LAYOUT["strategy_file"]
    if not strategy.exists():
        text = (TEMPLATES / "STRATEGY.md").read_text(encoding="utf-8")
        if title:
            text = text.replace("<Project title>", title, 1)
        strategy.write_text(text, encoding="utf-8")
        created.append(LAYOUT["strategy_file"])
    return created


def next_number(root: Path) -> int:
    used = [m.number for m in modules(root)]
    return max(used, default=0) + 1


def create_module(root: Path, slug: str) -> Module:
    """Create ``analysis/<NN_slug>/README.md`` and the results folders of a new module."""
    if not SLUG_RE.match(slug):
        raise LayoutError(
            f"{slug!r} is not a module slug: use lowercase letters, digits and underscores, "
            "starting with a letter or digit"
        )
    number = next_number(root)
    if number > 99:
        raise LayoutError("the project already has 99 modules")
    module = Module(root=root, number=number, slug=slug)
    module.analysis_dir.mkdir(parents=True, exist_ok=False)
    readme = (TEMPLATES / "README.md").read_text(encoding="utf-8")
    readme = readme.replace("<NN_slug>", module.name).replace("<checkout>", str(CHECKOUT))
    (module.analysis_dir / "README.md").write_text(readme, encoding="utf-8")
    for folder in (*LAYOUT["output_dirs"], *LAYOUT["runner_dirs"]):
        (module.results_dir / folder).mkdir(parents=True, exist_ok=True)
    return module


def today() -> str:
    return date.today().isoformat()
