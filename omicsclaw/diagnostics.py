"""Doctor, diagnostics, and context observability helpers."""

from __future__ import annotations

import importlib
import importlib.util
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from omicsclaw.core.provider_registry import (
    PROVIDER_PRESETS,
    detect_provider_from_env,
    resolve_provider,
)
from omicsclaw.runtime.context_assembler import (
    assemble_prompt_context,
    extract_analysis_hints,
    extract_user_text,
    should_attach_capability_context,
)
from omicsclaw.runtime.context_layers import (
    ContextAssemblyRequest,
    should_prefetch_knowledge_guidance,
)
from omicsclaw.runtime.transcript_store import (
    build_selective_replay_summary,
    build_transcript_summary,
)


DIAGNOSTIC_STATUS_OK = "ok"
DIAGNOSTIC_STATUS_WARN = "warn"
DIAGNOSTIC_STATUS_FAIL = "fail"
DIAGNOSTIC_STATUS_INFO = "info"

_CORE_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("openai", "openai"),
    ("requests", "requests"),
)
_OPTIONAL_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("dotenv", "python-dotenv"),
    ("prompt_toolkit", "prompt-toolkit"),
    ("aiosqlite", "aiosqlite"),
    ("yaml", "pyyaml"),
    ("textual", "textual"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("langchain_mcp_adapters", "langchain-mcp-adapters"),
)
_R_PACKAGES: tuple[str, ...] = (
    "Seurat",
    "SingleCellExperiment",
    "edgeR",
    "limma",
)
_CONTEXT_WARNING_THRESHOLD = 12_000


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: str
    summary: str
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorReport:
    generated_at: str
    omicsclaw_dir: str
    workspace_dir: str
    checks: tuple[DiagnosticCheck, ...]

    @property
    def failure_count(self) -> int:
        return sum(1 for check in self.checks if check.status == DIAGNOSTIC_STATUS_FAIL)

    @property
    def warning_count(self) -> int:
        return sum(1 for check in self.checks if check.status == DIAGNOSTIC_STATUS_WARN)

    @property
    def overall_status(self) -> str:
        if self.failure_count:
            return DIAGNOSTIC_STATUS_FAIL
        if self.warning_count:
            return DIAGNOSTIC_STATUS_WARN
        return DIAGNOSTIC_STATUS_OK


@dataclass(frozen=True, slots=True)
class ContextLayerObservation:
    name: str
    placement: str
    order: int
    estimated_tokens: int
    cost_chars: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextReport:
    surface: str
    query: str
    workspace_dir: str
    pipeline_workspace: str
    plan_context_present: bool
    message_count: int
    omitted_message_count: int
    compacted_tool_result_count: int
    plan_reference_count: int
    advisory_event_count: int
    total_estimated_tokens: int
    total_chars: int
    warning_threshold_tokens: int
    warnings: tuple[str, ...]
    layers: tuple[ContextLayerObservation, ...]


@dataclass(frozen=True, slots=True)
class UsageReport:
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    api_calls: int
    estimated_cost_usd: float
    input_price_per_1m: float
    output_price_per_1m: float
    session_seconds: float | None = None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _safe_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _status_label(status: str, *, markup: bool) -> str:
    plain = {
        DIAGNOSTIC_STATUS_OK: "OK",
        DIAGNOSTIC_STATUS_WARN: "WARN",
        DIAGNOSTIC_STATUS_FAIL: "FAIL",
        DIAGNOSTIC_STATUS_INFO: "INFO",
    }.get(status, "INFO")
    if not markup:
        return plain
    color = {
        DIAGNOSTIC_STATUS_OK: "green",
        DIAGNOSTIC_STATUS_WARN: "yellow",
        DIAGNOSTIC_STATUS_FAIL: "red",
        DIAGNOSTIC_STATUS_INFO: "cyan",
    }.get(status, "cyan")
    return f"[{color}]{plain}[/{color}]"


def _overall_label(status: str, *, markup: bool) -> str:
    return _status_label(status, markup=markup)


def _format_text(value: Any, *, markup: bool) -> str:
    text = str(value or "")
    if not markup:
        return text
    try:
        from rich.markup import escape
    except Exception:
        return text
    return escape(text)


def _get_session_db_path() -> Path:
    from omicsclaw.interactive._session import get_db_path

    return get_db_path()


def _get_mcp_config_path() -> Path:
    from omicsclaw.interactive._mcp import MCP_CONFIG_PATH

    return MCP_CONFIG_PATH


