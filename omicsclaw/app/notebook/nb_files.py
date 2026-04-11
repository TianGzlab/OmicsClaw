"""`.ipynb` file I/O helpers for the notebook router.

This module is kernel-agnostic: it only deals with reading and parsing
`.ipynb` JSON off disk (or out of an uploaded blob) and presenting the
subset of cells the frontend needs.

Kept deliberately small so the router layer can stay thin. Path-traversal
guarding lives here too because any caller that touches the filesystem
goes through ``resolve_ipynb_path``.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from pathlib import Path
from typing import Any


__all__ = [
    "parse_ipynb_bytes",
    "list_ipynb_files",
    "resolve_ipynb_path",
    "resolve_workspace_root",
    "resolve_workspace_notebook_target",
    "create_empty_notebook",
    "save_notebook",
    "delete_notebook",
    "derive_notebook_id",
    "list_workspace_notebooks",
    "open_workspace_notebook",
    "create_workspace_notebook",
    "save_workspace_notebook",
    "delete_workspace_notebook",
]

# Cell types the frontend is allowed to round-trip through save/open.
_ALLOWED_CELL_TYPES = ("code", "markdown")


def parse_ipynb_bytes(raw: bytes) -> list[dict[str, Any]]:
    """Decode an `.ipynb` blob into a list of frontend-friendly cells.

    Only ``code`` and ``markdown`` cells are returned. Each cell's
    ``outputs`` field is cleared to the empty list — notebook import is
    meant to seed a fresh editing session, not to carry over stale
    results from a foreign kernel.

    Raises
    ------
    ValueError
        If the blob is not valid JSON, not a v4-compatible notebook, or
        ``nbformat`` is not installed.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw must be bytes")

    # Strip UTF-8 BOM if present — some editors prepend one.
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]

    try:
        import nbformat  # type: ignore
    except ImportError as exc:  # pragma: no cover - env guard
        raise ValueError(
            "nbformat is required to parse .ipynb files; "
            "install it with `pip install nbformat`"
        ) from exc

    try:
        text = bytes(raw).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"ipynb must be UTF-8 encoded: {exc}") from exc

    try:
        nb = nbformat.reads(text, as_version=4)
    except Exception as exc:  # nbformat raises many distinct error classes
        raise ValueError(f"invalid notebook: {exc}") from exc

    cells: list[dict[str, Any]] = []
    for cell in getattr(nb, "cells", []) or []:
        cell_type = getattr(cell, "cell_type", None)
        if cell_type not in ("code", "markdown"):
            continue
        source = getattr(cell, "source", "")
        if isinstance(source, list):
            source = "".join(str(chunk) for chunk in source)
        cells.append(
            {
                "cell_type": cell_type,
                "source": source,
                "outputs": [],
            }
        )
    return cells


def list_ipynb_files(root: str) -> list[str]:
    """Return a sorted list of `.ipynb` file names directly under ``root``.

    Missing directories, file paths mistakenly passed as ``root``, and
    permission errors all resolve to an empty list so the caller can
    treat ``[]`` as "nothing to list" without branching on ``OSError``.
    """
    if not root:
        return []
    try:
        entries = os.listdir(root)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    except OSError:
        return []

    names: list[str] = []
    for name in entries:
        if not name.endswith(".ipynb"):
            continue
        full = os.path.join(root, name)
        try:
            if not os.path.isfile(full):
                continue
        except OSError:
            continue
        names.append(name)
    names.sort()
    return names


