"""Shared session command views for interactive surfaces."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from rich.markup import escape

from omicsclaw.extensions import list_installed_extensions
from omicsclaw.memory.scoped_memory import normalize_scoped_memory_scope
from omicsclaw.runtime.output_styles import normalize_output_style_name
from omicsclaw.runtime.transcript_store import build_transcript_summary
from omicsclaw.runtime.verification import (
    WORKSPACE_KIND_ANALYSIS_RUN,
    WORKSPACE_KIND_CONVERSATION,
)

from ._plan_mode_support import (
    build_interactive_plan_summary_lines,
    load_interactive_plan_from_metadata,
    normalize_interactive_plan_metadata,
)
from ._pipeline_support import (
    build_pipeline_display_from_snapshot,
    load_pipeline_workspace_snapshot,
    resolve_pipeline_workspace,
)
from ._session import (
    delete_session,
    export_conversation_to_markdown,
    format_relative_time,
    list_sessions,
    load_session,
)

_SESSION_METADATA_UNSET = object()
_SESSION_WORKFLOW_INTERACTIVE_PLAN = "interactive-plan"
_SESSION_WORKFLOW_RESEARCH_PIPELINE = "research-pipeline"
_SESSION_SEARCH_HINT = (
    "/resume to continue a session  "
    "/sessions tag:<tag> title:<text> workspace:<path> domain:<name> to search  "
    "/delete <id> to remove  /new to start fresh"
)
_DATASET_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<path>(?:~?/|\.{1,2}/)?[^\s'\"`()\[\]{}<>]+?"
    r"\.(?:h5ad|h5|loom|mtx|csv|tsv|vcf(?:\.gz)?|bam|mzml|mzxml|fastq(?:\.gz)?|fq(?:\.gz)?|pdf))"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_SLUG_PART_RE = re.compile(r"[^a-z0-9]+")
_DOMAIN_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("spatial", ("spatial", "visium", "merfish", "stereo-seq", "slide-seq")),
    ("singlecell", ("single-cell", "single cell", "scrna", "scatac", "seurat", "scanpy")),
    ("proteomics", ("proteomics", "peptide", "maxquant", ".mzml", ".mzxml")),
    ("metabolomics", ("metabolomics", "metabolite", "xcms")),
    ("genomics", ("genomics", "variant", ".vcf", "gwas", "plink", "crispr")),
    ("bulkrna", ("bulk rna", "bulk-rna", "deseq2", "edger", "limma")),
)


@dataclass(slots=True)
class SessionSearchQuery:
    free_text: str = ""
    tag: str = ""
    title: str = ""
    domain: str = ""
    workspace: str = ""


@dataclass(slots=True)
class SessionListEntry:
    session_id: str
    preview: str = ""
    title: str = ""
    tag: str = ""
    active_style: str = ""
    active_workflow: str = ""
    workspace_label: str = ""
    workspace_kind: str = ""
    last_active_task_id: str = ""
    domain: str = ""
    state_summary: str = ""
    enabled_extension_count: int = 0
    dataset_ref_count: int = 0
    message_count: int = 0
    compacted_tool_result_count: int = 0
    plan_reference_count: int = 0
    advisory_event_count: int = 0
    model: str = ""
    updated_at: str = ""
    updated_label: str = ""


@dataclass(slots=True)
class SessionListView:
    entries: list[SessionListEntry] = field(default_factory=list)
    empty_text: str = "No saved sessions."
    hint_text: str = _SESSION_SEARCH_HINT
    query: str = ""


@dataclass(slots=True)
class SessionCommandView:
    output_text: str
    success: bool = True
    render_as_markup: bool = False
    session_id: str = ""
    workspace_dir: str = ""
    session_metadata: dict[str, Any] = field(default_factory=dict)
    replace_session_metadata: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    replace_messages: bool = False
    clear_messages: bool = False
    clear_pipeline_workspace: bool = False
    reset_session_runtime: bool = False
    export_path: str = ""


def _normalize_text_field(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, (str, Path)):
        raw_values = [str(value)]
    elif isinstance(value, Mapping):
        return []
    elif isinstance(value, Iterable):
        raw_values = [str(item) for item in value]
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        text = _normalize_text_field(item)
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _slugify(value: str) -> str:
    lowered = _normalize_text_field(value).lower()
    if not lowered:
        return ""
    return _SLUG_PART_RE.sub("-", lowered).strip("-")


def _extract_dataset_refs_from_messages(
    messages: Iterable[dict[str, Any]] | None,
    *,
    limit: int = 8,
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for message in messages or ():
        if not isinstance(message, dict):
            continue
        content = _flatten_message_content(message.get("content", ""))
        if not content:
            continue
        for match in _DATASET_REF_RE.finditer(content):
            candidate = _normalize_text_field(match.group("path"))
            if not candidate or candidate in seen:
                continue
            refs.append(candidate)
            seen.add(candidate)
            if len(refs) >= limit:
                return refs
    return refs


def _infer_domain_from_text(text: str) -> str:
    lowered = _normalize_text_field(text).lower()
    if not lowered:
        return ""
    for domain, markers in _DOMAIN_MARKERS:
        if any(marker in lowered for marker in markers):
            return domain
    return ""


def _load_enabled_extension_refs(omicsclaw_dir: str | Path | None) -> list[str]:
    root = _normalize_text_field(omicsclaw_dir)
    if not root:
        return []
    try:
        names = []
        for item in list_installed_extensions(root):
            if not item.state.enabled:
                continue
            if item.record is not None and _normalize_text_field(item.record.extension_name):
                names.append(_normalize_text_field(item.record.extension_name))
            else:
                names.append(item.path.name)
        return _normalize_text_list(names)
    except Exception:
        return []


def resolve_session_title(
    metadata: Mapping[str, Any] | None,
    *,
    preview: str = "",
) -> str:
    title = _normalize_text_field(dict(metadata or {}).get("title"))
    if title:
        return title
    return _normalize_text_field(preview)


def resolve_session_tag(
    metadata: Mapping[str, Any] | None,
) -> str:
    return _normalize_text_field(dict(metadata or {}).get("tag"))


def _session_workspace_label(
    *,
    workspace_dir: str = "",
    pipeline_workspace: str = "",
) -> str:
    target = _normalize_text_field(pipeline_workspace) or _normalize_text_field(workspace_dir)
    if not target:
        return ""
    try:
        return Path(target).expanduser().resolve().name or target
    except Exception:
        return Path(target).name or target


def normalize_session_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_interactive_plan_metadata(metadata)
    title = _normalize_text_field(normalized.get("title"))
    if title:
        normalized["title"] = title
    else:
        normalized.pop("title", None)
    tag = _normalize_text_field(normalized.get("tag"))
    if tag:
        normalized["tag"] = tag
    else:
        normalized.pop("tag", None)
    active_style = normalize_output_style_name(normalized.get("active_style"))
    if active_style:
        normalized["active_style"] = active_style
    else:
        normalized.pop("active_style", None)
    pipeline_workspace = _normalize_text_field(
        normalized.get("pipeline_workspace")
        or normalized.get("active_pipeline_workspace")
    )
    if pipeline_workspace:
        normalized["pipeline_workspace"] = pipeline_workspace
        normalized["active_pipeline_workspace"] = pipeline_workspace
    else:
        normalized.pop("pipeline_workspace", None)
        normalized.pop("active_pipeline_workspace", None)
    active_workflow = _normalize_text_field(normalized.get("active_workflow"))
    if active_workflow:
        normalized["active_workflow"] = active_workflow
    else:
        normalized.pop("active_workflow", None)
    plan_slug = _slugify(normalized.get("plan_slug"))
    if plan_slug:
        normalized["plan_slug"] = plan_slug
    else:
        normalized.pop("plan_slug", None)
    last_active_task_id = _normalize_text_field(normalized.get("last_active_task_id"))
    if last_active_task_id:
        normalized["last_active_task_id"] = last_active_task_id
    else:
        normalized.pop("last_active_task_id", None)
    workspace_kind = _normalize_text_field(normalized.get("workspace_kind"))
    if workspace_kind:
        normalized["workspace_kind"] = workspace_kind
    else:
        normalized.pop("workspace_kind", None)
    domain = _normalize_text_field(normalized.get("domain")).lower()
    if domain:
        normalized["domain"] = domain
    else:
        normalized.pop("domain", None)
    dataset_refs = _normalize_text_list(normalized.get("dataset_refs"))
    if dataset_refs:
        normalized["dataset_refs"] = dataset_refs
    else:
        normalized.pop("dataset_refs", None)
    enabled_extension_refs = _normalize_text_list(
        normalized.get("enabled_extension_refs")
    )
    if enabled_extension_refs:
        normalized["enabled_extension_refs"] = enabled_extension_refs
    else:
        normalized.pop("enabled_extension_refs", None)
    return normalized


def build_session_metadata(
    metadata: dict[str, Any] | None,
    *,
    pipeline_workspace: str | None | object = _SESSION_METADATA_UNSET,
    active_style: str | None | object = _SESSION_METADATA_UNSET,
    title: str | None | object = _SESSION_METADATA_UNSET,
    tag: str | None | object = _SESSION_METADATA_UNSET,
    active_workflow: str | None | object = _SESSION_METADATA_UNSET,
    plan_slug: str | None | object = _SESSION_METADATA_UNSET,
    dataset_refs: list[str] | tuple[str, ...] | None | object = _SESSION_METADATA_UNSET,
    enabled_extension_refs: list[str] | tuple[str, ...] | None | object = _SESSION_METADATA_UNSET,
    last_active_task_id: str | None | object = _SESSION_METADATA_UNSET,
    workspace_kind: str | None | object = _SESSION_METADATA_UNSET,
    domain: str | None | object = _SESSION_METADATA_UNSET,
) -> dict[str, Any]:
    normalized = normalize_session_metadata(metadata)
    if pipeline_workspace is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(pipeline_workspace)
        if value:
            normalized["pipeline_workspace"] = value
            normalized["active_pipeline_workspace"] = value
        else:
            normalized.pop("pipeline_workspace", None)
            normalized.pop("active_pipeline_workspace", None)
    if active_style is not _SESSION_METADATA_UNSET:
        style_name = normalize_output_style_name(active_style)
        if style_name:
            normalized["active_style"] = style_name
        else:
            normalized.pop("active_style", None)
    if title is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(title)
        if value:
            normalized["title"] = value
        else:
            normalized.pop("title", None)
    if tag is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(tag)
        if value:
            normalized["tag"] = value
        else:
            normalized.pop("tag", None)
    if active_workflow is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(active_workflow)
        if value:
            normalized["active_workflow"] = value
        else:
            normalized.pop("active_workflow", None)
    if plan_slug is not _SESSION_METADATA_UNSET:
        value = _slugify(plan_slug)
        if value:
            normalized["plan_slug"] = value
        else:
            normalized.pop("plan_slug", None)
    if dataset_refs is not _SESSION_METADATA_UNSET:
        values = _normalize_text_list(dataset_refs)
        if values:
            normalized["dataset_refs"] = values
        else:
            normalized.pop("dataset_refs", None)
    if enabled_extension_refs is not _SESSION_METADATA_UNSET:
        values = _normalize_text_list(enabled_extension_refs)
        if values:
            normalized["enabled_extension_refs"] = values
        else:
            normalized.pop("enabled_extension_refs", None)
    if last_active_task_id is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(last_active_task_id)
        if value:
            normalized["last_active_task_id"] = value
        else:
            normalized.pop("last_active_task_id", None)
    if workspace_kind is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(workspace_kind)
        if value:
            normalized["workspace_kind"] = value
        else:
            normalized.pop("workspace_kind", None)
    if domain is not _SESSION_METADATA_UNSET:
        value = _normalize_text_field(domain).lower()
        if value:
            normalized["domain"] = value
        else:
            normalized.pop("domain", None)
    return normalized


def resolve_active_pipeline_workspace(
    pipeline_workspace: str | None,
    metadata: dict[str, Any] | None,
) -> str | None:
    current = str(pipeline_workspace or "").strip()
    if current:
        return current
    metadata_value = str(
        normalize_session_metadata(metadata).get("pipeline_workspace", "") or ""
    ).strip()
    return metadata_value or None


def resolve_active_output_style(
    metadata: dict[str, Any] | None,
) -> str | None:
    value = normalize_output_style_name(
        normalize_session_metadata(metadata).get("active_style")
    )
    return value or None


def enrich_session_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    messages: Iterable[dict[str, Any]] | None = None,
    workspace_dir: str = "",
    pipeline_workspace: str | None | object = _SESSION_METADATA_UNSET,
    omicsclaw_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized = build_session_metadata(
        dict(metadata or {}),
        pipeline_workspace=pipeline_workspace,
    )
    workspace_override = (
        None
        if pipeline_workspace is _SESSION_METADATA_UNSET
        else pipeline_workspace
    )
    active_pipeline_workspace = resolve_active_pipeline_workspace(
        workspace_override,
        normalized,
    )

    active_workflow = _normalize_text_field(normalized.get("active_workflow"))
    plan_slug = _slugify(normalized.get("plan_slug"))
    last_active_task_id = _normalize_text_field(normalized.get("last_active_task_id"))
    workspace_kind = _normalize_text_field(normalized.get("workspace_kind"))

    interactive_plan = load_interactive_plan_from_metadata(normalized)
    if interactive_plan is not None:
        active_task = interactive_plan.active_task()
        if active_task is not None and not last_active_task_id:
            last_active_task_id = active_task.id
        if not active_workflow:
            active_workflow = _SESSION_WORKFLOW_INTERACTIVE_PLAN
        if not plan_slug:
            plan_slug = _slugify(
                interactive_plan.plan_kind or _SESSION_WORKFLOW_INTERACTIVE_PLAN
            )

    if active_pipeline_workspace:
        snapshot = load_pipeline_workspace_snapshot(
            resolve_pipeline_workspace(None, active_pipeline_workspace)
        )
        if snapshot.has_pipeline_state:
            if not last_active_task_id:
                last_active_task_id = snapshot.current_stage or last_active_task_id
            if not active_workflow:
                active_workflow = _SESSION_WORKFLOW_RESEARCH_PIPELINE
            if not plan_slug:
                plan_slug = _slugify(snapshot.workspace.name)
        if not workspace_kind:
            workspace_kind = WORKSPACE_KIND_ANALYSIS_RUN
    elif not workspace_kind:
        workspace_kind = WORKSPACE_KIND_CONVERSATION

    dataset_refs = _normalize_text_list(normalized.get("dataset_refs"))
    if messages is not None:
        dataset_refs = _normalize_text_list(
            [*dataset_refs, *_extract_dataset_refs_from_messages(messages)]
        )

    enabled_extension_refs = _load_enabled_extension_refs(omicsclaw_dir)
    if not enabled_extension_refs:
        enabled_extension_refs = _normalize_text_list(
            normalized.get("enabled_extension_refs")
        )

    domain = _normalize_text_field(normalized.get("domain")).lower()
    if not domain:
        combined_text = "\n".join(
            part
            for part in (
                resolve_session_title(normalized),
                _normalize_text_field(normalized.get("tag")),
                " ".join(dataset_refs),
                " ".join(
                    _flatten_message_content(message.get("content", ""))
                    for message in (messages or [])
                    if isinstance(message, dict)
                ),
            )
            if part
        )
        domain = _infer_domain_from_text(combined_text)

    return build_session_metadata(
        normalized,
        pipeline_workspace=active_pipeline_workspace,
        active_workflow=active_workflow,
        plan_slug=plan_slug,
        dataset_refs=dataset_refs,
        enabled_extension_refs=enabled_extension_refs,
        last_active_task_id=last_active_task_id,
        workspace_kind=workspace_kind,
        domain=domain,
    )


def parse_session_search_query(raw: str) -> SessionSearchQuery:
    try:
        tokens = re.findall(r'(?:[^\s"]+|"[^"]*")+', raw.strip()) if raw.strip() else []
        if raw.strip():
            import shlex
            tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.strip().split()

    query = SessionSearchQuery()
    free_parts: list[str] = []
    for token in tokens:
        key, sep, value = token.partition(":")
        if not sep:
            free_parts.append(token)
            continue
        normalized_key = key.lower().strip()
        normalized_value = _normalize_text_field(value)
        if normalized_key == "tag":
            query.tag = normalized_value
        elif normalized_key == "title":
            query.title = normalized_value
        elif normalized_key == "domain":
            query.domain = normalized_value.lower()
        elif normalized_key == "workspace":
            query.workspace = normalized_value
        else:
            free_parts.append(token)
    query.free_text = " ".join(free_parts).strip()
    return query


def _session_search_blob(
    *,
    session_id: str,
    preview: str,
    metadata: Mapping[str, Any],
    workspace: str,
    model: str,
) -> str:
    parts = [
        session_id,
        preview,
        resolve_session_title(metadata, preview=preview),
        resolve_session_tag(metadata),
        _normalize_text_field(metadata.get("active_style")),
        _normalize_text_field(metadata.get("active_workflow")),
        _normalize_text_field(metadata.get("plan_slug")),
        _normalize_text_field(metadata.get("last_active_task_id")),
        _normalize_text_field(metadata.get("workspace_kind")),
        _normalize_text_field(metadata.get("domain")),
        _normalize_text_field(workspace),
        _normalize_text_field(metadata.get("pipeline_workspace")),
        " ".join(_normalize_text_list(metadata.get("dataset_refs"))),
        " ".join(_normalize_text_list(metadata.get("enabled_extension_refs"))),
        model,
    ]
    return " ".join(part for part in parts if part).lower()


def _matches_session_query(
    session_row: Mapping[str, Any],
    query: SessionSearchQuery,
) -> bool:
    metadata = normalize_session_metadata(session_row.get("metadata"))
    preview = _normalize_text_field(session_row.get("preview"))
    title = resolve_session_title(metadata, preview=preview).lower()
    tag = resolve_session_tag(metadata).lower()
    domain = _normalize_text_field(metadata.get("domain")).lower()
    workspace_text = " ".join(
        part
        for part in (
            _normalize_text_field(session_row.get("workspace")),
            _normalize_text_field(metadata.get("pipeline_workspace")),
        )
        if part
    ).lower()
    search_blob = _session_search_blob(
        session_id=_normalize_text_field(session_row.get("session_id")),
        preview=preview,
        metadata=metadata,
        workspace=_normalize_text_field(session_row.get("workspace")),
        model=_normalize_text_field(session_row.get("model")),
    )

    if query.tag and query.tag.lower() not in tag:
        return False
    if query.title and query.title.lower() not in title:
        return False
    if query.domain and query.domain.lower() not in domain and query.domain.lower() not in search_blob:
        return False
    if query.workspace and query.workspace.lower() not in workspace_text:
        return False
    if query.free_text:
        if query.free_text.lower() not in search_blob:
            return False
    return True


def _format_session_state_summary(
    metadata: Mapping[str, Any],
    *,
    workspace_dir: str,
    preview: str,
) -> str:
    parts: list[str] = []
    active_workflow = _normalize_text_field(metadata.get("active_workflow"))
    if active_workflow:
        parts.append(active_workflow)
    active_style = _normalize_text_field(metadata.get("active_style"))
    if active_style:
        parts.append(active_style)
    tag = resolve_session_tag(metadata)
    if tag:
        parts.append(f"tag={tag}")
    domain = _normalize_text_field(metadata.get("domain"))
    if domain:
        parts.append(f"domain={domain}")
    task_id = _normalize_text_field(metadata.get("last_active_task_id"))
    if task_id:
        parts.append(f"task={task_id}")
    workspace_label = _session_workspace_label(
        workspace_dir=workspace_dir,
        pipeline_workspace=_normalize_text_field(metadata.get("pipeline_workspace")),
    )
    if workspace_label:
        parts.append(f"ws={workspace_label}")
    extension_count = len(_normalize_text_list(metadata.get("enabled_extension_refs")))
    if extension_count:
        parts.append(f"ext={extension_count}")
    dataset_count = len(_normalize_text_list(metadata.get("dataset_refs")))
    if dataset_count:
        parts.append(f"data={dataset_count}")
    return " · ".join(parts)


async def build_session_list_view(
    limit: int = 20,
    *,
    query: str = "",
) -> SessionListView:
    query_text = _normalize_text_field(query)
    sessions = await list_sessions(limit=0 if query_text else limit)
    search_query = parse_session_search_query(query_text)
    entries: list[SessionListEntry] = []
    for item in sessions:
        metadata = enrich_session_metadata(
            item.get("metadata"),
            workspace_dir=_normalize_text_field(item.get("workspace")),
        )
        row = {**item, "metadata": metadata}
        if query_text and not _matches_session_query(row, search_query):
            continue
        preview = _normalize_text_field(item.get("preview"))
        entries.append(
            SessionListEntry(
                session_id=_normalize_text_field(item.get("session_id")),
                preview=preview,
                title=resolve_session_title(metadata, preview=preview),
                tag=resolve_session_tag(metadata),
                active_style=resolve_active_output_style(metadata) or "",
                active_workflow=_normalize_text_field(metadata.get("active_workflow")),
                workspace_label=_session_workspace_label(
                    workspace_dir=_normalize_text_field(item.get("workspace")),
                    pipeline_workspace=resolve_active_pipeline_workspace(
                        None,
                        metadata,
                    )
                    or "",
                ),
                workspace_kind=_normalize_text_field(metadata.get("workspace_kind")),
                last_active_task_id=_normalize_text_field(
                    metadata.get("last_active_task_id")
                ),
                domain=_normalize_text_field(metadata.get("domain")),
                state_summary=_format_session_state_summary(
                    metadata,
                    workspace_dir=_normalize_text_field(item.get("workspace")),
                    preview=preview,
                ),
                enabled_extension_count=len(
                    _normalize_text_list(metadata.get("enabled_extension_refs"))
                ),
                dataset_ref_count=len(
                    _normalize_text_list(metadata.get("dataset_refs"))
                ),
                message_count=int(item.get("message_count", 0) or 0),
                compacted_tool_result_count=int(
                    item.get("compacted_tool_result_count", 0) or 0
                ),
                plan_reference_count=int(item.get("plan_reference_count", 0) or 0),
                advisory_event_count=int(item.get("advisory_event_count", 0) or 0),
                model=_normalize_text_field(item.get("model")),
                updated_at=_normalize_text_field(item.get("updated_at")),
                updated_label=format_relative_time(item.get("updated_at")),
            )
        )

    if query_text and limit > 0:
        entries = entries[:limit]

    empty_text = (
        f"No saved sessions matched: {query_text}"
        if query_text
        else "No saved sessions."
    )
    return SessionListView(
        entries=entries,
        empty_text=empty_text,
        query=query_text,
    )


def format_session_list_plain(
    view: SessionListView,
    *,
    header: str = "Recent sessions (newest first):",
    hint_text: str | None = None,
) -> str:
    if not view.entries:
        return view.empty_text

    lines = [header]
    if view.query:
        lines.append(f"Query: {view.query}")
    for entry in view.entries:
        display_title = entry.title or entry.preview
        line = f"  [{entry.session_id}]  {display_title[:48]}  ({entry.message_count} msgs)"
        if entry.compacted_tool_result_count > 0:
            line += f" · {entry.compacted_tool_result_count} compacted"
        if entry.plan_reference_count > 0:
            line += f" · {entry.plan_reference_count} plan"
        if entry.advisory_event_count > 0:
            line += f" · {entry.advisory_event_count} advisory"
        lines.append(line)
        if entry.state_summary:
            lines.append(f"     {entry.state_summary}")
    final_hint = view.hint_text if hint_text is None else hint_text
    if final_hint:
        lines.append("")
        lines.append(final_hint)
    return "\n".join(lines)


def build_new_session_command_view(session_id: str) -> SessionCommandView:
    return SessionCommandView(
        output_text=f"New session: {session_id}",
        session_id=session_id,
        session_metadata={},
        replace_session_metadata=True,
        clear_messages=True,
        clear_pipeline_workspace=True,
        reset_session_runtime=True,
    )


def build_session_title_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
) -> SessionCommandView:
    metadata = normalize_session_metadata(dict(session_metadata or {}))
    current = resolve_session_title(metadata)
    value = _normalize_text_field(arg)
    if not value:
        return SessionCommandView(
            output_text=(
                f"Current session title: {current or '(unset)'}\n"
                "Usage: /session-title <title>  |  /session-title clear"
            )
        )
    if value.lower() == "clear":
        return SessionCommandView(
            output_text="Session title cleared.",
            session_metadata=build_session_metadata(metadata, title=None),
            replace_session_metadata=True,
        )
    return SessionCommandView(
        output_text=f"Session title set to: {value}",
        session_metadata=build_session_metadata(metadata, title=value),
        replace_session_metadata=True,
    )


def build_session_tag_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
) -> SessionCommandView:
    metadata = normalize_session_metadata(dict(session_metadata or {}))
    current = resolve_session_tag(metadata)
    value = _normalize_text_field(arg)
    if not value:
        return SessionCommandView(
            output_text=(
                f"Current session tag: {current or '(unset)'}\n"
                "Usage: /session-tag <tag>  |  /session-tag clear"
            )
        )
    if value.lower() == "clear":
        return SessionCommandView(
            output_text="Session tag cleared.",
            session_metadata=build_session_metadata(metadata, tag=None),
            replace_session_metadata=True,
        )
    return SessionCommandView(
        output_text=f"Session tag set to: {value}",
        session_metadata=build_session_metadata(metadata, tag=value),
        replace_session_metadata=True,
    )


def build_clear_conversation_command_view() -> SessionCommandView:
    return SessionCommandView(
        output_text="Conversation history cleared.",
        clear_messages=True,
    )


def build_export_session_command_view(
    session_id: str,
    messages: list[dict],
    *,
    workspace_dir: str | Path,
) -> SessionCommandView:
    export_dir = Path(workspace_dir) / "exports"
    export_path = export_dir / f"omicsclaw_session_{session_id}.md"
    try:
        export_conversation_to_markdown(session_id, messages, export_path)
    except Exception as exc:
        return SessionCommandView(
            output_text=f"Export failed: {exc}",
            success=False,
        )

    return SessionCommandView(
        output_text=f"Session exported to: {export_path}",
        export_path=str(export_path),
    )


def _flatten_message_content(content: Any) -> str:
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return " ".join(str(part) for part in parts if str(part).strip()).strip()
    return str(content or "").strip()


def _conversation_preview_lines(
    messages: Iterable[dict[str, Any]],
    *,
    limit: int = 6,
    max_len: int = 160,
) -> list[str]:
    preview_lines: list[str] = []
    visible = [message for message in messages if message.get("role") in ("user", "assistant")]
    for message in visible[-limit:]:
        role = str(message.get("role", "") or "")
        content = _flatten_message_content(message.get("content", ""))
        if not content:
            continue
        preview = escape(content[:max_len])
        if role == "user":
            preview_lines.append(f"[bold cyan]❯ [/bold cyan]{preview}")
        elif role == "assistant":
            preview_lines.append(f"[dim]{preview}[/dim]")
    return preview_lines


def _session_transcript_from_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    transcript = data.get("transcript")
    if isinstance(transcript, list):
        return [message for message in transcript if isinstance(message, dict)]
    messages = data.get("messages")
    if isinstance(messages, list):
        return [message for message in messages if isinstance(message, dict)]
    return []


def _session_transcript_summary_from_data(
    data: dict[str, Any],
    *,
    workspace_dir: str = "",
    session_metadata: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    summary = data.get("transcript_summary")
    if isinstance(summary, dict):
        compacted = summary.get("compacted_tool_results")
        plans = summary.get("plan_references")
        advisories = summary.get("advisory_events")
        if (
            isinstance(compacted, list)
            and isinstance(plans, list)
            and isinstance(advisories, list)
        ):
            return {
                "compacted_tool_results": [item for item in compacted if isinstance(item, dict)],
                "plan_references": [item for item in plans if isinstance(item, dict)],
                "advisory_events": [item for item in advisories if isinstance(item, dict)],
            }

    built = build_transcript_summary(
        _session_transcript_from_data(data),
        metadata=session_metadata or data.get("metadata"),
        workspace=workspace_dir or str(data.get("workspace", "") or ""),
    ).to_dict()
    return {
        key: [item for item in built.get(key, []) if isinstance(item, dict)]
        for key in ("compacted_tool_results", "plan_references", "advisory_events")
    }


def _append_session_state_lines(
    lines: list[str],
    *,
    metadata: Mapping[str, Any],
    workspace_dir: str,
    preview: str = "",
) -> None:
    title = resolve_session_title(metadata, preview=preview)
    tag = resolve_session_tag(metadata)
    active_style = resolve_active_output_style(metadata)
    active_pipeline_workspace = resolve_active_pipeline_workspace(None, dict(metadata))
    active_workflow = _normalize_text_field(metadata.get("active_workflow"))
    plan_slug = _normalize_text_field(metadata.get("plan_slug"))
    last_active_task_id = _normalize_text_field(metadata.get("last_active_task_id"))
    workspace_kind = _normalize_text_field(metadata.get("workspace_kind"))
    domain = _normalize_text_field(metadata.get("domain"))
    active_memory_scope = normalize_scoped_memory_scope(
        metadata.get("active_memory_scope")
    )
    dataset_refs = _normalize_text_list(metadata.get("dataset_refs"))
    enabled_extension_refs = _normalize_text_list(metadata.get("enabled_extension_refs"))

    if title:
        lines.append(f"[dim]Title:[/dim] [cyan]{escape(title)}[/cyan]")
    if tag:
        lines.append(f"[dim]Tag:[/dim] [cyan]{escape(tag)}[/cyan]")
    if active_pipeline_workspace:
        lines.append(
            f"[dim]Pipeline Workspace:[/dim] [cyan]{escape(active_pipeline_workspace)}[/cyan]"
        )
    if active_style:
        lines.append(f"[dim]Style:[/dim] [cyan]{escape(active_style)}[/cyan]")
    if active_workflow:
        lines.append(f"[dim]Workflow:[/dim] [cyan]{escape(active_workflow)}[/cyan]")
    if plan_slug:
        lines.append(f"[dim]Plan Slug:[/dim] [cyan]{escape(plan_slug)}[/cyan]")
    if last_active_task_id:
        lines.append(
            f"[dim]Last Active Task:[/dim] [cyan]{escape(last_active_task_id)}[/cyan]"
        )
    if workspace_kind:
        lines.append(
            f"[dim]Workspace Kind:[/dim] [cyan]{escape(workspace_kind)}[/cyan]"
        )
    if domain:
        lines.append(f"[dim]Domain:[/dim] [cyan]{escape(domain)}[/cyan]")
    if active_memory_scope:
        lines.append(
            f"[dim]Memory Scope:[/dim] [cyan]{escape(active_memory_scope)}[/cyan]"
        )
    if dataset_refs:
        sample = ", ".join(dataset_refs[:3])
        suffix = " ..." if len(dataset_refs) > 3 else ""
        lines.append(
            f"[dim]Datasets:[/dim] {len(dataset_refs)} ref(s) — [cyan]{escape(sample)}{escape(suffix)}[/cyan]"
        )
    if enabled_extension_refs:
        sample = ", ".join(enabled_extension_refs[:4])
        suffix = " ..." if len(enabled_extension_refs) > 4 else ""
        lines.append(
            f"[dim]Extensions:[/dim] {len(enabled_extension_refs)} enabled — [cyan]{escape(sample)}{escape(suffix)}[/cyan]"
        )


def build_resume_session_command_view_from_data(data: dict[str, Any]) -> SessionCommandView:
    session_id = str(data.get("session_id", "") or "")
    workspace_dir = str(data.get("workspace", "") or "").strip()
    messages = _session_transcript_from_data(data)
    preview = _normalize_text_field(data.get("preview"))
    if not preview and messages:
        preview = _flatten_message_content(messages[0].get("content", ""))
    session_metadata = enrich_session_metadata(
        data.get("metadata"),
        messages=messages,
        workspace_dir=workspace_dir,
    )
    transcript_summary = _session_transcript_summary_from_data(
        data,
        workspace_dir=workspace_dir,
        session_metadata=session_metadata,
    )
    compacted_tool_results = transcript_summary["compacted_tool_results"]
    plan_references = transcript_summary["plan_references"]
    advisory_events = transcript_summary["advisory_events"]

    lines = [f"[green]Resumed session:[/green] [yellow]{escape(session_id)}[/yellow]"]
    if workspace_dir:
        lines.append(f"[dim]Workspace:[/dim] [cyan]{escape(workspace_dir)}[/cyan]")
    _append_session_state_lines(
        lines,
        metadata=session_metadata,
        workspace_dir=workspace_dir,
        preview=preview,
    )
    for line in build_interactive_plan_summary_lines(session_metadata):
        label, _, value = line.partition(": ")
        lines.append(
            f"[dim]{escape(label)}:[/dim] {escape(value)}"
        )
    if compacted_tool_results:
        lines.append(
            f"[dim]Compacted Results:[/dim] {len(compacted_tool_results)} saved artifact(s)"
        )
    if plan_references:
        lines.append(
            f"[dim]Plan References:[/dim] {len(plan_references)} linked plan artifact(s)"
        )
    if advisory_events:
        lines.append(
            f"[dim]Advisory Events:[/dim] {len(advisory_events)} recorded hint(s)"
        )

    preview_lines = _conversation_preview_lines(messages)
    if preview_lines:
        lines.append("")
        lines.append("[dim]── Conversation history ──[/dim]")
        lines.extend(preview_lines)
        lines.append("[dim]── End of history ──[/dim]")

    return SessionCommandView(
        output_text="\n".join(lines),
        render_as_markup=True,
        session_id=session_id,
        workspace_dir=workspace_dir,
        session_metadata=session_metadata,
        replace_session_metadata=True,
        messages=messages,
        replace_messages=True,
    )


async def build_resume_session_command_view(target_id: str) -> SessionCommandView:
    data = await load_session(target_id)
    if not data:
        return SessionCommandView(
            output_text=f"Session '{target_id}' not found.",
            success=False,
        )
    return build_resume_session_command_view_from_data(data)


def build_current_session_command_view(
    *,
    session_id: str,
    workspace_dir: str,
    model: str,
    provider: str,
    messages: list[dict[str, Any]],
    session_metadata: dict[str, Any] | None = None,
    pipeline_workspace: str | None | object = _SESSION_METADATA_UNSET,
    omicsclaw_dir: str | Path | None = None,
) -> SessionCommandView:
    resolved_metadata = enrich_session_metadata(
        session_metadata,
        messages=messages,
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
        omicsclaw_dir=omicsclaw_dir,
    )
    active_pipeline_workspace = resolve_active_pipeline_workspace(
        pipeline_workspace,
        resolved_metadata,
    )
    transcript_summary = build_transcript_summary(
        messages,
        metadata=resolved_metadata,
        workspace=workspace_dir,
    ).to_dict()

    lines = [
        f"[dim]Session:[/dim]   [yellow]{escape(session_id)}[/yellow]",
        f"[dim]Workspace:[/dim] [cyan]{escape(workspace_dir)}[/cyan]",
    ]
    _append_session_state_lines(
        lines,
        metadata=resolved_metadata,
        workspace_dir=workspace_dir,
    )
    for line in build_interactive_plan_summary_lines(resolved_metadata):
        label, _, value = line.partition(": ")
        lines.append(
            f"[dim]{escape(label)}:[/dim] {escape(value)}"
        )
    lines.extend(
        (
            f"[dim]Model:[/dim]     [magenta]{escape(model)}[/magenta]",
            f"[dim]Provider:[/dim]  [magenta]{escape(provider)}[/magenta]",
            f"[dim]Messages:[/dim]  {len([m for m in messages if m.get('role') in ('user', 'assistant')])}",
        )
    )
    if transcript_summary["compacted_tool_results"]:
        lines.append(
            f"[dim]Compacted:[/dim] {len(transcript_summary['compacted_tool_results'])} tool result artifact(s)"
        )
    if transcript_summary["plan_references"]:
        lines.append(
            f"[dim]Plan Refs:[/dim] {len(transcript_summary['plan_references'])} linked plan artifact(s)"
        )
    if transcript_summary["advisory_events"]:
        lines.append(
            f"[dim]Advisories:[/dim] {len(transcript_summary['advisory_events'])} recorded hint(s)"
        )

    snapshot = load_pipeline_workspace_snapshot(
        resolve_pipeline_workspace(
            None,
            active_pipeline_workspace or workspace_dir,
        )
    )
    if snapshot.has_pipeline_state:
        snapshot_view = build_pipeline_display_from_snapshot(snapshot)
        lines.append(
            f"[dim]Pipeline Stage:[/dim] [cyan]{escape(snapshot_view.current_stage or 'idle')}[/cyan]"
        )
        if snapshot_view.plan.status:
            lines.append(
                f"[dim]Plan Status:[/dim] [cyan]{escape(snapshot_view.plan.status)}[/cyan]"
            )

    return SessionCommandView(
        output_text="\n".join(lines),
        render_as_markup=True,
    )


async def build_delete_session_command_view(
    target_id: str,
    *,
    current_session_id: str,
) -> SessionCommandView:
    if not target_id:
        return SessionCommandView(
            output_text="Usage: /delete <session-id>",
            success=False,
        )
    if target_id == current_session_id:
        return SessionCommandView(
            output_text="Cannot delete the current active session.",
            success=False,
        )

    data = await load_session(target_id)
    if not data:
        return SessionCommandView(
            output_text=f"Session '{target_id}' not found.",
            success=False,
        )

    deleted = await delete_session(str(data.get("session_id", "") or ""))
    if deleted:
        return SessionCommandView(
            output_text=f"Deleted session {data['session_id']}.",
        )
    return SessionCommandView(
        output_text="Failed to delete session.",
        success=False,
    )
