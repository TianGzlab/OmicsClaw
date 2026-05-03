"""Controlled notebook execution for autonomous fallback analyses."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path
import textwrap
import uuid
from typing import Any

from omicsclaw.common.manifest import StepRecord
from omicsclaw.common.report import build_output_dir_name
from omicsclaw.agents.notebook_session import NotebookSession
from omicsclaw.runtime.hooks import build_default_lifecycle_hook_runtime
from omicsclaw.runtime.verification import (
    COMPLETION_STATUS_FAILED,
    WORKSPACE_KIND_ANALYSIS_RUN,
    ArtifactRequirement,
    build_completion_report,
    update_workspace_manifest,
    write_completion_report,
)
from omicsclaw.version import __version__

_OMICSCLAW_ROOT = Path(__file__).resolve().parents[2]


_BLOCKED_IMPORTS = {
    "subprocess",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "urllib.request",
    "ftplib",
    "paramiko",
    "webbrowser",
    "pip",
}

_BLOCKED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
}

_BLOCKED_ATTRS = {
    "system",
    "popen",
    "Popen",
    "run",
    "call",
    "check_call",
    "check_output",
    "spawn",
    "reload",
}

_BLOCKED_TEXT_SNIPPETS = (
    "!pip",
    "%pip",
    "pip install",
    "!wget",
    "!curl",
    "os.system(",
    "subprocess.",
    "requests.",
    "httpx.",
    "socket.",
)

AUTONOMOUS_ANALYSIS_VERSION = __version__


def validate_custom_analysis_code(source: str) -> list[str]:
    """Validate generated Python before sending it to the notebook kernel."""
    issues: list[str] = []
    source = source or ""

    for snippet in _BLOCKED_TEXT_SNIPPETS:
        if snippet in source:
            issues.append(f"blocked code pattern: {snippet}")

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _BLOCKED_IMPORTS:
                    issues.append(f"blocked import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _BLOCKED_IMPORTS:
                issues.append(f"blocked import-from: {module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
                issues.append(f"blocked call: {node.func.id}()")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in _BLOCKED_ATTRS:
                value = node.func.value
                owner = value.id if isinstance(value, ast.Name) else "object"
                issues.append(f"blocked attribute call: {owner}.{node.func.attr}()")

    return sorted(set(issues))


def _json_literal(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _safe_setup_code(
    *,
    goal: str,
    context: str,
    web_context: str,
    input_file: str,
    output_dir: str,
) -> str:
    """Bootstrap the notebook with bounded execution helpers."""
    return textwrap.dedent(
        f"""
        ANALYSIS_GOAL = {_json_literal(goal)}
        ANALYSIS_CONTEXT = {_json_literal(context)}
        WEB_CONTEXT = {_json_literal(web_context)}
        INPUT_FILE = {_json_literal(input_file)}
        AUTONOMOUS_OUTPUT_DIR = {_json_literal(output_dir)}

        import pathlib
        import subprocess as _subprocess
        import socket as _socket

        def _blocked(*args, **kwargs):
            raise RuntimeError("custom_analysis_execute blocks shell/network/package-install actions")

        _subprocess.run = _blocked
        _subprocess.Popen = _blocked
        _subprocess.call = _blocked
        _subprocess.check_call = _blocked
        _subprocess.check_output = _blocked
        _socket.socket = _blocked

        try:
            import requests as _requests
            _requests.get = _blocked
            _requests.post = _blocked
            _requests.put = _blocked
            _requests.delete = _blocked
        except Exception:
            pass

        try:
            import httpx as _httpx
            _httpx.get = _blocked
            _httpx.post = _blocked
            _httpx.put = _blocked
            _httpx.delete = _blocked
        except Exception:
            pass

        OUTPUT_PATH = pathlib.Path(AUTONOMOUS_OUTPUT_DIR)
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

        print("Autonomous notebook ready.")
        print("INPUT_FILE =", INPUT_FILE or "<none>")
        print("OUTPUT_PATH =", OUTPUT_PATH)
        """
    ).strip()


def _autonomous_analysis_requirements() -> list[ArtifactRequirement]:
    return [
        ArtifactRequirement(
            name="analysis_plan",
            path="analysis_plan.md",
            description="Human-readable autonomous analysis plan.",
        ),
        ArtifactRequirement(
            name="web_sources",
            path="web_sources.md",
            description="Captured web references or source notes.",
        ),
        ArtifactRequirement(
            name="capability_decision",
            path="capability_decision.json",
            description="Capability resolver decision snapshot.",
        ),
        ArtifactRequirement(
            name="result_summary",
            path="result_summary.md",
            description="Top-level execution summary.",
        ),
        ArtifactRequirement(
            name="notebook",
            path="reproducibility/analysis_notebook.ipynb",
            description="Reproducibility notebook for the autonomous run.",
        ),
        ArtifactRequirement(
            name="workspace_manifest",
            path="manifest.json",
            description="Workspace lineage and verification ledger.",
        ),
    ]


def run_autonomous_analysis(
    *,
    output_root: str,
    goal: str,
    analysis_plan: str,
    python_code: str,
    context: str = "",
    web_context: str = "",
    input_file: str = "",
    sources: str = "",
    capability_decision: dict | None = None,
    output_label: str = "autonomous-analysis",
) -> dict[str, Any]:
    """Execute custom analysis code in a constrained notebook session."""
    hook_runtime = build_default_lifecycle_hook_runtime(_OMICSCLAW_ROOT)
    issues = validate_custom_analysis_code(python_code)
    if issues:
        return {
            "ok": False,
            "error": "Blocked custom analysis code:\n- " + "\n- ".join(issues),
        }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_root) / build_output_dir_name(
        output_label,
        ts,
        unique_suffix=uuid.uuid4().hex[:8],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    repro_dir = out_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    plan_path = out_dir / "analysis_plan.md"
    sources_path = out_dir / "web_sources.md"
    capability_path = out_dir / "capability_decision.json"
    summary_path = out_dir / "result_summary.md"
    notebook_path = repro_dir / "analysis_notebook.ipynb"
    requirements = _autonomous_analysis_requirements()
    manifest_metadata = {
        "goal": goal,
        "output_label": output_label,
        "input_file": input_file,
        "has_web_context": bool(web_context.strip()),
        "has_sources": bool((sources or "").strip()),
    }

    plan_path.write_text((analysis_plan or goal or "").strip() + "\n", encoding="utf-8")
    sources_path.write_text((sources or web_context or "No external sources captured.\n"), encoding="utf-8")
    capability_payload = capability_decision or {}
    capability_path.write_text(
        json.dumps(capability_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_path = update_workspace_manifest(
        out_dir,
        workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
        workspace_purpose="autonomous_analysis",
        requirements=requirements,
        step=StepRecord(
            skill="custom_analysis_execute",
            version=AUTONOMOUS_ANALYSIS_VERSION,
            input_file=input_file,
            output_file=str(summary_path),
            params={
                "goal": goal,
                "output_label": output_label,
                "has_web_context": bool(web_context.strip()),
            },
        ),
        isolation_mode="workspace_dir",
        metadata=manifest_metadata,
    )

    def _finalize_workspace(
        *,
        status: str = "",
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        completed: bool | None = None,
        exec_ok: bool | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        report = build_completion_report(
            out_dir,
            workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
            workspace_purpose="autonomous_analysis",
            requirements=requirements,
            status=status,
            warnings=warnings,
            errors=errors,
            manifest_path=str(manifest_path),
            metadata={
                **manifest_metadata,
                "execution_ok": exec_ok,
            },
            completed=completed,
        )
        report_path = write_completion_report(
            out_dir,
            report,
            hook_runtime=hook_runtime,
            hook_context={
                "workspace": str(out_dir),
                "source": "autonomous_analysis",
            },
        )
        update_workspace_manifest(
            out_dir,
            workspace_kind=WORKSPACE_KIND_ANALYSIS_RUN,
            workspace_purpose="autonomous_analysis",
            requirements=requirements,
            completion_report=report,
            isolation_mode="workspace_dir",
            metadata=manifest_metadata,
            append_step=False,
        )
        return report_path, report.to_dict()

    session = None
    try:
        session = NotebookSession(str(notebook_path))
        session.insert_cell(None, "markdown", "# Autonomous Analysis Plan\n\n" + (analysis_plan or goal))
        if web_context:
            session.insert_cell(None, "markdown", "## External Method Context\n\n" + web_context[:12000])

        setup_result = session.insert_execute_code_cell(
            None,
            _safe_setup_code(
                goal=goal,
                context=context,
                web_context=web_context,
                input_file=input_file,
                output_dir=str(out_dir),
            ),
        )
        if not setup_result["ok"]:
            summary_path.write_text(
                "Setup failed.\n\n" + (setup_result.get("error") or "unknown error") + "\n",
                encoding="utf-8",
            )
            completion_report_path, completion = _finalize_workspace(
                status=COMPLETION_STATUS_FAILED,
                errors=[setup_result.get("error") or "autonomous notebook setup failed"],
                exec_ok=False,
            )
            return {
                "ok": False,
                "error": setup_result.get("error") or "autonomous notebook setup failed",
                "output_dir": str(out_dir),
                "notebook_path": str(notebook_path),
                "manifest_path": str(manifest_path),
                "completion_report_path": str(completion_report_path),
                "completion": completion,
            }

        exec_result = session.insert_execute_code_cell(None, python_code)
        preview = exec_result.get("output_preview") or ""
        status = "success" if exec_result["ok"] else "failed"
        summary_path.write_text(
            textwrap.dedent(
                f"""
                # Autonomous Analysis {status.title()}

                Goal:
                {goal}

                Output Preview:
                {preview or "<no stdout preview>"}

                Error:
                {exec_result.get("error") or "<none>"}
                """
            ).strip() + "\n",
            encoding="utf-8",
        )
        completion_report_path, completion = _finalize_workspace(
            status=COMPLETION_STATUS_FAILED if not exec_result["ok"] else "",
            errors=[exec_result.get("error") or ""],
            exec_ok=bool(exec_result["ok"]),
        )
        return {
            "ok": bool(exec_result["ok"]),
            "output_dir": str(out_dir),
            "notebook_path": str(notebook_path),
            "summary_path": str(summary_path),
            "output_preview": preview,
            "error": exec_result.get("error") or "",
            "manifest_path": str(manifest_path),
            "completion_report_path": str(completion_report_path),
            "completion": completion,
        }
    except Exception as exc:
        summary_path.write_text(
            "Execution failed.\n\n" + str(exc) + "\n",
            encoding="utf-8",
        )
        completion_report_path, completion = _finalize_workspace(
            status=COMPLETION_STATUS_FAILED,
            errors=[str(exc)],
            exec_ok=False,
        )
        return {
            "ok": False,
            "error": str(exc),
            "output_dir": str(out_dir),
            "notebook_path": str(notebook_path),
            "summary_path": str(summary_path),
            "manifest_path": str(manifest_path),
            "completion_report_path": str(completion_report_path),
            "completion": completion,
        }
    finally:
        if session is not None:
            try:
                session.shutdown()
            except Exception:
                pass
