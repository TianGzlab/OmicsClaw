"""Tests for the NotebookSession and notebook tools integration.

These tests verify the new CellVoyager-inspired notebook execution
layer that enables the coding-agent to run OmicsClaw skill functions
in Jupyter notebooks.

Tests are split into two groups:
1. Unit tests for NotebookSession (require nbformat + jupyter_client)
2. Config/registry tests (no optional deps needed)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# =========================================================================
# Config & registry tests (no optional deps)
# =========================================================================


class TestNotebookToolsConfig:
    """Tests for notebook tool registration in config.yaml."""

    def test_coding_agent_has_notebook_tools(self):
        """coding-agent in config.yaml must declare notebook and search tools."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        coding_tools = config["coding-agent"]["tools"]
        assert "skill_search" in coding_tools
        assert "notebook_create" in coding_tools
        assert "notebook_add_execute" in coding_tools
        assert "notebook_read" in coding_tools
        assert "notebook_read_cell" in coding_tools

    def test_analysis_agent_has_notebook_read_tools(self):
        """analysis-agent must have notebook_read and notebook_read_cell."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        analysis_tools = config["analysis-agent"]["tools"]
        assert "notebook_read" in analysis_tools
        assert "notebook_read_cell" in analysis_tools

    def test_planner_agent_has_self_critique(self):
        """planner-agent system_prompt must contain self-critique protocol."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        prompt = config["planner-agent"]["system_prompt"]
        assert "SELF-CRITIQUE" in prompt
        assert "initial plan AND the revised plan" in prompt

    def test_coding_agent_has_skill_function_constraint(self):
        """coding-agent prompt must enforce skill search + fallback logic."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        prompt = config["coding-agent"]["system_prompt"]
        assert "SEARCH FOR SKILLS" in prompt
        assert "TIER 1" in prompt
        assert "TIER 2" in prompt
        assert "skill_search" in prompt

    def test_notebook_tools_in_registry(self):
        """build_tool_registry() should include all notebook + search tools."""
        from omicsclaw.agents.tools import build_tool_registry
        registry = build_tool_registry()
        assert "skill_search" in registry
        assert "notebook_create" in registry
        assert "notebook_add_execute" in registry
        assert "notebook_read" in registry
        assert "notebook_read_cell" in registry

    def test_skill_search_returns_results(self):
        """skill_search tool should find skills matching keywords."""
        from omicsclaw.agents.tools import skill_search
        result = skill_search.invoke({"query": "preprocessing"})
        assert "preprocessing" in result.lower() or "preprocess" in result.lower()

    def test_skill_search_domain_filter(self):
        """skill_search with domain filter should narrow results."""
        from omicsclaw.agents.tools import skill_search
        result = skill_search.invoke({"query": "", "domain": "spatial"})
        assert "spatial" in result.lower()

    def test_skill_search_no_results(self):
        """skill_search with unknown keyword should return fallback message."""
        from omicsclaw.agents.tools import skill_search
        result = skill_search.invoke({"query": "quantum_teleportation_xyz"})
        assert "No skills found" in result


# =========================================================================
# NotebookSession unit tests (require nbformat + jupyter_client)
# =========================================================================


def _has_notebook_deps():
    """Check if notebook deps are available."""
    try:
        import nbformat  # noqa: F401
        import jupyter_client  # noqa: F401
        return True
    except ImportError:
        return False


def _has_local_socket_runtime():
    """Jupyter kernels need loopback sockets; sandboxed CI may forbid them."""
    try:
        import socket

        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", 0))
        finally:
            sock.close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(
    (not _has_notebook_deps()) or (not _has_local_socket_runtime()),
    reason="Notebook runtime unavailable (missing deps or local sockets blocked)",
)
class TestNotebookSession:
    """Tests for the NotebookSession class."""

    def test_create_notebook(self, tmp_path):
        """NotebookSession creates a .ipynb file."""
        from omicsclaw.agents.notebook_session import NotebookSession

        nb_path = str(tmp_path / "test.ipynb")
        session = NotebookSession(nb_path)
        try:
            assert Path(nb_path).exists()
            # Should be valid JSON (nbformat)
            with open(nb_path) as f:
                data = json.load(f)
            assert "cells" in data
            assert "nbformat" in data
        finally:
            session.shutdown()

    def test_insert_code_cell(self, tmp_path):
        """insert_cell adds a code cell."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            result = session.insert_cell(None, "code", "x = 42")
            assert result["ok"] is True
            assert result["cell_type"] == "code"
            assert result["num_cells"] >= 1
        finally:
            session.shutdown()

    def test_insert_markdown_cell(self, tmp_path):
        """insert_cell adds a markdown cell."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            result = session.insert_cell(None, "markdown", "# Title")
            assert result["ok"] is True
            assert result["cell_type"] == "markdown"
        finally:
            session.shutdown()

    def test_execute_simple_code(self, tmp_path):
        """Execute a simple print statement and verify output."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            result = session.insert_execute_code_cell(None, 'print("hello_oc")')
            assert result["ok"] is True
            assert "hello_oc" in result["output_preview"]
        finally:
            session.shutdown()

    def test_execute_error_capture(self, tmp_path):
        """Executing bad code should capture the error."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            result = session.insert_execute_code_cell(None, "1/0")
            assert result["ok"] is False
            assert result["error"] is not None
            assert "ZeroDivisionError" in result["error"]
        finally:
            session.shutdown()

    def test_read_notebook_structure(self, tmp_path):
        """read_notebook returns correct cell count and structure."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            session.insert_cell(None, "markdown", "# Analysis")
            session.insert_execute_code_cell(None, "x = 1 + 1\nprint(x)")

            info = session.read_notebook()
            assert info["ok"] is True
            assert info["num_cells"] >= 2
            # Find our cells
            types = [c["cell_type"] for c in info["cells"]]
            assert "markdown" in types
            assert "code" in types
        finally:
            session.shutdown()

    def test_read_cell(self, tmp_path):
        """read_cell returns full source and output for a cell."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            session.insert_execute_code_cell(None, 'msg = "test_read"\nprint(msg)')
            idx = len(session.nb.cells) - 1
            info = session.read_cell(idx)
            assert info["ok"] is True
            assert "test_read" in info["source"]
            assert "test_read" in info["output_preview"]
        finally:
            session.shutdown()

    def test_overwrite_cell(self, tmp_path):
        """overwrite_cell_source replaces source and clears outputs."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            session.insert_execute_code_cell(None, "print('old')")
            idx = len(session.nb.cells) - 1
            result = session.overwrite_cell_source(idx, "print('new')")
            assert result["ok"] is True
            # Re-read and verify source changed
            cell_info = session.read_cell(idx)
            assert "new" in cell_info["source"]
        finally:
            session.shutdown()

    def test_kernel_restart(self, tmp_path):
        """restart_kernel clears state."""
        from omicsclaw.agents.notebook_session import NotebookSession

        session = NotebookSession(str(tmp_path / "test.ipynb"))
        try:
            session.insert_execute_code_cell(None, "my_var_123 = 42")
            result = session.restart_kernel()
            assert result["ok"] is True
            # Variable should be gone after restart
            check = session.insert_execute_code_cell(None, "print(my_var_123)")
            assert check["ok"] is False  # NameError
        finally:
            session.shutdown()
