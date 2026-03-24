"""Jupyter Notebook Session Manager for the OmicsClaw Research Pipeline.

Provides ``NotebookSession`` — a persistent Jupyter kernel backed
``.ipynb`` editing and execution engine.  Adapted from CellVoyager's
``NotebookSession`` design, tailored for OmicsClaw's multi-omics
skill-function workflow.

Usage::

    session = NotebookSession("/tmp/analysis.ipynb")
    session.insert_execute_code_cell(None,
        'from skills.spatial.spatial_preprocess import preprocess\\n'
        'adata, summary = preprocess(adata, min_genes=200)')
    print(session.read_cell(0))
    session.shutdown()
"""

from __future__ import annotations

import logging
import queue
import sys
from pathlib import Path
from typing import Any

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook, new_output

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KERNEL_TIMEOUT = 120  # seconds to wait for kernel ready
_IOPUB_TIMEOUT = 5     # seconds per iopub message poll
_EXEC_TIMEOUT = 600    # max wall-clock seconds for a single cell execution
_MAX_PREVIEW = 4000    # characters for output previews

# ---------------------------------------------------------------------------
# OmicsClaw project root (for PYTHONPATH injection into kernel)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class NotebookSession:
    """Manage a ``.ipynb`` file backed by a live Jupyter kernel.

    The kernel persists across cell executions so that variables (like
    ``adata``) survive between steps — enabling OmicsClaw skill functions
    to share in-memory data objects.

    Parameters
    ----------
    notebook_path : str
        Absolute path to the ``.ipynb`` file.  Created if missing.
    kernel_name : str
        Jupyter kernel spec name (default ``"python3"``).
    """

    def __init__(self, notebook_path: str, kernel_name: str = "python3"):
        self.path = Path(notebook_path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Load or create notebook
        if self.path.exists():
            self.nb = nbf.read(self.path, as_version=4)
            logger.info("Loaded existing notebook: %s (%d cells)", self.path, len(self.nb.cells))
        else:
            self.nb = new_notebook()
            logger.info("Created new notebook: %s", self.path)

        # Start kernel
        from jupyter_client import KernelManager

        self.km = KernelManager(kernel_name=kernel_name)
        self.km.start_kernel(cwd=str(self.path.parent))
        self.kc = self.km.client()
        self.kc.start_channels()
        self.kc.wait_for_ready(timeout=_KERNEL_TIMEOUT)

        # Bootstrap: set up matplotlib inline, suppress warnings, inject PYTHONPATH,
        # and provide the load_skill() helper that handles hyphenated skill dirs.
        bootstrap = (
            "%matplotlib inline\n"
            "import warnings\n"
            "warnings.filterwarnings('ignore')\n"
            "import sys, os, importlib.util\n"
            f"sys.path.insert(0, r'''{_PROJECT_ROOT}''')\n"
            f"os.chdir(r'''{self.path.parent}''')\n"
            "\n"
            "# ── OmicsClaw skill loader ──────────────────────────────\n"
            "def load_skill(name):\n"
            "    '''Load an OmicsClaw skill module by name, e.g. load_skill(\"spatial-preprocess\").\n"
            "    Returns the module object so you can call its functions directly:\n"
            "        mod = load_skill(\"spatial-preprocess\")\n"
            "        adata, summary = mod.preprocess(adata, min_genes=200)\n"
            "    '''\n"
            "    from omicsclaw.core.registry import OmicsRegistry\n"
            "    reg = OmicsRegistry()\n"
            "    reg.load_all()\n"
            "    info = reg.skills.get(name)\n"
            "    if not info:\n"
            "        raise ValueError(f'Skill {name!r} not found. Use load_skill() with '"
            "                         f'a valid skill name from `oc list`.')\n"
            "    script = info.get('script', '')\n"
            "    if not script or not os.path.exists(script):\n"
            "        raise FileNotFoundError(f'Script not found for {name}: {script}')\n"
            "    mod_name = name.replace('-', '_')\n"
            "    spec = importlib.util.spec_from_file_location(mod_name, script)\n"
            "    mod = importlib.util.module_from_spec(spec)\n"
            "    spec.loader.exec_module(mod)\n"
            "    return mod\n"
            "\n"
            "print('✓ OmicsClaw kernel ready. Use load_skill(\"skill-name\") to load skills.')\n"
        )
        self._execute_source(bootstrap)
        self.save()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write current notebook state to disk."""
        with open(self.path, "w", encoding="utf-8") as f:
            nbf.write(self.nb, f)

    def shutdown(self) -> None:
        """Stop kernel and release resources."""
        try:
            self.kc.stop_channels()
        except Exception:
            pass
        try:
            self.km.shutdown_kernel(now=True)
        except Exception:
            pass
        logger.info("Notebook session shut down: %s", self.path)

    def restart_kernel(self) -> dict[str, Any]:
        """Restart the kernel (clears all in-memory state)."""
        self.shutdown()

        from jupyter_client import KernelManager

        self.km = KernelManager()
        self.km.start_kernel(cwd=str(self.path.parent))
        self.kc = self.km.client()
        self.kc.start_channels()
        self.kc.wait_for_ready(timeout=_KERNEL_TIMEOUT)

        # Re-run the same bootstrap (includes load_skill helper)
        bootstrap = (
            "%matplotlib inline\n"
            "import warnings\n"
            "warnings.filterwarnings('ignore')\n"
            "import sys, os, importlib.util\n"
            f"sys.path.insert(0, r'''{_PROJECT_ROOT}''')\n"
            f"os.chdir(r'''{self.path.parent}''')\n"
            "\n"
            "def load_skill(name):\n"
            "    from omicsclaw.core.registry import OmicsRegistry\n"
            "    reg = OmicsRegistry()\n"
            "    reg.load_all()\n"
            "    info = reg.skills.get(name)\n"
            "    if not info: raise ValueError(f'Skill {name!r} not found')\n"
            "    script = info.get('script', '')\n"
            "    if not script or not os.path.exists(script): raise FileNotFoundError(f'Script: {script}')\n"
            "    spec = importlib.util.spec_from_file_location(name.replace('-','_'), script)\n"
            "    mod = importlib.util.module_from_spec(spec)\n"
            "    spec.loader.exec_module(mod)\n"
            "    return mod\n"
        )
        self._execute_source(bootstrap)
        return {"ok": True, "message": "Kernel restarted. All in-memory variables cleared."}

    # ------------------------------------------------------------------
    # Cell CRUD
    # ------------------------------------------------------------------

    def _normalize_insert_index(self, index: int | None) -> int:
        if index is None or index < 0 or index > len(self.nb.cells):
            return len(self.nb.cells)
        return index

    def _require_index(self, index: int) -> None:
        if index < 0 or index >= len(self.nb.cells):
            raise IndexError(
                f"Cell index {index} out of range (0..{len(self.nb.cells) - 1})"
            )

    def insert_cell(
        self, index: int | None, cell_type: str, source: str
    ) -> dict[str, Any]:
        """Insert a markdown or code cell at *index* (append if ``None``)."""
        index = self._normalize_insert_index(index)

        if cell_type == "markdown":
            cell = new_markdown_cell(source)
        elif cell_type == "code":
            cell = new_code_cell(source)
        else:
            raise ValueError("cell_type must be 'markdown' or 'code'")

        self.nb.cells.insert(index, cell)
        self.save()
        return {
            "ok": True,
            "cell_index": index,
            "cell_type": cell_type,
            "num_cells": len(self.nb.cells),
        }

    def overwrite_cell_source(self, index: int, source: str) -> dict[str, Any]:
        """Replace the source of an existing cell."""
        self._require_index(index)
        self.nb.cells[index].source = source
        if self.nb.cells[index].cell_type == "code":
            self.nb.cells[index]["outputs"] = []
            self.nb.cells[index]["execution_count"] = None
        self.save()
        return {"ok": True, "cell_index": index}

    def delete_cell(self, index: int) -> dict[str, Any]:
        """Delete cell at *index*."""
        self._require_index(index)
        deleted_type = self.nb.cells[index].cell_type
        del self.nb.cells[index]
        self.save()
        return {
            "ok": True,
            "deleted_index": index,
            "deleted_type": deleted_type,
            "num_cells": len(self.nb.cells),
        }

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_notebook(self) -> dict[str, Any]:
        """Return an overview of all cells (source + output previews)."""
        # Re-read from disk to pick up user edits made in Jupyter UI
        if self.path.exists():
            self.nb = nbf.read(self.path, as_version=4)

        cells = []
        for i, cell in enumerate(self.nb.cells):
            cells.append(
                {
                    "index": i,
                    "cell_type": cell.cell_type,
                    "source_preview": self._trim(cell.source, 600),
                    "output_preview": self._cell_output_preview(cell, 1200),
                }
            )
        return {
            "ok": True,
            "notebook_path": str(self.path),
            "num_cells": len(self.nb.cells),
            "cells": cells,
        }

    def read_cell(self, index: int) -> dict[str, Any]:
        """Return full source and output for a single cell."""
        self._require_index(index)
        cell = self.nb.cells[index]
        return {
            "ok": True,
            "cell_index": index,
            "cell_type": cell.cell_type,
            "source": cell.source,
            "output_preview": self._cell_output_preview(cell, _MAX_PREVIEW),
            "execution_count": cell.get("execution_count"),
        }

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute_cell(self, index: int) -> dict[str, Any]:
        """Execute an existing code cell and store outputs in the notebook."""
        self._require_index(index)
        cell = self.nb.cells[index]
        if cell.cell_type != "code":
            raise ValueError(f"Cell {index} is not a code cell")

        source = cell.source
        if isinstance(source, list):
            source = "\n".join(source)

        result = self._execute_source(source)

        cell["outputs"] = result["outputs"]
        cell["execution_count"] = result["execution_count"]
        self.save()

        return {
            "ok": result["ok"],
            "cell_index": index,
            "execution_count": result["execution_count"],
            "output_preview": result["preview"],
            "error": result.get("error"),
        }

    def insert_execute_code_cell(
        self, index: int | None, source: str
    ) -> dict[str, Any]:
        """Insert a code cell and immediately execute it (convenience combo)."""
        inserted = self.insert_cell(index=index, cell_type="code", source=source)
        idx = inserted["cell_index"]
        executed = self.execute_cell(idx)
        return {
            "ok": executed["ok"],
            "cell_index": idx,
            "execution_count": executed["execution_count"],
            "output_preview": executed["output_preview"],
            "error": executed.get("error"),
        }

    # ------------------------------------------------------------------
    # Internal: kernel message loop
    # ------------------------------------------------------------------

    def _execute_source(self, source: str) -> dict[str, Any]:
        """Send *source* to the kernel and collect outputs.

        Applies a global execution timeout (``_EXEC_TIMEOUT`` seconds) in
        addition to the per-message ``_IOPUB_TIMEOUT``.  If the kernel produces
        no ``status: idle`` within the limit, the execution is considered timed
        out and an error is returned.
        """
        import time

        msg_id = self.kc.execute(source, allow_stdin=False, stop_on_error=False)

        outputs: list = []
        execution_count = None
        error_text = None
        wall_start = time.monotonic()

        while True:
            # ── Global timeout guard ─────────────────────────────────
            elapsed = time.monotonic() - wall_start
            if elapsed > _EXEC_TIMEOUT:
                error_text = (
                    f"Cell execution timed out after {_EXEC_TIMEOUT}s. "
                    "Consider reducing the workload (subset the data, "
                    "fewer epochs, etc.) or running in background."
                )
                logger.warning(error_text)
                outputs.append(
                    new_output(
                        output_type="error",
                        ename="TimeoutError",
                        evalue=error_text,
                        traceback=[error_text],
                    )
                )
                break

            try:
                msg = self.kc.get_iopub_msg(timeout=_IOPUB_TIMEOUT)
            except queue.Empty:
                continue
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue

            msg_type = msg["msg_type"]
            content = msg["content"]

            if msg_type == "status":
                if content.get("execution_state") == "idle":
                    break

            elif msg_type == "execute_input":
                execution_count = content.get("execution_count", execution_count)

            elif msg_type == "stream":
                outputs.append(
                    new_output(
                        output_type="stream",
                        name=content["name"],
                        text=content["text"],
                    )
                )

            elif msg_type == "display_data":
                outputs.append(
                    new_output(
                        output_type="display_data",
                        data=content["data"],
                        metadata=content.get("metadata", {}),
                    )
                )

            elif msg_type == "execute_result":
                execution_count = content.get("execution_count", execution_count)
                outputs.append(
                    new_output(
                        output_type="execute_result",
                        data=content["data"],
                        metadata=content.get("metadata", {}),
                        execution_count=execution_count,
                    )
                )

            elif msg_type == "error":
                outputs.append(
                    new_output(
                        output_type="error",
                        ename=content["ename"],
                        evalue=content["evalue"],
                        traceback=content["traceback"],
                    )
                )
                error_text = "\n".join(content["traceback"][-8:])

            elif msg_type == "clear_output":
                outputs = []

        preview = self._outputs_preview(outputs, _MAX_PREVIEW)
        ok = error_text is None
        return {
            "ok": ok,
            "outputs": outputs,
            "execution_count": execution_count,
            "preview": preview,
            "error": error_text,
        }

    # ------------------------------------------------------------------
    # Format helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        text = text or ""
        return text if len(text) <= limit else text[:limit] + "...[truncated]"

    def _cell_output_preview(self, cell: Any, limit: int) -> str:
        outputs = cell.get("outputs", []) if cell.cell_type == "code" else []
        return self._outputs_preview(outputs, limit)

    def _outputs_preview(self, outputs: list[Any], limit: int) -> str:
        parts: list[str] = []
        for out in outputs:
            ot = out.get("output_type")
            if ot == "stream":
                parts.append(out.get("text", ""))
            elif ot in ("display_data", "execute_result"):
                data = out.get("data", {})
                if "text/plain" in data:
                    parts.append(str(data["text/plain"]))
                elif "image/png" in data:
                    parts.append("[image/png output]")
                elif "text/html" in data:
                    parts.append("[text/html output]")
                else:
                    parts.append("[rich output]")
            elif ot == "error":
                parts.append("\n".join(out.get("traceback", [])))
        joined = "\n".join(parts).strip()
        return self._trim(joined, limit)

