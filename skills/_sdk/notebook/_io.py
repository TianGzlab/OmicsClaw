"""Reading inputs, writing outputs and loading demo data from a step.

A step learns which file it is from ``OMICSCLAW_STEP_FILE`` (set by the
step runner) or, when run on its own, from ``sys.argv[0]``. The step file
must sit in ``analysis/<NN_slug>/``; the project root is the parent of
``analysis/``, whatever the working directory.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skills._sdk import REPO_ROOT
from skills._sdk.notebook import _hashing, _ledger
from skills._sdk.notebook._layout import MODULE_RE, Module, module_from_name
from skills._sdk.notebook.contract import ENVIRONMENT, LAYOUT

DEMOS = {
    "pbmc3k_raw": {
        "files": ["data/pbmc3k_raw.h5ad", "examples/pbmc3k.h5ad"],
        "download": "pbmc3k",
        "about": "10x PBMC 3k, raw counts (2,700 cells x 32,738 genes)",
    },
    "pbmc3k_processed": {
        "files": ["data/pbmc3k_processed.h5ad", "examples/pbmc3k_processed.h5ad"],
        "download": "pbmc3k_processed",
        "about": "10x PBMC 3k after scanpy's tutorial: log-normalised, PCA, UMAP, louvain labels",
    },
    "pbmc68k_reduced": {
        "files": ["data/pbmc68k_reduced.h5ad"],
        "download": "pbmc68k_reduced",
        "about": "700-cell subsample of 10x PBMC 68k bundled with scanpy, processed",
    },
}
"""Registered demo datasets: candidate files under the checkout, and the scanpy loader that downloads them."""


@dataclass(frozen=True)
class StepContext:
    """The step being run, its module and project, and the ledger of the run if there is one."""

    step_file: Path | None
    root: Path | None
    module: Module | None
    ledger: _ledger.Ledger | None

    def require_module(self, action: str) -> Module:
        if self.module is None or self.root is None:
            where = self.step_file or "an unknown file"
            raise RuntimeError(
                f"cannot {action}: {where} is not a step file in analysis/<NN_slug>/. "
                "Run the step with the step runner, or as `python analysis/<NN_slug>/<step>.py` "
                "from the project root."
            )
        return self.module


def step_context(*, notice: bool = True) -> StepContext:
    """Work out the running step from the environment or ``sys.argv[0]``."""
    named = os.environ.get(ENVIRONMENT["step_file"], "").strip()
    raw = named or (sys.argv[0] if sys.argv and sys.argv[0] else "")
    step = Path(os.path.abspath(raw)) if raw and raw.endswith(".py") else None
    root = module = None
    if step is not None and step.parent.parent.name == "analysis" and MODULE_RE.match(step.parent.name):
        root = step.parent.parent.parent
        module = module_from_name(root, step.parent.name)
    return StepContext(step_file=step, root=root, module=module, ledger=_ledger.current(notice=notice))


def project_relative(path: Path, root: Path | None) -> str:
    """*path* relative to the project root in POSIX form, or absolute when it lies outside."""
    if root is not None:
        try:
            return Path(os.path.abspath(path)).relative_to(root).as_posix()
        except ValueError:
            pass
    return str(Path(os.path.abspath(path)))


def outside_contract(path: Path, root: Path, module: Module | None) -> bool:
    """Whether a step reading *path* goes outside what a step may read.

    A step reads ``data/``, ``manifests/``, an earlier module's
    ``intermediate/`` and ``tables/``, and anything in its own results.
    """
    try:
        parts = Path(os.path.abspath(path)).relative_to(root).parts
    except ValueError:
        return True
    if not parts:
        return True
    if parts[0] in {"data", "manifests"}:
        return False
    if parts[0] == "results" and len(parts) >= 2 and MODULE_RE.match(parts[1]):
        if module is not None and parts[1] == module.name:
            return False
        if len(parts) >= 3 and parts[2] in {"intermediate", "tables"}:
            return module is not None and int(parts[1][:2]) >= module.number
    return True


def record_input(ctx: StepContext, path: Path, *, via: str, contract_checked: bool = True) -> None:
    """Hash *path* and record it as an input of the running step."""
    flagged = False
    if contract_checked and ctx.root is not None:
        flagged = outside_contract(path, ctx.root, ctx.module)
        if flagged:
            print(
                f"warning: {project_relative(path, ctx.root)} is outside what a step reads "
                "(data/, manifests/, an earlier module's intermediate/ or tables/, this module's results)",
                file=sys.stderr,
            )
    if ctx.ledger is None:
        return
    ctx.ledger.append(
        "input",
        path=project_relative(path, ctx.root),
        sha256=_hashing.sha256_path(path),
        bytes=_hashing.size_of(path),
        via=via,
        outside_contract=flagged,
    )


def _default_reader(path: Path) -> Any:
    suffix = path.suffix.lower()
    if path.is_dir():
        return path
    if suffix == ".h5ad":
        import anndata

        return anndata.read_h5ad(path)
    if suffix in {".csv", ".tsv"}:
        import pandas as pd

        return pd.read_csv(path, sep="\t" if suffix == ".tsv" else ",")
    if suffix == ".parquet":
        import pandas as pd

        return pd.read_parquet(path)
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    return path


def read_input(path: str | os.PathLike, *, reader: Callable[[Path], Any] | None = None) -> Any:
    """Load a file or directory the step reads, and record its path and sha256.

    The path is relative to the project root. A step reads data/,
    manifests/, an earlier module's results/<NN_slug>/intermediate/ and
    tables/, and its own module's results; another path is read too, with a
    warning on stderr, and recorded as outside the contract.

    Without a reader the loader follows the suffix: .h5ad anndata.read_h5ad,
    .csv and .tsv pandas.read_csv, .parquet pandas.read_parquet, .json the
    parsed JSON, .txt and .md the text. A directory, or any other suffix,
    returns the Path itself. pandas reads a column of digit-only labels,
    such as cluster ids, as integers: compare it through as_labels from
    skills._sdk.notebook.checks, or pass
    reader=lambda p: pd.read_csv(p, dtype={"leiden": str}).

    :raises FileNotFoundError: nothing exists at the path.
    """
    ctx = step_context()
    raw = Path(path)
    base = ctx.root if ctx.root is not None else Path.cwd()
    target = raw if raw.is_absolute() else base / raw
    if not target.exists():
        raise FileNotFoundError(f"{path}: no such file or directory under {base}")
    record_input(ctx, target, via="read_input")
    return (reader or _default_reader)(target)


def _is_frozen(module: Module) -> bool:
    try:
        manifest = json.loads(module.manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(manifest.get("frozen"))


def check_output_path(module: Module, path: str | os.PathLike) -> Path:
    """The absolute target of an output path, checked against the module's output folders.

    :raises ValueError: the path is absolute, climbs with ``..``, or does not
        start with one of ``figures``, ``tables``, ``intermediate``, ``logs``.
    """
    relative = Path(path)
    allowed = LAYOUT["output_dirs"]
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(
            f"{path}: write_output takes a path inside this module's results, "
            f"starting with one of {', '.join(allowed)} (for example tables/summary.csv)"
        )
    if len(relative.parts) < 2 or relative.parts[0] not in allowed:
        raise ValueError(
            f"{path}: the first folder must be one of {', '.join(allowed)}, "
            f"for example tables/{relative.name or 'summary.csv'}"
        )
    return module.results_dir / relative


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _default_writer(obj: Any, target: Path, suffix: str) -> None:
    suffix = suffix.lower()
    if suffix == ".h5ad" and hasattr(obj, "write_h5ad"):
        obj.write_h5ad(target)
    elif suffix in {".csv", ".tsv"} and hasattr(obj, "to_csv"):
        index = getattr(obj, "index", None)
        keep_index = not (index is not None and type(index).__name__ == "RangeIndex")
        obj.to_csv(target, sep="\t" if suffix == ".tsv" else ",", index=keep_index)
    elif suffix == ".parquet" and hasattr(obj, "to_parquet"):
        obj.to_parquet(target)
    elif suffix in {".png", ".pdf", ".svg"} and hasattr(obj, "savefig"):
        obj.savefig(target, dpi=150, bbox_inches="tight", format=suffix[1:])
    elif suffix == ".json" and isinstance(obj, (dict, list)):
        target.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")
    elif suffix in {".md", ".txt"} and isinstance(obj, str):
        target.write_text(obj, encoding="utf-8")
    else:
        raise ValueError(
            f"no default writer for a {type(obj).__name__} as {suffix or 'a file without suffix'}; "
            "pass writer=lambda obj, path: ..."
        )


def write_output(obj: Any, path: str | os.PathLike, *,
                 writer: Callable[[Any, Path], None] | None = None) -> Path:
    """Write one output of the current module atomically and record its sha256.

    The path is relative to results/<NN_slug>/ and starts with figures/,
    tables/, intermediate/ or logs/; subfolders are allowed, ".." and
    absolute paths are not. Give an output a new name rather than
    overwriting a file the same step read.

    Without a writer the format follows the suffix and the object's type:
    .h5ad an object with write_h5ad; .csv and .tsv an object with to_csv,
    written without its index when that is a RangeIndex; .parquet an object
    with to_parquet; .png, .pdf and .svg an object with savefig, at dpi 150
    with bbox_inches="tight"; .json a dict or list, indented, with numpy
    values as plain numbers and lists; .md and .txt a str. Anything else
    needs writer=lambda obj, path: .... Returns the absolute path written.

    :raises ValueError: the path is outside the module's output folders, or
        no default writer fits the object and suffix.
    :raises RuntimeError: the step's module is not known, or it is accepted
        and frozen.
    """
    ctx = step_context()
    module = ctx.require_module("write an output")
    if _is_frozen(module):
        raise RuntimeError(
            f"module {module.name} is accepted and frozen; run `revise analysis/{module.name}` before changing it"
        )
    target = check_output_path(module, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".tmp-{secrets.token_hex(4)}-{target.name}"
    try:
        if writer is not None:
            writer(obj, temporary)
        else:
            _default_writer(obj, temporary, target.suffix)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    if ctx.ledger is not None:
        ctx.ledger.append(
            "output",
            path=target.relative_to(module.results_dir).as_posix(),
            sha256=_hashing.sha256_path(target),
            bytes=_hashing.size_of(target),
            kind=Path(path).parts[0],
        )
    return target


def demo_cache_dir() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(cache).expanduser() if cache else Path.home() / ".cache"
    return base / "omicsclaw" / "demo"


def demo_candidates(name: str) -> list[Path]:
    """Where :func:`load_demo` looks for *name*, in order, before downloading it."""
    entry = DEMOS[name]
    found: list[Path] = []
    demo_dir = os.environ.get(ENVIRONMENT["demo_dir"], "").strip()
    if demo_dir:
        found.append(Path(demo_dir).expanduser() / f"{name}.h5ad")
    found.extend(REPO_ROOT / relative for relative in entry["files"])
    found.append(demo_cache_dir() / f"{name}.h5ad")
    return found


def _download_demo(name: str) -> Path:
    import scanpy as sc

    cache = demo_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    previous = sc.settings.datasetdir
    sc.settings.datasetdir = cache
    try:
        adata = getattr(sc.datasets, DEMOS[name]["download"])()
    finally:
        sc.settings.datasetdir = previous
    target = cache / f"{name}.h5ad"
    if not target.exists():
        adata.write_h5ad(target)
    return target


def load_demo(name: str) -> Any:
    """Load a registered demo dataset as AnnData and record it as an input of the step.

    The file is looked for, in order: <name>.h5ad in $OMICSCLAW_DEMO_DIR;
    the checkout's data/ and examples/; <name>.h5ad in
    $XDG_CACHE_HOME/omicsclaw/demo/ (~/.cache/omicsclaw/demo/ when unset).
    When none has it, scanpy downloads it into that cache.

    :raises LookupError: *name* is not a registered demo dataset.
    :raises RuntimeError: the file is in none of the places looked at and
        cannot be downloaded.
    """
    if name not in DEMOS:
        raise LookupError(f"no demo dataset named {name!r}; registered: {', '.join(sorted(DEMOS))}")
    path = next((p for p in demo_candidates(name) if p.is_file()), None)
    if path is None:
        try:
            path = _download_demo(name)
        except Exception as exc:  # network errors come in many types
            places = "\n  ".join(str(p) for p in demo_candidates(name))
            raise RuntimeError(
                f"demo dataset {name!r} is not available and could not be downloaded ({exc}). "
                f"Put {name}.h5ad in one of:\n  {places}\n"
                f"or point {ENVIRONMENT['demo_dir']} at a folder holding it."
            ) from exc
    ctx = step_context()
    record_input(ctx, path, via="load_demo", contract_checked=False)
    import anndata

    return anndata.read_h5ad(path)
