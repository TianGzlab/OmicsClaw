from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .task_store import (
    TASK_STATUS_BLOCKED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PENDING,
    TASK_STATUS_SKIPPED,
    TaskRecord,
    TaskStore,
)
from .tool_spec import (
    RESULT_POLICY_WEB_REFERENCE,
    RISK_LEVEL_MEDIUM,
    ToolSpec,
)
from .tool_validation import ToolInputValidationResult

_TASK_STATUSES = (
    TASK_STATUS_PENDING,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_SKIPPED,
    TASK_STATUS_BLOCKED,
    TASK_STATUS_FAILED,
)
_DEFAULT_GLOB_LIMIT = 200
_DEFAULT_GREP_LIMIT = 50
_DEFAULT_TOOL_SEARCH_LIMIT = 12
_DEFAULT_WEB_MAX_CHARS = 12000
_DEFAULT_FILE_READ_MAX_CHARS = 12000
_MAX_GREP_FILE_BYTES = 1_000_000
_TOKEN_RE = re.compile(r"[a-z0-9_-]+")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _validate_file_read_input(
    arguments: dict[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
) -> ToolInputValidationResult:
    start_line = arguments.get("start_line")
    end_line = arguments.get("end_line")
    if start_line is not None and end_line is not None:
        try:
            if int(end_line) < int(start_line):
                return ToolInputValidationResult(
                    valid=False,
                    message="'end_line' must be greater than or equal to 'start_line'.",
                )
        except (TypeError, ValueError):
            return ToolInputValidationResult(
                valid=False,
                message="'start_line' and 'end_line' must be integers when provided.",
            )
    return ToolInputValidationResult(valid=True)


def _validate_web_url_input(
    arguments: dict[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
) -> ToolInputValidationResult:
    target = str(arguments.get("url", "") or arguments.get("query", "") or "").strip()
    if "url" in arguments and target and not target.startswith(("http://", "https://")):
        return ToolInputValidationResult(
            valid=False,
            message="URL must start with http:// or https://.",
        )
    return ToolInputValidationResult(valid=True)


def _classify_workspace_mutation(
    arguments: dict[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "label": "workspace_mutation",
        "risk": "medium",
    }


def _classify_network_access(
    arguments: dict[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "label": "network_access",
        "risk": "medium",
    }


def build_engineering_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="tool_search",
            description=(
                "Search available OmicsClaw tools by name, description, and tags. "
                "Use this before assuming a tool exists."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text for tool names, capabilities, or tags.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tools to return. Default: 12.",
                    },
                    "include_schema": {
                        "type": "boolean",
                        "description": "Include parameter names in the response.",
                    },
                },
            },
            surfaces=("bot", "interactive"),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("discovery", "tooling"),
        ),
        ToolSpec(
            name="file_read",
            description=(
                "Read a text file from the active workspace, pipeline workspace, or trusted project directories."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read."},
                    "start_line": {
                        "type": "integer",
                        "description": "1-based starting line number. Default: 1.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "1-based ending line number. Default: end of file.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return. Default: 12000.",
                    },
                },
                "required": ["path"],
            },
            surfaces=("bot", "interactive"),
            context_params=("surface", "workspace", "pipeline_workspace"),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("workspace", "inspection"),
            input_validator=_validate_file_read_input,
        ),
        ToolSpec(
            name="glob_files",
            description=(
                "Find files under the active workspace or project directories using a glob pattern."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern such as '**/*.py' or 'data/*.csv'.",
                    },
                    "root": {
                        "type": "string",
                        "description": "Optional root directory to search from.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of matches to return. Default: 200.",
                    },
                },
                "required": ["pattern"],
            },
            surfaces=("bot", "interactive"),
            context_params=("surface", "workspace", "pipeline_workspace"),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("workspace", "inspection", "search"),
        ),
        ToolSpec(
            name="grep_files",
            description=(
                "Search text files under the active workspace or project directories using a regular expression."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression to search for.",
                    },
                    "root": {
                        "type": "string",
                        "description": "Optional root directory to search from.",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Optional glob filter for candidate files. Default: '**/*'.",
                    },
                    "max_matches": {
                        "type": "integer",
                        "description": "Maximum number of matches to return. Default: 50.",
                    },
                },
                "required": ["pattern"],
            },
            surfaces=("bot", "interactive"),
            context_params=("surface", "workspace", "pipeline_workspace"),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("workspace", "inspection", "search"),
        ),
        ToolSpec(
            name="file_write",
            description=(
                "Create or overwrite a text file inside the active workspace or a safe engineering output workspace."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to write."},
                    "content": {"type": "string", "description": "Full file contents."},
                    "create_dirs": {
                        "type": "boolean",
                        "description": "Create parent directories when missing. Default: true.",
                    },
                },
                "required": ["path", "content"],
            },
            surfaces=("bot", "interactive"),
            context_params=("surface", "workspace", "pipeline_workspace"),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "mutation"),
            speculative_classifier=_classify_workspace_mutation,
        ),
        ToolSpec(
            name="file_edit",
            description=(
                "Perform a controlled text replacement inside an existing text file."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to edit."},
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to replace.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all matches instead of exactly one match.",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
            surfaces=("bot", "interactive"),
            context_params=("surface", "workspace", "pipeline_workspace"),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "mutation"),
            speculative_classifier=_classify_workspace_mutation,
        ),
        ToolSpec(
            name="task_create",
            description="Create a persisted engineering task for the current session.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Optional stable task id."},
                    "title": {"type": "string", "description": "Task title."},
                    "description": {"type": "string", "description": "Task description."},
                    "owner": {"type": "string", "description": "Task owner label."},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional prerequisite task ids.",
                    },
                },
                "required": ["title"],
            },
            surfaces=("bot", "interactive"),
            context_params=("session_id", "chat_id", "surface", "workspace", "pipeline_workspace"),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_config=True,
            policy_tags=("planning", "task"),
        ),
        ToolSpec(
            name="task_get",
            description="Read one persisted engineering task for the current session.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task id to fetch."},
                },
                "required": ["task_id"],
            },
            surfaces=("bot", "interactive"),
            context_params=("session_id", "chat_id", "surface", "workspace", "pipeline_workspace"),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("planning", "task"),
        ),
        ToolSpec(
            name="task_list",
            description="List persisted engineering tasks for the current session.",
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": list(_TASK_STATUSES),
                        "description": "Optional status filter.",
                    },
                },
            },
            surfaces=("bot", "interactive"),
            context_params=("session_id", "chat_id", "surface", "workspace", "pipeline_workspace"),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("planning", "task"),
        ),
        ToolSpec(
            name="task_update",
            description="Update status or details for a persisted engineering task.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task id to update."},
                    "status": {
                        "type": "string",
                        "enum": list(_TASK_STATUSES),
                        "description": "New task status.",
                    },
                    "title": {"type": "string", "description": "Updated title."},
                    "description": {"type": "string", "description": "Updated description."},
                    "owner": {"type": "string", "description": "Updated owner."},
                    "summary": {
                        "type": "string",
                        "description": "Short execution summary stored in metadata.summary.",
                    },
                    "artifact_ref": {
                        "type": "string",
                        "description": "Artifact path or identifier to append.",
                    },
                },
                "required": ["task_id"],
            },
            surfaces=("bot", "interactive"),
            context_params=("session_id", "chat_id", "surface", "workspace", "pipeline_workspace"),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_config=True,
            policy_tags=("planning", "task"),
        ),
        ToolSpec(
            name="todo_write",
            description=(
                "Replace the current session task list with a structured todo plan."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "status": {"type": "string", "enum": list(_TASK_STATUSES)},
                                "owner": {"type": "string"},
                                "dependencies": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "artifact_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title"],
                        },
                        "description": "Complete task list to persist.",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional task store kind label.",
                    },
                },
                "required": ["items"],
            },
            surfaces=("bot", "interactive"),
            context_params=("session_id", "chat_id", "surface", "workspace", "pipeline_workspace"),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_config=True,
            policy_tags=("planning", "task", "todo"),
        ),
        ToolSpec(
            name="web_fetch",
            description="Fetch a webpage and convert the result to markdown for local reasoning.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute URL to fetch."},
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return. Default: 12000.",
                    },
                },
                "required": ["url"],
            },
            surfaces=("bot", "interactive"),
            read_only=True,
            concurrency_safe=True,
            result_policy=RESULT_POLICY_WEB_REFERENCE,
            risk_level=RISK_LEVEL_MEDIUM,
            touches_network=True,
            policy_tags=("network", "reference"),
            input_validator=_validate_web_url_input,
            speculative_classifier=_classify_network_access,
        ),
        ToolSpec(
            name="web_search",
            description=(
                "Search the web for method documentation, package docs, workflow guidance, or external references."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing the method or topic.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to fetch. Default: 3.",
                    },
                    "topic": {
                        "type": "string",
                        "enum": ["general", "news", "finance"],
                        "description": "Search topic. Default: general.",
                    },
                },
                "required": ["query"],
            },
            executor_name="web_method_search",
            surfaces=("bot", "interactive"),
            read_only=True,
            concurrency_safe=True,
            result_policy=RESULT_POLICY_WEB_REFERENCE,
            risk_level=RISK_LEVEL_MEDIUM,
            touches_network=True,
            policy_tags=("network", "reference", "discovery"),
            input_validator=_validate_web_url_input,
            speculative_classifier=_classify_network_access,
        ),
    ]


