"""Shared scoped-memory command helpers for interactive CLI/TUI."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omicsclaw.memory.scoped_memory import (
    DEFAULT_SCOPED_MEMORY_SCOPE,
    SCOPED_MEMORY_SCOPES,
    normalize_scoped_memory_freshness,
    normalize_scoped_memory_scope,
    prune_scoped_memories,
    resolve_scoped_memory_root,
    write_scoped_memory,
)
from omicsclaw.memory.scoped_memory_index import list_scoped_memory_records

from ._session_command_support import SessionCommandView, normalize_session_metadata


def resolve_active_scoped_memory_scope(
    metadata: Mapping[str, Any] | None,
) -> str:
    return normalize_scoped_memory_scope(dict(metadata or {}).get("active_memory_scope"))


def build_memory_command_view(
    arg: str,
    *,
    session_metadata: Mapping[str, Any] | None,
    workspace_dir: str = "",
    pipeline_workspace: str = "",
    owner: str = "",
) -> SessionCommandView:
    tokens = shlex.split(arg.strip()) if arg.strip() else []
    metadata = normalize_session_metadata(dict(session_metadata or {}))
    active_scope = resolve_active_scoped_memory_scope(metadata)
    root = resolve_scoped_memory_root(
        workspace_dir=workspace_dir,
        pipeline_workspace=pipeline_workspace,
    )
    root_text = str(root) if root is not None else "(no active workspace)"

    if not tokens:
        return SessionCommandView(
            output_text=(
                f"Scoped memory root: {root_text}\n"
                f"Active scoped memory scope: {active_scope or '(unset)'}\n"
                f"Scopes: {', '.join(SCOPED_MEMORY_SCOPES)}\n"
                "Usage:\n"
                "  /memory list [scope|all] [query]\n"
                "  /memory add [scope] [--title <title>] [--freshness <level>] [--domain <name>] [--dataset <path>] [--keyword <term>] <text>\n"
                "  /memory add project \"PBMC QC defaults :: Prefer mito cutoff 20% before Harmony.\"\n"
                "  /memory prune [scope|all] [--days <n>] [--apply]\n"
                "  /memory scope <scope|clear>"
            )
        )

    subcommand = tokens[0].lower()
    if subcommand == "scope":
        if len(tokens) < 2:
            return SessionCommandView(
                output_text=(
                    f"Active scoped memory scope: {active_scope or '(unset)'}\n"
                    f"Available scopes: {', '.join(SCOPED_MEMORY_SCOPES)}"
                )
            )

        requested = tokens[1].strip().lower()
        if requested == "clear":
            metadata.pop("active_memory_scope", None)
            return SessionCommandView(
                output_text="Scoped memory scope cleared.",
                session_metadata=metadata,
                replace_session_metadata=True,
            )

        normalized_scope = normalize_scoped_memory_scope(requested)
        if not normalized_scope:
            return SessionCommandView(
                output_text=f"Unknown scoped memory scope: {tokens[1]}",
                success=False,
            )

        metadata["active_memory_scope"] = normalized_scope
        return SessionCommandView(
            output_text=f"Active scoped memory scope set to: {normalized_scope}",
            session_metadata=metadata,
            replace_session_metadata=True,
        )

    if subcommand == "list":
        scope, query = _parse_list_args(tokens[1:], active_scope=active_scope)
        records = list_scoped_memory_records(
            root,
            scope=scope,
            query=query,
            limit=12,
        )
        if not records:
            return SessionCommandView(
                output_text=(
                    f"No scoped memories found under: {root_text}"
                    if not query
                    else f"No scoped memories matched '{query}' under: {root_text}"
                )
            )
        lines = [
            f"Scoped memories: {len(records)}",
            f"Root: {root_text}",
            f"Active scope: {active_scope or '(unset)'}",
        ]
        if scope:
            lines.append(f"Listing scope: {scope}")
        if query:
            lines.append(f"Query: {query}")
        lines.append("")
        for record in records:
            lines.append(
                f"- [{record.scope}] {record.title} ({record.memory_id})"
            )
            lines.append(
                f"  owner={record.owner or 'unknown'} | freshness={record.freshness} | updated={record.updated_at[:10]} | path={record.relative_path}"
            )
            if record.description:
                lines.append(f"  {record.description}")
        return SessionCommandView(output_text="\n".join(lines))

    if subcommand == "add":
        try:
            parsed = _parse_add_args(tokens[1:], active_scope=active_scope)
        except ValueError as exc:
            return SessionCommandView(output_text=str(exc), success=False)

        effective_owner = owner or os.environ.get("USER", "") or "interactive"
        record = write_scoped_memory(
            body=parsed["body"],
            scope=parsed["scope"],
            title=parsed["title"],
            freshness=parsed["freshness"],
            domain=parsed["domain"],
            dataset_refs=parsed["dataset_refs"],
            keywords=parsed["keywords"],
            owner=effective_owner,
            workspace_dir=workspace_dir,
            pipeline_workspace=pipeline_workspace,
        )
        return SessionCommandView(
            output_text=(
                f"Scoped memory saved: {record.title}\n"
                f"Scope: {record.scope}\n"
                f"Freshness: {record.freshness}\n"
                f"Owner: {record.owner}\n"
                f"Path: {record.path}"
            )
        )

    if subcommand == "prune":
        try:
            scope, stale_days, apply_changes = _parse_prune_args(tokens[1:], active_scope=active_scope)
        except ValueError as exc:
            return SessionCommandView(output_text=str(exc), success=False)

        result = prune_scoped_memories(
            workspace_dir=workspace_dir,
            pipeline_workspace=pipeline_workspace,
            scope=scope,
            stale_days=stale_days,
            apply_changes=apply_changes,
        )
        if not result.candidates:
            return SessionCommandView(
                output_text=f"No scoped memories to prune under: {result.root}"
            )

        lines = [
            (
                f"Pruned {result.deleted_count} scoped memories."
                if apply_changes
                else f"Scoped memory prune preview: {len(result.candidates)} candidate(s)"
            ),
            f"Root: {result.root}",
        ]
        if result.scope:
            lines.append(f"Scope: {result.scope}")
        lines.append("")
        for candidate in result.candidates:
            lines.append(
                f"- [{candidate.record.scope}] {candidate.record.title} ({candidate.record.memory_id})"
            )
            lines.append(f"  reason: {candidate.reason}")
            lines.append(f"  path: {candidate.record.relative_path}")
        if not apply_changes:
            lines.extend(("", "Re-run with /memory prune ... --apply to delete these files."))
        return SessionCommandView(output_text="\n".join(lines))

    return SessionCommandView(
        output_text=f"Unknown /memory subcommand: {subcommand}",
        success=False,
    )


def _parse_list_args(tokens: list[str], *, active_scope: str) -> tuple[str, str]:
    scope = ""
    if tokens:
        candidate = normalize_scoped_memory_scope(tokens[0])
        if candidate:
            scope = candidate
            tokens = tokens[1:]
        elif tokens[0].lower() == "all":
            tokens = tokens[1:]
    if not scope and active_scope:
        scope = active_scope
    return scope, " ".join(tokens).strip()


def _parse_add_args(tokens: list[str], *, active_scope: str) -> dict[str, Any]:
    scope = ""
    title = ""
    freshness = ""
    domain = ""
    dataset_refs: list[str] = []
    keywords: list[str] = []
    body_parts: list[str] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--scope":
            index += 1
            if index >= len(tokens):
                raise ValueError("Usage: /memory add [scope] [--title <title>] <text>")
            scope = normalize_scoped_memory_scope(tokens[index])
            if not scope:
                raise ValueError(f"Unknown scoped memory scope: {tokens[index]}")
        elif token == "--title":
            index += 1
            if index >= len(tokens):
                raise ValueError("Missing value for --title")
            title = tokens[index].strip()
        elif token == "--freshness":
            index += 1
            if index >= len(tokens):
                raise ValueError("Missing value for --freshness")
            freshness = normalize_scoped_memory_freshness(tokens[index])
            if not freshness:
                raise ValueError(
                    "Unknown freshness. Use one of: stable, evolving, volatile"
                )
        elif token == "--domain":
            index += 1
            if index >= len(tokens):
                raise ValueError("Missing value for --domain")
            domain = tokens[index].strip().lower()
        elif token == "--dataset":
            index += 1
            if index >= len(tokens):
                raise ValueError("Missing value for --dataset")
            dataset_refs.append(tokens[index].strip())
        elif token == "--keyword":
            index += 1
            if index >= len(tokens):
                raise ValueError("Missing value for --keyword")
            keywords.append(tokens[index].strip())
        else:
            body_parts.append(token)
        index += 1

    if body_parts and not scope:
        candidate = normalize_scoped_memory_scope(body_parts[0])
        if candidate:
            scope = candidate
            body_parts = body_parts[1:]

    normalized_scope = scope or active_scope or DEFAULT_SCOPED_MEMORY_SCOPE
    body = " ".join(body_parts).strip()
    if "::" in body and not title:
        title_part, _, body_part = body.partition("::")
        title = title_part.strip()
        body = body_part.strip()
    if not body:
        raise ValueError(
            "Usage: /memory add [scope] [--title <title>] [--freshness <level>] <text>"
        )

    return {
        "scope": normalized_scope,
        "title": title,
        "freshness": freshness,
        "domain": domain,
        "dataset_refs": dataset_refs,
        "keywords": keywords,
        "body": body,
    }


def _parse_prune_args(tokens: list[str], *, active_scope: str) -> tuple[str, int | None, bool]:
    scope = ""
    stale_days: int | None = None
    apply_changes = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--days":
            index += 1
            if index >= len(tokens):
                raise ValueError("Missing value for --days")
            try:
                stale_days = int(tokens[index])
            except ValueError as exc:
                raise ValueError("Expected integer value for --days") from exc
        elif token == "--apply":
            apply_changes = True
        elif token.lower() == "all":
            scope = ""
        elif not scope:
            candidate = normalize_scoped_memory_scope(token)
            if candidate:
                scope = candidate
            else:
                raise ValueError(
                    f"Unknown prune argument: {token}. Use a scope name, all, --days, or --apply."
                )
        else:
            raise ValueError(
                f"Unknown prune argument: {token}. Use a scope name, all, --days, or --apply."
            )
        index += 1
    return scope or active_scope, stale_days, apply_changes


__all__ = [
    "build_memory_command_view",
    "resolve_active_scoped_memory_scope",
]