def resolve_ipynb_path(root: str, filename: str) -> str:
    """Resolve ``filename`` inside ``root`` with path-traversal guarding.

    Returns the absolute path as a string. Raises ``ValueError`` when:

    * ``filename`` is empty or has a non-``.ipynb`` extension
    * ``filename`` is absolute
    * the resolved path escapes ``root``
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("filename is required")
    if not filename.endswith(".ipynb"):
        raise ValueError("filename must end with .ipynb")
    if os.path.isabs(filename):
        raise ValueError("filename must be relative to root")

    root_abs = os.path.abspath(root)
    candidate = os.path.abspath(os.path.join(root_abs, filename))

    # Ensure candidate is strictly inside root_abs. commonpath() raises
    # on mixed drives (Windows) but on Linux we can rely on startswith
    # against ``root_abs + os.sep``. Handle the equality case explicitly
    # so root itself is not accepted as a file.
    root_with_sep = root_abs.rstrip(os.sep) + os.sep
    if candidate == root_abs or not candidate.startswith(root_with_sep):
        raise ValueError("filename escapes root directory")

    return candidate


def _build_notebook_bytes(cells: list[dict[str, Any]]) -> bytes:
    """Serialize ``cells`` into a v4 `.ipynb` byte blob.

    Raises ``ValueError`` for unsupported cell types or malformed entries.
    """
    try:
        import nbformat  # type: ignore
    except ImportError as exc:  # pragma: no cover - env guard
        raise ValueError(
            "nbformat is required to write .ipynb files; "
            "install it with `pip install nbformat`"
        ) from exc

    nb = nbformat.v4.new_notebook()
    for index, cell in enumerate(cells or []):
        if not isinstance(cell, dict):
            raise ValueError(f"cell {index} must be an object, got {type(cell).__name__}")
        cell_type = cell.get("cell_type")
        source = cell.get("source", "")
        if cell_type not in _ALLOWED_CELL_TYPES:
            raise ValueError(
                f"cell {index} has unsupported cell_type {cell_type!r}; "
                f"allowed: {list(_ALLOWED_CELL_TYPES)}"
            )
        if isinstance(source, list):
            source = "".join(str(chunk) for chunk in source)
        if not isinstance(source, str):
            raise ValueError(f"cell {index} source must be a string or list of strings")
        if cell_type == "code":
            nb.cells.append(nbformat.v4.new_code_cell(source=source))
        else:
            nb.cells.append(nbformat.v4.new_markdown_cell(source=source))
    return nbformat.writes(nb).encode("utf-8")


def create_empty_notebook(root: str, filename: str) -> str:
    """Create an empty `.ipynb` inside ``root``; return its absolute path.

    Parent directories are created on demand. Existing files are never
    overwritten — callers should delete first or use ``save_notebook``
    if they want to replace content.
    """
    os.makedirs(root, exist_ok=True)
    target = resolve_ipynb_path(root, filename)
    if os.path.exists(target):
        raise FileExistsError(f"notebook already exists: {target}")

    data = _build_notebook_bytes([])
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def save_notebook(root: str, filename: str, cells: list[dict[str, Any]]) -> str:
    """Write ``cells`` into ``root/filename``; return its absolute path.

    The parent directory is created on demand. Existing notebooks are
    replaced atomically-ish (write to temp, rename) so a crash in the
    middle of a save does not leave a half-written `.ipynb` on disk.
    """
    os.makedirs(root, exist_ok=True)
    target = resolve_ipynb_path(root, filename)
    data = _build_notebook_bytes(cells)

    tmp_path = target + ".tmp"
    with open(tmp_path, "wb") as handle:
        handle.write(data)
    os.replace(tmp_path, target)
    return target


def delete_notebook(root: str, filename: str) -> None:
    """Delete ``root/filename``; raise ``FileNotFoundError`` if absent."""
    target = resolve_ipynb_path(root, filename)
    os.remove(target)


_IGNORED_DIRS = {
    "node_modules",
    ".git",
    "dist",
    ".next",
    "__pycache__",
    ".cache",
    ".turbo",
    "coverage",
    ".output",
    "build",
    ".venv",
    "venv",
    "env",
}
_MAX_DEPTH = 6
_MAX_RESULTS = 500
_NOTEBOOKS_SUBDIR = "notebooks"
_MAX_AUTO_SUFFIX = 999


def derive_notebook_id(file_path: str) -> str:
    target = str(Path(file_path).expanduser().resolve())
    return "nbk_" + hashlib.sha256(target.encode("utf-8")).hexdigest()[:24]


def resolve_workspace_root(workspace: str) -> str:
    return str(_validate_workspace(workspace))


def resolve_workspace_notebook_target(
    path: str,
    workspace: str | None = None,
) -> tuple[str, str]:
    workspace_real, target_real = _resolve_workspace_and_target(workspace, path)
    return str(workspace_real), str(target_real)


def _generate_cell_id() -> str:
    return secrets.token_hex(4)


def _generate_notebook_id() -> str:
    return f"nb_{secrets.token_hex(4)}_{int(time.time() * 1000):x}"


def _join_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _normalize_notebook(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("notebook must be an object")

    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    omicsclaw_meta = metadata.get("omicsclaw")
    if not isinstance(omicsclaw_meta, dict):
        omicsclaw_meta = {}
    if not omicsclaw_meta.get("notebook_id"):
        omicsclaw_meta["notebook_id"] = _generate_notebook_id()
    metadata = {**metadata, "omicsclaw": omicsclaw_meta}

    cells: list[dict[str, Any]] = []
    for cell in raw.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or not cell_id:
            cell_id = _generate_cell_id()
        cell_metadata = cell.get("metadata")
        if not isinstance(cell_metadata, dict):
            cell_metadata = {}
        source = _join_text(cell.get("source", ""))
        cell_type = cell.get("cell_type")
        if cell_type == "code":
            execution_count = cell.get("execution_count")
            if not isinstance(execution_count, int):
                execution_count = None
            outputs = cell.get("outputs")
            if not isinstance(outputs, list):
                outputs = []
            cells.append({
                "id": cell_id,
                "cell_type": "code",
                "source": source,
                "execution_count": execution_count,
                "outputs": outputs,
                "metadata": cell_metadata,
            })
        elif cell_type == "markdown":
            cells.append({
                "id": cell_id,
                "cell_type": "markdown",
                "source": source,
                "metadata": cell_metadata,
            })
        else:
            cells.append({
                "id": cell_id,
                "cell_type": "raw",
                "source": source,
                "metadata": cell_metadata,
            })

    nbformat = raw.get("nbformat")
    if not isinstance(nbformat, int):
        nbformat = 4
    nbformat_minor = raw.get("nbformat_minor")
    if not isinstance(nbformat_minor, int):
        nbformat_minor = 5

    return {
        "cells": cells,
        "metadata": metadata,
        "nbformat": nbformat,
        "nbformat_minor": nbformat_minor,
    }


def _serialize_notebook(raw: dict[str, Any]) -> str:
    return json_dumps(_normalize_notebook(raw)) + "\n"


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, ensure_ascii=False)


def _empty_notebook(language: str = "python") -> dict[str, Any]:
    return {
        "cells": [
            {
                "id": _generate_cell_id(),
                "cell_type": "code",
                "source": "",
                "execution_count": None,
                "outputs": [],
                "metadata": {},
            }
        ],
        "metadata": {
            "kernelspec": {
                "name": language,
                "display_name": "Python 3" if language == "python" else language,
                "language": language,
            },
            "language_info": {"name": language},
            "omicsclaw": {"notebook_id": _generate_notebook_id()},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _trusted_workspace_roots() -> list[Path]:
    roots: list[Path] = []
    current_workspace = str(os.environ.get("OMICSCLAW_WORKSPACE", "") or "").strip()
    if current_workspace:
        roots.append(Path(current_workspace))

    extra = str(os.environ.get("OMICSCLAW_DATA_DIRS", "") or "").strip()
    if extra:
        for raw_item in extra.split(","):
            text = raw_item.strip()
            if text:
                roots.append(Path(text))

    try:
        from omicsclaw.app import server as app_server

        core = getattr(app_server, "_core", None)
        if core is not None:
            for entry in getattr(core, "TRUSTED_DATA_DIRS", []) or []:
                roots.append(Path(entry))
    except Exception:
        pass

    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        resolved = root.expanduser().resolve()
        token = str(resolved)
        if token in seen:
            continue
        unique.append(resolved)
        seen.add(token)
    return unique


def _is_inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _realpath_or_ancestor(target: Path) -> Path:
    target = target.expanduser()
    missing_parts: list[str] = []
    current = target
    while not current.exists():
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(f"path does not exist: {target}")
        missing_parts.append(current.name)
        current = parent
    current_real = current.resolve()
    for part in reversed(missing_parts):
        current_real = current_real / part
    return current_real


def _validate_workspace(workspace: str) -> Path:
    if not workspace or not isinstance(workspace, str):
        raise ValueError("workspace is required")

    workspace_path = Path(workspace).expanduser()
    if not workspace_path.is_absolute():
        raise ValueError("workspace must be an absolute path")

    try:
        workspace_real = workspace_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileNotFoundError("workspace directory does not exist") from exc

    if not workspace_real.is_dir():
        raise ValueError("workspace is not a directory")

    trusted_roots = _trusted_workspace_roots()
    if trusted_roots and not any(_is_inside(workspace_real, root) for root in trusted_roots):
        raise ValueError("workspace is outside the trusted scope")

    return workspace_real


def _resolve_target_in_workspace(workspace_real: Path, target: str) -> Path:
    if not target or not isinstance(target, str):
        raise ValueError("path is required")

    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = workspace_real / target_path

    target_real = _realpath_or_ancestor(target_path)
    if not _is_inside(target_real, workspace_real):
        raise ValueError("target path escapes the workspace")
    return target_real


def _resolve_workspace_and_target(workspace: str | None, target: str) -> tuple[Path, Path]:
    if workspace:
        workspace_real = _validate_workspace(workspace)
        return workspace_real, _resolve_target_in_workspace(workspace_real, target)

    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        raise ValueError("path must be absolute when workspace is omitted")

    target_real = _realpath_or_ancestor(target_path)
    trusted_roots = _trusted_workspace_roots()
    best_workspace: Path | None = None
    best_length = -1
    for root in trusted_roots:
        if _is_inside(target_real, root):
            length = len(str(root))
            if length > best_length:
                best_workspace = root
                best_length = length

    if best_workspace is None:
        best_workspace = target_real.parent.resolve()

    return best_workspace, target_real


def list_workspace_notebooks(workspace: str) -> list[dict[str, Any]]:
    workspace_real = Path(resolve_workspace_root(workspace))
    results: list[dict[str, Any]] = []

    def walk(current_dir: Path, depth: int) -> None:
        if depth > _MAX_DEPTH or len(results) >= _MAX_RESULTS:
            return
        try:
            entries = list(current_dir.iterdir())
        except OSError:
            return

        for entry in entries:
            if len(results) >= _MAX_RESULTS:
                return
            name = entry.name
            if name.startswith(".") and name != ".":
                continue
            try:
                if entry.is_dir():
                    if name in _IGNORED_DIRS:
                        continue
                    walk(entry, depth + 1)
                elif entry.is_file() and name.lower().endswith(".ipynb"):
                    real_entry = entry.resolve()
                    if not _is_inside(real_entry, workspace_real):
                        continue
                    stat = real_entry.stat()
                    results.append({
                        "path": str(real_entry),
                        "relativePath": real_entry.relative_to(workspace_real).as_posix(),
                        "name": real_entry.stem,
                        "mtime": stat.st_mtime * 1000,
                        "size": stat.st_size,
                    })
            except OSError:
                continue

    walk(workspace_real, 0)
    results.sort(key=lambda item: float(item.get("mtime", 0)), reverse=True)
    return results


def open_workspace_notebook(path: str, workspace: str | None = None) -> tuple[str, str, dict[str, Any]]:
    workspace_real, target_real = resolve_workspace_notebook_target(path, workspace)
    target_path = Path(target_real)
    if target_path.suffix.lower() != ".ipynb":
        raise ValueError("File must end with .ipynb")
    if not target_path.exists():
        raise FileNotFoundError("notebook not found")
    if not target_path.is_file():
        raise ValueError("Path is not a file")

    import json

    try:
        notebook = _normalize_notebook(json.loads(target_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid notebook JSON: {exc}") from exc

    return workspace_real, target_real, notebook


def create_workspace_notebook(workspace: str) -> str:
    workspace_real = _validate_workspace(workspace)
    notebooks_dir = workspace_real / _NOTEBOOKS_SUBDIR
    notebooks_dir.mkdir(parents=True, exist_ok=True)
    notebooks_real = notebooks_dir.resolve()
    if not _is_inside(notebooks_real, workspace_real):
        raise ValueError(f"{_NOTEBOOKS_SUBDIR}/ escapes workspace via a symlink")

    payload = _serialize_notebook(_empty_notebook())
    for index in range(1, _MAX_AUTO_SUFFIX + 1):
        candidate = notebooks_real / f"Untitled-{index}.ipynb"
        try:
            with open(candidate, "x", encoding="utf-8") as handle:
                handle.write(payload)
            return str(candidate.resolve())
        except FileExistsError:
            continue
    raise OSError(f"Could not pick a free Untitled-N name (1..{_MAX_AUTO_SUFFIX} all taken)")


def save_workspace_notebook(workspace: str, path: str, notebook: dict[str, Any]) -> str:
    workspace_real = _validate_workspace(workspace)
    target_real = _resolve_target_in_workspace(workspace_real, path)
    if target_real.suffix.lower() != ".ipynb":
        raise ValueError("File must end with .ipynb")

    parent = target_real.parent
    if not parent.exists():
        raise FileNotFoundError("Parent directory does not exist")
    if not parent.is_dir():
        raise ValueError("Parent path is not a directory")

    target_real.write_text(_serialize_notebook(notebook), encoding="utf-8")
    return str(target_real)


def delete_workspace_notebook(workspace: str, path: str) -> str:
    workspace_real = _validate_workspace(workspace)
    target_real = _resolve_target_in_workspace(workspace_real, path)
    if target_real.suffix.lower() != ".ipynb":
        raise ValueError("File must end with .ipynb")
    if not target_real.exists():
        raise FileNotFoundError("notebook not found")
    if not target_real.is_file():
        raise ValueError("Path is not a regular file")
    target_real.unlink()
    return str(target_real)