def build_engineering_tool_executors(
    *,
    omicsclaw_dir: str | Path,
    state_root: str | Path | None = None,
    tool_specs_supplier: Callable[[], Iterable[ToolSpec]] | None = None,
) -> dict[str, object]:
    root = Path(omicsclaw_dir).expanduser().resolve()
    runtime_state_root = _resolve_state_root(state_root)

    async def tool_search(args: dict[str, Any]) -> str:
        specs = tuple(tool_specs_supplier() if tool_specs_supplier else ())
        query = str(args.get("query", "") or "").strip().lower()
        limit = _bounded_int(args.get("limit"), default=_DEFAULT_TOOL_SEARCH_LIMIT, minimum=1, maximum=100)
        include_schema = bool(args.get("include_schema", False))

        tokens = _tokenize(query)
        matches: list[tuple[int, ToolSpec]] = []
        for spec in specs:
            score = _tool_match_score(spec, query=query, tokens=tokens)
            if query and score <= 0:
                continue
            matches.append((score, spec))

        matches.sort(key=lambda item: (-item[0], item[1].name))
        payload = [
            _tool_summary(spec, include_schema=include_schema)
            for _, spec in matches[:limit]
        ]
        return json.dumps(
            {
                "query": query,
                "count": len(payload),
                "tools": payload,
            },
            indent=2,
            ensure_ascii=False,
        )

    async def file_read(
        args: dict[str, Any],
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        path_arg = str(args.get("path", "") or "").strip()
        if not path_arg:
            return "Error: 'path' is required."

        target = _resolve_path_for_read(
            path_arg,
            omicsclaw_dir=root,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        if target is None:
            return f"Error: file not found or outside allowed roots: {path_arg}"
        if not target.is_file():
            return f"Error: target is not a file: {target}"

        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        total_lines = len(lines)
        start_line = _bounded_int(args.get("start_line"), default=1, minimum=1)
        end_line = _bounded_int(args.get("end_line"), default=total_lines or 1, minimum=start_line)
        max_chars = _bounded_int(args.get("max_chars"), default=_DEFAULT_FILE_READ_MAX_CHARS, minimum=200, maximum=100000)

        selected = lines[start_line - 1 : end_line]
        rendered_lines = [
            f"{index}: {line}"
            for index, line in enumerate(selected, start=start_line)
        ]
        body = "\n".join(rendered_lines)
        truncated = False
        if len(body) > max_chars:
            body = body[:max_chars].rstrip() + "\n... [truncated]"
            truncated = True
        header = [
            f"File: {target}",
            f"Lines: {start_line}-{min(end_line, total_lines or end_line)} of {total_lines}",
        ]
        if truncated:
            header.append(f"Truncated to {max_chars} characters")
        return "\n".join(header + ["", body])

    async def glob_files(
        args: dict[str, Any],
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        pattern = str(args.get("pattern", "") or "").strip()
        if not pattern:
            return "Error: 'pattern' is required."
        try:
            root_dir = _resolve_search_root(
                args.get("root"),
                omicsclaw_dir=root,
                surface=surface,
                workspace=workspace,
                pipeline_workspace=pipeline_workspace,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        limit = _bounded_int(args.get("limit"), default=_DEFAULT_GLOB_LIMIT, minimum=1, maximum=5000)
        matches: list[str] = []
        for path in sorted(root_dir.glob(pattern)):
            if path.is_dir():
                continue
            matches.append(str(path))
            if len(matches) >= limit:
                break
        return json.dumps(
            {
                "root": str(root_dir),
                "pattern": pattern,
                "count": len(matches),
                "matches": matches,
            },
            indent=2,
            ensure_ascii=False,
        )

    async def grep_files(
        args: dict[str, Any],
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        pattern = str(args.get("pattern", "") or "").strip()
        if not pattern:
            return "Error: 'pattern' is required."

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"Error: invalid regular expression: {exc}"
        try:
            root_dir = _resolve_search_root(
                args.get("root"),
                omicsclaw_dir=root,
                surface=surface,
                workspace=workspace,
                pipeline_workspace=pipeline_workspace,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        glob_pattern = str(args.get("glob", "") or "").strip() or "**/*"
        max_matches = _bounded_int(args.get("max_matches"), default=_DEFAULT_GREP_LIMIT, minimum=1, maximum=1000)

        matches: list[dict[str, Any]] = []
        for path in sorted(root_dir.glob(glob_pattern)):
            if not path.is_file():
                continue
            try:
                if path.stat().st_size > _MAX_GREP_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for line_no, line in enumerate(text.splitlines(), start=1):
                if not regex.search(line):
                    continue
                matches.append(
                    {
                        "path": str(path),
                        "line": line_no,
                        "text": line,
                    }
                )
                if len(matches) >= max_matches:
                    return json.dumps(
                        {
                            "root": str(root_dir),
                            "pattern": pattern,
                            "glob": glob_pattern,
                            "count": len(matches),
                            "truncated": True,
                            "matches": matches,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )

        return json.dumps(
            {
                "root": str(root_dir),
                "pattern": pattern,
                "glob": glob_pattern,
                "count": len(matches),
                "truncated": False,
                "matches": matches,
            },
            indent=2,
            ensure_ascii=False,
        )

    async def file_write(
        args: dict[str, Any],
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        path_arg = str(args.get("path", "") or "").strip()
        if not path_arg:
            return "Error: 'path' is required."

        content = str(args.get("content", ""))
        target = _resolve_path_for_write(
            path_arg,
            omicsclaw_dir=root,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        if target is None:
            return f"Error: cannot write outside allowed roots: {path_arg}"

        if bool(args.get("create_dirs", True)):
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            return f"Error: parent directory does not exist: {target.parent}"

        target.write_text(content, encoding="utf-8")
        return f"Wrote file: {target}"

    async def file_edit(
        args: dict[str, Any],
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        path_arg = str(args.get("path", "") or "").strip()
        old_text = str(args.get("old_text", ""))
        new_text = str(args.get("new_text", ""))
        replace_all = bool(args.get("replace_all", False))

        if not path_arg:
            return "Error: 'path' is required."
        if not old_text:
            return "Error: 'old_text' is required."

        target = _resolve_path_for_write(
            path_arg,
            omicsclaw_dir=root,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        if target is None or not target.exists() or not target.is_file():
            return f"Error: file not found or outside allowed roots: {path_arg}"

        content = target.read_text(encoding="utf-8", errors="replace")
        occurrences = content.count(old_text)
        if occurrences == 0:
            return f"Error: text to replace was not found in {target}"
        if occurrences > 1 and not replace_all:
            return (
                f"Error: found {occurrences} matches in {target}. "
                "Set 'replace_all' to true or provide a more specific 'old_text'."
            )

        updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        target.write_text(updated, encoding="utf-8")
        replaced_count = occurrences if replace_all else 1
        return f"Edited file: {target} (replaced {replaced_count} occurrence{'s' if replaced_count != 1 else ''})"

    async def task_create(
        args: dict[str, Any],
        session_id: str = "",
        chat_id: str = "",
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        title = str(args.get("title", "") or "").strip()
        if not title:
            return "Error: 'title' is required."

        path, store = _load_engineering_task_store(
            runtime_state_root,
            session_id=session_id,
            chat_id=chat_id,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        task_id = _normalize_task_id(args.get("task_id")) or _allocate_task_id(title, store.task_ids())
        task = TaskRecord(
            id=task_id,
            title=title,
            description=str(args.get("description", "") or "").strip(),
            owner=str(args.get("owner", "") or "").strip(),
            dependencies=_normalize_string_list(args.get("dependencies")),
        )
        try:
            store.add_task(task)
        except ValueError as exc:
            return f"Error: {exc}"
        store.save(path)
        return _json_payload(
            {
                "store_path": str(path),
                "task": task.to_dict(),
            }
        )

    async def task_get(
        args: dict[str, Any],
        session_id: str = "",
        chat_id: str = "",
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        task_id = str(args.get("task_id", "") or "").strip()
        if not task_id:
            return "Error: 'task_id' is required."

        path, store = _load_engineering_task_store(
            runtime_state_root,
            session_id=session_id,
            chat_id=chat_id,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        task = store.get(task_id)
        if task is None:
            return _json_payload({"store_path": str(path), "error": f"Unknown task id: {task_id}"})
        return _json_payload({"store_path": str(path), "task": task.to_dict()})

    async def task_list(
        args: dict[str, Any],
        session_id: str = "",
        chat_id: str = "",
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        path, store = _load_engineering_task_store(
            runtime_state_root,
            session_id=session_id,
            chat_id=chat_id,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        status = str(args.get("status", "") or "").strip()
        if status and status not in _TASK_STATUSES:
            return f"Error: unsupported status '{status}'."
        tasks = [
            task.to_dict()
            for task in store.tasks
            if not status or task.status == status
        ]
        return _json_payload(
            {
                "store_path": str(path),
                "kind": store.kind,
                "metadata": dict(store.metadata),
                "tasks": tasks,
            }
        )

    async def task_update(
        args: dict[str, Any],
        session_id: str = "",
        chat_id: str = "",
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        task_id = str(args.get("task_id", "") or "").strip()
        if not task_id:
            return "Error: 'task_id' is required."

        path, store = _load_engineering_task_store(
            runtime_state_root,
            session_id=session_id,
            chat_id=chat_id,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        task = store.get(task_id)
        if task is None:
            return _json_payload({"store_path": str(path), "error": f"Unknown task id: {task_id}"})

        status = str(args.get("status", "") or "").strip()
        if status:
            if status not in _TASK_STATUSES:
                return f"Error: unsupported status '{status}'."
            store.set_task_status(
                task_id,
                status,
                summary=str(args.get("summary", "") or "").strip(),
                artifact_ref=str(args.get("artifact_ref", "") or "").strip(),
                owner=str(args.get("owner", "") or "").strip(),
            )
            task = store.require(task_id)
        else:
            title = str(args.get("title", "") or "").strip()
            description = str(args.get("description", "") or "").strip()
            owner = str(args.get("owner", "") or "").strip()
            if title:
                task.title = title
            if description:
                task.description = description
            if owner:
                task.owner = owner
            summary = str(args.get("summary", "") or "").strip()
            artifact_ref = str(args.get("artifact_ref", "") or "").strip()
            if summary:
                task.metadata["summary"] = summary
            if artifact_ref and artifact_ref not in task.artifact_refs:
                task.artifact_refs.append(artifact_ref)
            task.touch()

        store.save(path)
        return _json_payload({"store_path": str(path), "task": task.to_dict()})

    async def todo_write(
        args: dict[str, Any],
        session_id: str = "",
        chat_id: str = "",
        surface: str = "",
        workspace: str = "",
        pipeline_workspace: str = "",
    ) -> str:
        items = args.get("items")
        if not isinstance(items, list):
            return "Error: 'items' must be an array."

        path, store = _load_engineering_task_store(
            runtime_state_root,
            session_id=session_id,
            chat_id=chat_id,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
        )
        store.kind = str(args.get("kind", "") or "").strip() or "engineering_plan"
        store.tasks = []
        seen_ids: set[str] = set()
        for index, raw_item in enumerate(items, start=1):
            if not isinstance(raw_item, dict):
                return f"Error: todo item #{index} must be an object."
            title = str(raw_item.get("title", "") or "").strip()
            if not title:
                return f"Error: todo item #{index} is missing 'title'."
            task_id = _normalize_task_id(raw_item.get("id")) or _allocate_task_id(title, seen_ids.union(set(store.task_ids())))
            if task_id in seen_ids:
                return f"Error: duplicate todo task id '{task_id}'."
            status = str(raw_item.get("status", TASK_STATUS_PENDING) or TASK_STATUS_PENDING).strip()
            if status not in _TASK_STATUSES:
                return f"Error: unsupported status '{status}' for todo item '{title}'."
            task = TaskRecord(
                id=task_id,
                title=title,
                description=str(raw_item.get("description", "") or "").strip(),
                status=status,
                owner=str(raw_item.get("owner", "") or "").strip(),
                dependencies=_normalize_string_list(raw_item.get("dependencies")),
                artifact_refs=_normalize_string_list(raw_item.get("artifact_refs")),
            )
            store.add_task(task)
            seen_ids.add(task_id)

        store.save(path)
        return _json_payload(
            {
                "store_path": str(path),
                "kind": store.kind,
                "task_count": len(store.tasks),
                "tasks": [task.to_dict() for task in store.tasks],
            }
        )

    async def web_fetch(args: dict[str, Any]) -> str:
        url = str(args.get("url", "") or "").strip()
        if not url:
            return "Error: 'url' is required."
        if not url.startswith(("http://", "https://")):
            return f"Error: unsupported url '{url}'."

        try:
            from omicsclaw.research.web_search import _fetch_webpage
        except ImportError as exc:
            return f"Error: web fetch dependencies unavailable: {exc}"

        max_chars = _bounded_int(args.get("max_chars"), default=_DEFAULT_WEB_MAX_CHARS, minimum=20, maximum=100000)
        content = await _fetch_webpage(url)
        if len(content) > max_chars:
            content = content[:max_chars].rstrip() + "\n\n... [truncated]"
        return f"URL: {url}\n\n{content}"

    return {
        "tool_search": tool_search,
        "file_read": file_read,
        "glob_files": glob_files,
        "grep_files": grep_files,
        "file_write": file_write,
        "file_edit": file_edit,
        "task_create": task_create,
        "task_get": task_get,
        "task_list": task_list,
        "task_update": task_update,
        "todo_write": todo_write,
        "web_fetch": web_fetch,
    }


def _resolve_state_root(state_root: str | Path | None) -> Path:
    if state_root is not None:
        root = Path(state_root).expanduser().resolve()
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else Path.home() / ".config"
        root = (base / "omicsclaw" / "runtime").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _tokenize(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_TOKEN_RE.findall(query.lower())))


def _tool_match_score(spec: ToolSpec, *, query: str, tokens: tuple[str, ...]) -> int:
    if not query:
        return 1

    haystacks = [
        spec.name.lower(),
        spec.description.lower(),
        " ".join(spec.policy_tags).lower(),
    ]
    score = 0
    if query in haystacks[0]:
        score += 12
    if query in haystacks[1]:
        score += 8
    if query in haystacks[2]:
        score += 6
    for token in tokens:
        if token in haystacks[0]:
            score += 4
        if token in haystacks[1]:
            score += 2
        if token in haystacks[2]:
            score += 2
    return score


def _tool_summary(spec: ToolSpec, *, include_schema: bool) -> dict[str, Any]:
    payload = {
        "name": spec.name,
        "description": spec.description,
        "risk_level": spec.risk_level,
        "read_only": spec.read_only,
        "writes_workspace": spec.writes_workspace,
        "writes_config": spec.writes_config,
        "touches_network": spec.touches_network,
        "policy_tags": list(spec.policy_tags),
    }
    if include_schema:
        payload["parameters"] = sorted(spec.parameters.get("properties", {}).keys())
    return payload


def _json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        items.append(text)
        seen.add(text)
    return items


def _normalize_task_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _SAFE_NAME_RE.sub("-", text).strip("-")


def _allocate_task_id(title: str, existing_ids: Iterable[str]) -> str:
    base = _normalize_task_id(title.lower()) or "task"
    used = set(existing_ids)
    if base not in used:
        return base
    index = 2
    while True:
        candidate = f"{base}-{index}"
        if candidate not in used:
            return candidate
        index += 1


def _load_engineering_task_store(
    state_root: Path,
    *,
    session_id: str,
    chat_id: str,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
) -> tuple[Path, TaskStore]:
    session_token = _normalize_task_id(session_id or f"{surface or 'surface'}-{chat_id or 'default'}") or "default"
    store_dir = state_root / "engineering_tasks"
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / f"{session_token}.json"
    store = TaskStore.load(path) or TaskStore(kind="engineering_plan")
    store.metadata["session_id"] = session_id
    store.metadata["chat_id"] = chat_id
    store.metadata["surface"] = surface
    active_workspace = str(pipeline_workspace or workspace or "").strip()
    if active_workspace:
        store.metadata["workspace"] = active_workspace
    elif "workspace" in store.metadata:
        store.metadata.pop("workspace", None)
    return path, store


def _resolve_search_root(
    root_arg: Any,
    *,
    omicsclaw_dir: Path,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
) -> Path:
    root_text = str(root_arg or "").strip()
    if root_text:
        target = _resolve_path_for_read(
            root_text,
            omicsclaw_dir=omicsclaw_dir,
            surface=surface,
            workspace=workspace,
            pipeline_workspace=pipeline_workspace,
            expect_dir=True,
        )
        if target is None:
            raise ValueError(f"Search root not found or outside allowed roots: {root_text}")
        return target
    return _preferred_read_root(
        omicsclaw_dir=omicsclaw_dir,
        surface=surface,
        workspace=workspace,
        pipeline_workspace=pipeline_workspace,
    )


def _preferred_read_root(
    *,
    omicsclaw_dir: Path,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
) -> Path:
    explicit_roots = _explicit_roots(workspace=workspace, pipeline_workspace=pipeline_workspace)
    if explicit_roots:
        return explicit_roots[0]
    if str(surface or "").strip().lower() == "interactive":
        return omicsclaw_dir
    fallback = omicsclaw_dir / "output" / "engineering"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _read_roots(
    *,
    omicsclaw_dir: Path,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
) -> list[Path]:
    roots = _explicit_roots(workspace=workspace, pipeline_workspace=pipeline_workspace)
    data_roots = [
        omicsclaw_dir / "data",
        omicsclaw_dir / "examples",
        omicsclaw_dir / "output",
    ]
    if str(surface or "").strip().lower() == "interactive":
        roots.append(omicsclaw_dir)
    roots.extend(data_roots)

    extra = os.environ.get("OMICSCLAW_DATA_DIRS", "").strip()
    if extra:
        for raw_item in extra.split(","):
            text = raw_item.strip()
            if not text:
                continue
            path = Path(text).expanduser()
            if path.is_absolute():
                roots.append(path.resolve())

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


def _write_roots(
    *,
    omicsclaw_dir: Path,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
) -> list[Path]:
    roots = _explicit_roots(workspace=workspace, pipeline_workspace=pipeline_workspace)
    if roots:
        return roots
    if str(surface or "").strip().lower() == "interactive":
        return [omicsclaw_dir]
    fallback = (omicsclaw_dir / "output" / "engineering").resolve()
    fallback.mkdir(parents=True, exist_ok=True)
    return [fallback]


def _explicit_roots(*, workspace: str, pipeline_workspace: str) -> list[Path]:
    roots: list[Path] = []
    for raw in (pipeline_workspace, workspace):
        text = str(raw or "").strip()
        if not text:
            continue
        roots.append(Path(text).expanduser().resolve())
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        token = str(root)
        if token in seen:
            continue
        unique.append(root)
        seen.add(token)
    return unique


def _resolve_path_for_read(
    path_arg: str,
    *,
    omicsclaw_dir: Path,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
    expect_dir: bool = False,
) -> Path | None:
    raw_path = Path(path_arg).expanduser()
    allowed_roots = _read_roots(
        omicsclaw_dir=omicsclaw_dir,
        surface=surface,
        workspace=workspace,
        pipeline_workspace=pipeline_workspace,
    )
    if raw_path.is_absolute():
        resolved = raw_path.resolve()
        if _path_allowed(resolved, allowed_roots) and resolved.exists():
            if expect_dir and resolved.is_dir():
                return resolved
            if not expect_dir and resolved.is_file():
                return resolved
        return None

    for root in allowed_roots:
        candidate = (root / raw_path).resolve()
        if not _path_allowed(candidate, allowed_roots) or not candidate.exists():
            continue
        if expect_dir and candidate.is_dir():
            return candidate
        if not expect_dir and candidate.is_file():
            return candidate
    return None


def _resolve_path_for_write(
    path_arg: str,
    *,
    omicsclaw_dir: Path,
    surface: str,
    workspace: str,
    pipeline_workspace: str,
) -> Path | None:
    raw_path = Path(path_arg).expanduser()
    allowed_roots = _write_roots(
        omicsclaw_dir=omicsclaw_dir,
        surface=surface,
        workspace=workspace,
        pipeline_workspace=pipeline_workspace,
    )
    if raw_path.is_absolute():
        candidate = raw_path.resolve()
        return candidate if _path_allowed(candidate, allowed_roots) else None

    base = allowed_roots[0]
    candidate = (base / raw_path).resolve()
    return candidate if _path_allowed(candidate, allowed_roots) else None


def _path_allowed(candidate: Path, allowed_roots: Iterable[Path]) -> bool:
    for root in allowed_roots:
        try:
            candidate.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int | None = None,
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _load_mcp_servers() -> list[dict[str, Any]]:
    try:
        import yaml
    except ImportError:
        return []

    config_path = _mcp_config_path()
    if not config_path.is_file():
        return []
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []

    servers: list[dict[str, Any]] = []
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        payload: dict[str, Any] = {
            "name": str(name),
            "transport": str(entry.get("transport", "") or ""),
        }
        if "command" in entry:
            payload["command"] = str(entry.get("command", "") or "")
        if "args" in entry and isinstance(entry.get("args"), list):
            payload["args"] = [str(item) for item in entry.get("args", [])]
        if "url" in entry:
            payload["url"] = str(entry.get("url", "") or "")
        if "tools" in entry and isinstance(entry.get("tools"), list):
            payload["tools"] = [str(item) for item in entry.get("tools", [])]
        if "env" in entry and isinstance(entry.get("env"), dict):
            payload["env_keys"] = sorted(str(key) for key in entry.get("env", {}).keys())
        servers.append(payload)
    servers.sort(key=lambda item: item["name"])
    return servers


def _mcp_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return (base / "omicsclaw" / "mcp.yaml").resolve()


__all__ = [
    "build_engineering_tool_executors",
    "build_engineering_tool_specs",
]