def _collect_provider_check() -> DiagnosticCheck:
    env_provider = str(os.environ.get("LLM_PROVIDER", "") or "").strip()
    env_model = str(os.environ.get("OMICSCLAW_MODEL", "") or "").strip()
    env_base_url = str(os.environ.get("LLM_BASE_URL", "") or "").strip()
    bot_core = _safe_import("bot.core")
    provider_presets = getattr(bot_core, "PROVIDER_PRESETS", PROVIDER_PRESETS)
    detected_provider = detect_provider_from_env(provider_presets=provider_presets)
    provider_name = env_provider or detected_provider
    resolved_model = env_model
    resolved_url = env_base_url
    api_key_present = False
    details: list[str] = []

    try:
        resolved_url_value, resolved_model_value, resolved_key = resolve_provider(
            provider=provider_name,
            base_url=env_base_url,
            model=env_model,
            api_key=os.environ.get("LLM_API_KEY", ""),
            provider_presets=provider_presets,
        )
        if resolved_url_value:
            resolved_url = str(resolved_url_value)
        if resolved_model_value:
            resolved_model = str(resolved_model_value)
        api_key_present = bool(resolved_key)
        if bot_core is not None:
            provider_name = provider_name or getattr(bot_core, "LLM_PROVIDER_NAME", "") or detected_provider
    except Exception as exc:
        details.append(f"Provider resolution fallback used: {exc}")

    if not resolved_model:
        preset = provider_presets.get(provider_name, ("", "", ""))
        resolved_model = str(preset[1] or "")
        resolved_url = resolved_url or str(preset[0] or "")
        api_env = str(preset[2] or "")
        api_key_present = bool(
            os.environ.get(api_env, "")
            or os.environ.get("LLM_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
        )

    base_url_detail = resolved_url or "(default)"
    if not provider_name and not resolved_model:
        return DiagnosticCheck(
            name="Provider Config",
            status=DIAGNOSTIC_STATUS_WARN,
            summary="No provider or model configured in environment.",
            details=(
                "Run `oc onboard` or set LLM_PROVIDER / OMICSCLAW_MODEL before interactive use.",
            ),
        )

    provider_for_keyless = str(provider_name or "").lower()
    key_optional = provider_for_keyless in {"ollama", "custom"} or base_url_detail.startswith("http://localhost")
    status = DIAGNOSTIC_STATUS_OK if (api_key_present or key_optional) else DIAGNOSTIC_STATUS_WARN
    if not provider_name:
        details.append("Provider will be auto-detected from available API-key env vars.")
    if env_provider:
        details.append(f"LLM_PROVIDER={env_provider}")
    if env_model:
        details.append(f"OMICSCLAW_MODEL={env_model}")
    if env_base_url:
        details.append(f"LLM_BASE_URL={env_base_url}")
    details.append(f"Resolved base URL: {base_url_detail}")
    details.append(f"API key: {'set' if api_key_present else 'missing'}")
    return DiagnosticCheck(
        name="Provider Config",
        status=status,
        summary=(
            f"provider={provider_name or '(auto)'} "
            f"model={resolved_model or '(unset)'} "
            f"api_key={'set' if api_key_present else 'missing'}"
        ),
        details=tuple(details),
    )


def _collect_python_checks() -> tuple[DiagnosticCheck, DiagnosticCheck, DiagnosticCheck]:
    python_check = DiagnosticCheck(
        name="Python",
        status=DIAGNOSTIC_STATUS_OK,
        summary=f"{platform.python_version()} ({sys.executable})",
        details=(platform.platform(),),
    )

    missing_core = [label for module_name, label in _CORE_DEPENDENCIES if not _module_available(module_name)]
    core_check = DiagnosticCheck(
        name="Core Packages",
        status=DIAGNOSTIC_STATUS_OK if not missing_core else DIAGNOSTIC_STATUS_FAIL,
        summary=(
            "All required Python packages are importable."
            if not missing_core
            else "Missing required packages: " + ", ".join(missing_core)
        ),
    )

    missing_optional = [label for module_name, label in _OPTIONAL_DEPENDENCIES if not _module_available(module_name)]
    optional_check = DiagnosticCheck(
        name="Optional Packages",
        status=DIAGNOSTIC_STATUS_OK if not missing_optional else DIAGNOSTIC_STATUS_WARN,
        summary=(
            "Optional feature packages look available."
            if not missing_optional
            else "Missing optional packages: " + ", ".join(missing_optional)
        ),
    )
    return python_check, core_check, optional_check


def _collect_r_check() -> DiagnosticCheck:
    rscript = shutil.which("Rscript")
    if not rscript:
        return DiagnosticCheck(
            name="R Runtime",
            status=DIAGNOSTIC_STATUS_WARN,
            summary="Rscript not found on PATH.",
            details=("R-backed skills will be unavailable until R is installed.",),
        )

    details: list[str] = [f"Rscript={rscript}"]
    version_text = ""
    try:
        version_proc = subprocess.run(
            [rscript, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        version_text = " ".join(
            part.strip()
            for part in (
                version_proc.stdout.strip(),
                version_proc.stderr.strip(),
            )
            if part.strip()
        )
    except Exception as exc:
        details.append(f"Version probe failed: {exc}")

    try:
        probe = subprocess.run(
            [
                rscript,
                "--vanilla",
                "-e",
                (
                    "pkgs <- c("
                    + ", ".join(f"'{pkg}'" for pkg in _R_PACKAGES)
                    + "); vals <- sapply(pkgs, requireNamespace, quietly=TRUE); "
                    "cat(paste(sprintf('%s=%s', names(vals), ifelse(vals, '1', '0')), collapse=';'))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return DiagnosticCheck(
            name="R Runtime",
            status=DIAGNOSTIC_STATUS_WARN,
            summary=f"Rscript is present but package probe failed: {exc}",
            details=tuple(details),
        )

    raw_output = str(probe.stdout or "").strip()
    package_statuses: dict[str, bool] = {}
    for chunk in raw_output.split(";"):
        if "=" not in chunk:
            continue
        package_name, value = chunk.split("=", 1)
        package_statuses[package_name.strip()] = value.strip() == "1"

    missing = [package_name for package_name in _R_PACKAGES if not package_statuses.get(package_name, False)]
    if version_text:
        details.append(version_text)
    if missing:
        details.append("Missing R packages: " + ", ".join(missing))
    status = DIAGNOSTIC_STATUS_OK if not missing else DIAGNOSTIC_STATUS_WARN
    return DiagnosticCheck(
        name="R Runtime",
        status=status,
        summary=(
            "Rscript available; common analysis packages detected."
            if not missing
            else f"Rscript available; missing R packages: {', '.join(missing)}"
        ),
        details=tuple(details),
    )


def _collect_session_db_check() -> DiagnosticCheck:
    db_path = _get_session_db_path()
    parent = db_path.parent
    details = [f"path={db_path}"]
    has_aiosqlite = _module_available("aiosqlite")
    if not parent.exists():
        return DiagnosticCheck(
            name="Session DB",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Session config directory is missing: {parent}",
            details=tuple(details),
        )

    if not os.access(parent, os.W_OK):
        return DiagnosticCheck(
            name="Session DB",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Session config directory is not writable: {parent}",
            details=tuple(details),
        )

    if not db_path.exists():
        status = DIAGNOSTIC_STATUS_OK if has_aiosqlite else DIAGNOSTIC_STATUS_WARN
        details.append("Database has not been created yet; it will be initialized on first interactive save.")
        if not has_aiosqlite:
            details.append("Install aiosqlite to enable session persistence.")
        return DiagnosticCheck(
            name="Session DB",
            status=status,
            summary="Session database path is writable.",
            details=tuple(details),
        )

    if not db_path.is_file():
        return DiagnosticCheck(
            name="Session DB",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Expected a file but found a non-file path: {db_path}",
            details=tuple(details),
        )

    if not os.access(db_path, os.R_OK | os.W_OK):
        return DiagnosticCheck(
            name="Session DB",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Session database is not readable/writable: {db_path}",
            details=tuple(details),
        )

    table_count = 0
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            table_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sessions'"
                ).fetchone()[0]
            )
        finally:
            connection.close()
    except Exception as exc:
        return DiagnosticCheck(
            name="Session DB",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Session database exists but could not be opened: {exc}",
            details=tuple(details),
        )

    details.append(f"size={db_path.stat().st_size} bytes")
    if table_count:
        details.append("sessions table present")
    else:
        details.append("sessions table missing; schema will be recreated on next interactive start")
    if not has_aiosqlite:
        details.append("Install aiosqlite to use session persistence from interactive mode.")
    status = DIAGNOSTIC_STATUS_OK if (has_aiosqlite and table_count) else DIAGNOSTIC_STATUS_WARN
    return DiagnosticCheck(
        name="Session DB",
        status=status,
        summary="Session database is accessible.",
        details=tuple(details),
    )


def _collect_knowledge_check() -> DiagnosticCheck:
    try:
        from omicsclaw.knowledge.retriever import KnowledgeAdvisor
    except Exception as exc:
        return DiagnosticCheck(
            name="Knowledge Index",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Knowledge subsystem import failed: {exc}",
        )

    advisor = KnowledgeAdvisor()
    root = advisor.kb_root
    store = advisor._store
    details = [f"root={root}", f"db={store.db_path}"]
    if not root.is_dir():
        return DiagnosticCheck(
            name="Knowledge Index",
            status=DIAGNOSTIC_STATUS_WARN,
            summary=f"Knowledge root is missing: {root}",
            details=tuple(details),
        )

    if not store.is_built():
        return DiagnosticCheck(
            name="Knowledge Index",
            status=DIAGNOSTIC_STATUS_WARN,
            summary="Knowledge index has not been built yet.",
            details=tuple(details),
        )

    up_to_date = False
    try:
        up_to_date = bool(store.is_up_to_date(root))
    except Exception as exc:
        details.append(f"Freshness probe failed: {exc}")

    try:
        stats = advisor.stats()
    except Exception as exc:
        return DiagnosticCheck(
            name="Knowledge Index",
            status=DIAGNOSTIC_STATUS_WARN,
            summary=f"Knowledge index exists but stats probe failed: {exc}",
            details=tuple(details),
        )

    if "error" in stats:
        return DiagnosticCheck(
            name="Knowledge Index",
            status=DIAGNOSTIC_STATUS_WARN,
            summary=str(stats["error"]),
            details=tuple(details),
        )

    details.append(f"documents={int(stats.get('total_documents', 0) or 0)}")
    details.append(f"chunks={int(stats.get('total_chunks', 0) or 0)}")
    status = DIAGNOSTIC_STATUS_OK if up_to_date else DIAGNOSTIC_STATUS_WARN
    freshness = "up-to-date" if up_to_date else "stale"
    return DiagnosticCheck(
        name="Knowledge Index",
        status=status,
        summary=(
            f"{int(stats.get('total_documents', 0) or 0)} docs, "
            f"{int(stats.get('total_chunks', 0) or 0)} chunks ({freshness})"
        ),
        details=tuple(details),
    )


def _collect_extensions_check(omicsclaw_dir: str) -> DiagnosticCheck:
    if not omicsclaw_dir:
        return DiagnosticCheck(
            name="Extensions",
            status=DIAGNOSTIC_STATUS_INFO,
            summary="OmicsClaw root not provided; extension inventory skipped.",
        )

    try:
        from omicsclaw.extensions import list_installed_extensions
        from omicsclaw.extensions.validators import validate_extension_directory
    except Exception as exc:
        return DiagnosticCheck(
            name="Extensions",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"Extension runtime import failed: {exc}",
        )

    entries = list_installed_extensions(omicsclaw_dir)
    enabled_count = sum(1 for entry in entries if entry.state.enabled)
    invalid_details: list[str] = []
    for entry in entries:
        validation = validate_extension_directory(
            entry.path,
            source_kind=entry.record.source_kind if entry.record is not None else "local",
        )
        if validation.valid:
            continue
        invalid_details.append(
            f"{entry.path.name}: " + "; ".join(validation.errors)
        )

    status = DIAGNOSTIC_STATUS_OK if not invalid_details else DIAGNOSTIC_STATUS_WARN
    summary = (
        "No installed extensions detected."
        if not entries
        else f"{len(entries)} installed, {enabled_count} enabled, {len(invalid_details)} invalid"
    )
    details = tuple(invalid_details[:8])
    return DiagnosticCheck(
        name="Extensions",
        status=status,
        summary=summary,
        details=details,
    )


def _collect_mcp_check() -> DiagnosticCheck:
    config_path = _get_mcp_config_path()
    details = [f"path={config_path}"]
    yaml_module = _safe_import("yaml")
    if yaml_module is None:
        return DiagnosticCheck(
            name="MCP Config",
            status=DIAGNOSTIC_STATUS_WARN,
            summary="pyyaml is not installed; MCP config cannot be parsed.",
            details=tuple(details),
        )

    if not config_path.exists():
        return DiagnosticCheck(
            name="MCP Config",
            status=DIAGNOSTIC_STATUS_OK,
            summary="No MCP config file found yet.",
            details=tuple(details),
        )

    try:
        data = yaml_module.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return DiagnosticCheck(
            name="MCP Config",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary=f"MCP config parse failed: {exc}",
            details=tuple(details),
        )

    if not isinstance(data, dict):
        return DiagnosticCheck(
            name="MCP Config",
            status=DIAGNOSTIC_STATUS_FAIL,
            summary="MCP config should be a mapping of server names to settings.",
            details=tuple(details),
        )

    server_names = [str(name) for name in data.keys()]
    details.extend(server_names[:8])
    return DiagnosticCheck(
        name="MCP Config",
        status=DIAGNOSTIC_STATUS_OK,
        summary=f"{len(server_names)} configured server(s)",
        details=tuple(details),
    )


def _collect_directory_check(name: str, path: str | Path | None) -> DiagnosticCheck:
    target = Path(path or "").expanduser()
    if not str(target):
        return DiagnosticCheck(
            name=name,
            status=DIAGNOSTIC_STATUS_WARN,
            summary=f"{name} path is not configured.",
        )

    parent = target.parent
    details = [f"path={target}"]
    if target.exists():
        if not target.is_dir():
            return DiagnosticCheck(
                name=name,
                status=DIAGNOSTIC_STATUS_FAIL,
                summary=f"{name} exists but is not a directory.",
                details=tuple(details),
            )
        if not os.access(target, os.R_OK | os.W_OK | os.X_OK):
            return DiagnosticCheck(
                name=name,
                status=DIAGNOSTIC_STATUS_FAIL,
                summary=f"{name} is not fully accessible.",
                details=tuple(details),
            )
        return DiagnosticCheck(
            name=name,
            status=DIAGNOSTIC_STATUS_OK,
            summary=f"{name} directory is readable and writable.",
            details=tuple(details),
        )

    if parent.exists() and os.access(parent, os.W_OK):
        details.append(f"parent={parent}")
        return DiagnosticCheck(
            name=name,
            status=DIAGNOSTIC_STATUS_WARN,
            summary=f"{name} directory does not exist yet, but parent is writable.",
            details=tuple(details),
        )

    return DiagnosticCheck(
        name=name,
        status=DIAGNOSTIC_STATUS_FAIL,
        summary=f"{name} directory is missing and parent is not writable.",
        details=tuple(details),
    )


def build_doctor_report(
    *,
    omicsclaw_dir: str,
    workspace_dir: str,
    pipeline_workspace: str = "",
    output_dir: str = "",
) -> DoctorReport:
    resolved_workspace = str(workspace_dir or "").strip()
    resolved_pipeline_workspace = str(pipeline_workspace or "").strip()
    resolved_output_dir = str(output_dir or "").strip()
    checks: list[DiagnosticCheck] = []
    checks.extend(_collect_python_checks())
    checks.append(_collect_r_check())
    checks.append(_collect_provider_check())
    checks.append(_collect_session_db_check())
    checks.append(_collect_knowledge_check())
    checks.append(_collect_extensions_check(str(omicsclaw_dir or "").strip()))
    checks.append(_collect_mcp_check())
    checks.append(_collect_directory_check("Workspace", resolved_workspace))
    if resolved_pipeline_workspace and resolved_pipeline_workspace != resolved_workspace:
        checks.append(_collect_directory_check("Pipeline Workspace", resolved_pipeline_workspace))
    if resolved_output_dir:
        checks.append(_collect_directory_check("Default Output", resolved_output_dir))
    return DoctorReport(
        generated_at=_utcnow_iso(),
        omicsclaw_dir=str(omicsclaw_dir or "").strip(),
        workspace_dir=resolved_workspace,
        checks=tuple(checks),
    )


def render_doctor_report(
    report: DoctorReport,
    *,
    markup: bool = False,
) -> str:
    lines = [
        "Doctor Report",
        f"Generated: {_format_text(report.generated_at, markup=markup)}",
        f"Project Root: {_format_text(report.omicsclaw_dir or '(unset)', markup=markup)}",
        f"Workspace: {_format_text(report.workspace_dir or '(unset)', markup=markup)}",
        (
            f"Overall: {_overall_label(report.overall_status, markup=markup)} "
            f"(fail={report.failure_count}, warn={report.warning_count})"
        ),
        "",
    ]
    for check in report.checks:
        label = _status_label(check.status, markup=markup)
        prefix = label if markup else f"[{label}]"
        lines.append(
            f"{prefix} {_format_text(check.name, markup=markup)}: "
            f"{_format_text(check.summary, markup=markup)}"
        )
        for detail in check.details:
            lines.append(f"  {_format_text(detail, markup=markup)}")
    return "\n".join(lines).strip()


def _latest_user_text(messages: Iterable[dict[str, Any]]) -> str:
    for message in reversed(list(messages or ())):
        if not isinstance(message, dict):
            continue
        if str(message.get("role", "") or "") != "user":
            continue
        text = extract_user_text(message.get("content", ""))
        if text.strip():
            return text.strip()
    return ""


def _context_warning_threshold() -> int:
    raw = str(os.environ.get("OMICSCLAW_CONTEXT_WARNING_TOKENS", "") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = _CONTEXT_WARNING_THRESHOLD
    return max(1, value)


def _resolve_usage_snapshot() -> dict[str, Any]:
    bot_core = _safe_import("bot.core")
    if bot_core is None or not hasattr(bot_core, "get_usage_snapshot"):
        return {}
    try:
        snapshot = bot_core.get_usage_snapshot()
    except Exception:
        return {}
    return dict(snapshot or {})


def build_usage_report(
    *,
    session_usage: Mapping[str, Any] | None = None,
    session_seconds: float | None = None,
) -> UsageReport:
    snapshot = _resolve_usage_snapshot()
    prompt_tokens = int(
        (session_usage or {}).get("prompt_tokens", snapshot.get("prompt_tokens", 0)) or 0
    )
    completion_tokens = int(
        (session_usage or {}).get("completion_tokens", snapshot.get("completion_tokens", 0)) or 0
    )
    total_tokens = int(
        (session_usage or {}).get("total_tokens", prompt_tokens + completion_tokens)
        or (prompt_tokens + completion_tokens)
    )
    api_calls = int(
        (session_usage or {}).get("api_calls", snapshot.get("api_calls", 0)) or 0
    )
    input_price_per_1m = float(snapshot.get("input_price_per_1m", 0.0) or 0.0)
    output_price_per_1m = float(snapshot.get("output_price_per_1m", 0.0) or 0.0)
    estimated_cost_usd = (
        prompt_tokens / 1_000_000 * input_price_per_1m
        + completion_tokens / 1_000_000 * output_price_per_1m
    )
    return UsageReport(
        model=str(snapshot.get("model", "") or ""),
        provider=str(snapshot.get("provider", "") or ""),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        api_calls=api_calls,
        estimated_cost_usd=estimated_cost_usd,
        input_price_per_1m=input_price_per_1m,
        output_price_per_1m=output_price_per_1m,
        session_seconds=session_seconds,
    )


def render_usage_report(
    report: UsageReport,
) -> str:
    lines = [
        "Usage Report",
        f"Model: {report.model or '(unknown)'} ({report.provider or 'unknown'})",
        f"Input tokens: {report.prompt_tokens:,}",
        f"Output tokens: {report.completion_tokens:,}",
        f"Total tokens: {report.total_tokens:,}",
        f"API calls: {report.api_calls}",
        f"Estimated cost: ${report.estimated_cost_usd:.6f} USD",
        (
            f"Price: ${report.input_price_per_1m:.3f} / "
            f"${report.output_price_per_1m:.3f} per 1M tokens (in/out)"
        ),
    ]
    if report.session_seconds is not None:
        elapsed = max(0, int(report.session_seconds))
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        lines.append(f"Session time: {hours}h {minutes}m {seconds}s")
    return "\n".join(lines)


def _load_nonmutating_knowledge_guidance(
    *,
    query: str = "",
    skill: str = "",
    domain: str = "",
    limit: int = 2,
    max_snippet: int = 500,
) -> str:
    if not should_prefetch_knowledge_guidance(
        query=query,
        skill=skill,
        domain=domain,
    ):
        return ""

    try:
        from omicsclaw.knowledge.retriever import KnowledgeAdvisor
    except Exception:
        return ""

    advisor = KnowledgeAdvisor()
    store = advisor._store
    root = advisor.kb_root
    if not root.is_dir() or not store.is_built() or not store.is_up_to_date(root):
        return ""

    try:
        result = advisor.search_formatted(
            query=" ".join(part for part in (skill, query) if str(part).strip()),
            domain=domain or None,
            limit=limit,
            max_snippet=max_snippet,
            auto_build=False,
        )
    except Exception:
        return ""

    text = str(result or "").strip()
    if not text or text.startswith("No knowledge base results found"):
        return ""
    if "Knowledge base not built yet" in text:
        return ""
    return text


def _resolve_prompt_pack_context(
    *,
    omicsclaw_dir: str,
    surface: str,
    skill: str,
    query: str,
    domain: str,
) -> str:
    if not omicsclaw_dir:
        return ""
    try:
        from omicsclaw.extensions import build_prompt_pack_context
    except Exception:
        return ""
    return str(
        build_prompt_pack_context(
            omicsclaw_dir,
            surface=surface,
            skill=skill,
            query=query,
            domain=domain,
        )
        or ""
    ).strip()


def _resolve_scoped_memory_context(
    *,
    query: str,
    domain: str,
    workspace_dir: str,
    pipeline_workspace: str,
    scoped_memory_scope: str,
) -> str:
    if not workspace_dir and not pipeline_workspace:
        return ""
    try:
        from omicsclaw.memory.scoped_memory_select import load_scoped_memory_context
    except Exception:
        return ""

    recall = load_scoped_memory_context(
        query=query,
        domain=domain,
        workspace=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        preferred_scope=scoped_memory_scope,
    )
    if recall is None:
        return ""
    if hasattr(recall, "to_context_text"):
        return str(recall.to_context_text() or "").strip()
    return str(recall or "").strip()


def _resolve_context_budget_defaults() -> tuple[int, int | None]:
    bot_core = _safe_import("bot.core")
    if bot_core is None:
        return 50, None
    max_history = int(getattr(bot_core, "MAX_HISTORY", 50) or 50)
    max_history_chars = getattr(bot_core, "MAX_HISTORY_CHARS", 0)
    max_history_chars_value = int(max_history_chars or 0)
    return max_history, (max_history_chars_value or None)


def build_context_report(
    *,
    surface: str,
    messages: list[dict[str, Any]],
    session_metadata: Mapping[str, Any] | None,
    workspace_dir: str,
    pipeline_workspace: str = "",
    query: str = "",
    plan_context: str = "",
    output_style: str = "",
    scoped_memory_scope: str = "",
    omicsclaw_dir: str = "",
    mcp_servers: tuple[str, ...] = (),
) -> ContextReport:
    normalized_surface = str(surface or "interactive").strip() or "interactive"
    normalized_query = str(query or "").strip() or _latest_user_text(messages)
    normalized_workspace = str(workspace_dir or "").strip()
    normalized_pipeline_workspace = str(pipeline_workspace or "").strip()
    metadata = dict(session_metadata or {})
    transcript_summary = build_transcript_summary(
        list(messages or []),
        metadata=metadata,
        workspace=normalized_workspace,
    )
    max_history, max_history_chars = _resolve_context_budget_defaults()
    replay_summary = build_selective_replay_summary(
        list(messages or []),
        metadata=metadata,
        workspace=normalized_workspace,
        max_messages=max_history,
        max_chars=max_history_chars,
    )

    skill_hint, domain_hint = extract_analysis_hints(normalized_query)
    capability_context = ""
    warnings: list[str] = []
    if should_attach_capability_context(normalized_query):
        try:
            from omicsclaw.core.capability_resolver import resolve_capability

            decision = resolve_capability(normalized_query, domain_hint=domain_hint)
            capability_context = str(decision.to_prompt_block() or "").strip()
            if not skill_hint and getattr(decision, "chosen_skill", ""):
                skill_hint = str(decision.chosen_skill)
            if not domain_hint and getattr(decision, "domain", ""):
                domain_hint = str(decision.domain)
        except Exception as exc:
            warnings.append(f"Capability assessment unavailable: {exc}")

    try:
        prompt_pack_context = _resolve_prompt_pack_context(
            omicsclaw_dir=omicsclaw_dir,
            surface=normalized_surface,
            skill=skill_hint,
            query=normalized_query[:200],
            domain=domain_hint,
        )
    except Exception as exc:
        prompt_pack_context = ""
        warnings.append(f"Prompt-pack context unavailable: {exc}")

    try:
        scoped_memory_context = _resolve_scoped_memory_context(
            query=normalized_query[:200],
            domain=domain_hint,
            workspace_dir=normalized_workspace,
            pipeline_workspace=normalized_pipeline_workspace,
            scoped_memory_scope=scoped_memory_scope,
        )
    except Exception as exc:
        scoped_memory_context = ""
        warnings.append(f"Scoped memory context unavailable: {exc}")

    prompt_context = assemble_prompt_context(
        request=ContextAssemblyRequest(
            surface=normalized_surface,
            omicsclaw_dir=omicsclaw_dir,
            output_style=output_style,
            memory_context="",
            scoped_memory_context=scoped_memory_context,
            skill=skill_hint,
            query=normalized_query[:200],
            domain=domain_hint,
            capability_context=capability_context,
            plan_context=str(plan_context or "").strip(),
            prompt_pack_context=prompt_pack_context,
            transcript_context=replay_summary.to_prompt_block(),
            workspace=normalized_workspace,
            pipeline_workspace=normalized_pipeline_workspace,
            mcp_servers=tuple(mcp_servers or ()),
            knowledge_loader=_load_nonmutating_knowledge_guidance,
        )
    )

    threshold = _context_warning_threshold()
    if prompt_context.total_estimated_tokens >= threshold:
        warnings.append(
            f"Estimated prompt size {prompt_context.total_estimated_tokens:,} tokens exceeds warning threshold {threshold:,}."
        )

    layers = tuple(
        ContextLayerObservation(
            name=layer.name,
            placement=layer.placement,
            order=layer.order,
            estimated_tokens=layer.estimated_tokens,
            cost_chars=layer.cost_chars,
            metadata=dict(layer.metadata or {}),
        )
        for layer in prompt_context.layers
    )
    return ContextReport(
        surface=normalized_surface,
        query=normalized_query,
        workspace_dir=normalized_workspace,
        pipeline_workspace=normalized_pipeline_workspace,
        plan_context_present=bool(str(plan_context or "").strip()),
        message_count=len(list(messages or [])),
        omitted_message_count=replay_summary.omitted_message_count,
        compacted_tool_result_count=len(transcript_summary.compacted_tool_results),
        plan_reference_count=len(transcript_summary.plan_references),
        advisory_event_count=len(transcript_summary.advisory_events),
        total_estimated_tokens=prompt_context.total_estimated_tokens,
        total_chars=prompt_context.total_chars,
        warning_threshold_tokens=threshold,
        warnings=tuple(warnings),
        layers=layers,
    )


def render_context_report(
    report: ContextReport,
    *,
    markup: bool = False,
) -> str:
    del markup
    lines = [
        "Context Report",
        f"Surface: {report.surface}",
        f"Query basis: {report.query or '(latest user message unavailable)'}",
        f"Workspace: {report.workspace_dir or '(unset)'}",
    ]
    if report.pipeline_workspace:
        lines.append(f"Pipeline workspace: {report.pipeline_workspace}")
    lines.append(f"Plan context: {'present' if report.plan_context_present else 'absent'}")
    lines.extend(
        (
            f"Messages tracked: {report.message_count}",
            (
                "Transcript refs: "
                f"compacted={report.compacted_tool_result_count}, "
                f"plan={report.plan_reference_count}, "
                f"advisory={report.advisory_event_count}, "
                f"omitted={report.omitted_message_count}"
            ),
            (
                "Prompt estimate: "
                f"{report.total_estimated_tokens:,} tokens / {report.total_chars:,} chars"
            ),
            f"Warning threshold: {report.warning_threshold_tokens:,} tokens",
        )
    )
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    lines.append("Layers:")
    for layer in report.layers:
        line = (
            f"- {layer.name} ({layer.placement}) "
            f"{layer.estimated_tokens:,} tokens / {layer.cost_chars:,} chars"
        )
        active_packs = tuple(layer.metadata.get("active_prompt_packs", ()) or ())
        if active_packs:
            line += " | active=" + ", ".join(str(name) for name in active_packs)
        omitted_packs = tuple(layer.metadata.get("omitted_prompt_packs", ()) or ())
        if omitted_packs:
            line += " | omitted=" + ", ".join(str(name) for name in omitted_packs)
        lines.append(line)
    return "\n".join(lines)


__all__ = [
    "ContextLayerObservation",
    "ContextReport",
    "DIAGNOSTIC_STATUS_FAIL",
    "DIAGNOSTIC_STATUS_INFO",
    "DIAGNOSTIC_STATUS_OK",
    "DIAGNOSTIC_STATUS_WARN",
    "DiagnosticCheck",
    "DoctorReport",
    "UsageReport",
    "build_context_report",
    "build_doctor_report",
    "build_usage_report",
    "render_context_report",
    "render_doctor_report",
    "render_usage_report",
]
