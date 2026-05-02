# Memory System

OmicsClaw uses two complementary memory layers:

1. Graph memory for durable cross-session context
2. Scoped memory for workspace-local project and dataset knowledge

Together they let the assistant keep useful context without turning every chat turn into a full replay of the workspace.

## Why OmicsClaw Has Two Memory Layers

Different kinds of context have different lifetimes.

### Graph memory is for durable context

Use graph memory when the information should survive across sessions and surfaces, for example:

- user language or reporting preferences
- stable project context
- confirmed analysis lineage
- durable metadata about prior runs

### Scoped memory is for local workspace context

Use scoped memory when the information is tied to a project, dataset, lab, or pipeline workspace, for example:

- project-specific QC thresholds
- local dataset caveats
- workspace conventions
- lab policy notes
- reusable heuristics for a single analysis directory

This split prevents short-lived workspace notes from polluting global memory while still making them retrievable during active work.

## Layer 1: Graph Memory

Graph memory lives under `omicsclaw/memory/` and is backed by SQLite or PostgreSQL through SQLAlchemy.

It models durable entities as nodes and edges rooted at `ROOT_NODE_UUID`.

Typical URI families include:

- `session://` for conversation or workflow sessions
- `dataset://` for durable dataset metadata
- `preference://` for user preferences
- `insight://` for confirmed biological or analytical insights

This allows OmicsClaw to preserve relationships such as:

- which datasets were used in a session
- how a result was derived from earlier preprocessing
- which user preferences should be reused in later turns

### What graph memory stores

Graph memory is intended for:

- metadata
- preferences
- analysis parameters
- durable summaries
- relationships between analysis entities

It is not intended to store:

- raw omics matrices
- bulk binary artifacts
- arbitrary temporary logs
- secrets or API keys
- unconfirmed biological claims

## Layer 2: Scoped Memory

Scoped memory is a workspace-local markdown-based memory layer stored under:

```text
.omicsclaw/scoped_memory
```

Each scoped-memory record carries normalized metadata such as:

- `scope` such as `project`, `dataset`, or `lab_policy`
- `freshness`
- title and summary
- optional dataset references

This layer is especially useful for interactive sessions and pipeline workspaces where the assistant needs to remember local conventions without elevating them to global memory.

### Typical scoped-memory use cases

- "This PBMC dataset uses doublet filtering threshold 0.08 in this workspace."
- "Use Harmony before differential analysis in this project."
- "Lab policy: never overwrite final reports under `output/final/`."

## Runtime Integration

Memory is not just stored; it is also injected back into the reasoning loop.

### Session memory restoration

During chat-context assembly, OmicsClaw can load session memory for the active `user_id/platform/chat_id` tuple and inject it as prompt memory context.

### Scoped-memory recall

When a workspace or pipeline workspace is active, OmicsClaw can recall matching scoped-memory records and inject a summarized `## Scoped Memory` block into the prompt.

### Concurrent context preparation

The runtime currently prepares several context sources concurrently during prompt assembly, including:

- session memory
- capability resolution
- prompt-pack context
- scoped-memory recall
- prefetched skill context

This keeps memory useful without making prompt assembly fully serial.

## What Problems Memory Solves

| Without memory | With OmicsClaw memory |
| --- | --- |
| Repeating the same project background every turn | Session memory restores durable context |
| Losing project-specific caveats between commands | Scoped memory keeps workspace-local heuristics |
| Losing user output preferences | Preferences can be remembered and reused |
| No lineage between earlier and later analysis steps | Graph memory preserves relationships |
| Large workspaces forcing all context into prompt text | Memory keeps durable state outside raw transcript history |

## Managing Memory via Dashboard

OmicsClaw ships with a memory dashboard frontend plus a REST API backend.

### 1. Start the backend API

The API server runs through the OmicsClaw CLI:

```bash
pip install -e ".[memory]"
oc memory-server
# or: make memory-server
```

By default the API listens on `127.0.0.1:8766`.
If you want to bind it to a non-local interface, you must also set `OMICSCLAW_MEMORY_API_TOKEN`.

### 2. Start the frontend dashboard

```bash
cd frontend
npm install
npm run dev
```

By default the dashboard runs on port `3000`.

Open:

```text
http://localhost:3000
```

You can use it to:

- search memories
- browse graph relationships
- inspect session and dataset nodes
- review stored lineage and metadata

### 3. Remote access via SSH port forwarding

```bash
ssh -N -L 3000:localhost:3000 -L 8766:localhost:8766 <user>@<remote-host>
```

Then open `http://localhost:3000` locally.

## Configuration

Common environment variables:

- `OMICSCLAW_MEMORY_DB_URL`
  - database URL, for example `sqlite+aiosqlite:///bot/data/memory.db`
- `OMICSCLAW_MEMORY_API_TOKEN`
  - bearer token for the REST API when exposing it beyond localhost
  - also protects `/docs` and `/openapi.json` when enabled
- `OMICSCLAW_MEMORY_HOST`
  - optional bind host, default `127.0.0.1`
- `OMICSCLAW_MEMORY_PORT`
  - optional API port override

## Developer Guide

### Using graph memory from Python

```python
import asyncio
from omicsclaw.memory import MemoryClient, SessionContext


async def main():
    client = MemoryClient("sqlite+aiosqlite:///bot/data/memory.db")
    await client.boot()

    context = SessionContext(domain="session", path="user123/analysis_run")

    await client.remember(
        context=context,
        name="pipeline_result",
        content={"status": "success", "artifact": "output/result.h5ad"},
        metadata={"skill": "spatial-preprocess"},
    )

    result = await client.recall(context, "pipeline_result")
    search_results = await client.search(context, query="pipeline_result")
    print(result, search_results)


asyncio.run(main())
```

### Using scoped memory from Python

```python
from omicsclaw.memory import write_scoped_memory

record = write_scoped_memory(
    body="Use Harmony before clustering for this project.",
    title="Project integration default",
    scope="project",
    workspace="/path/to/workspace",
)

print(record.path)
```

### Interactive access

Interactive CLI and TUI sessions expose scoped-memory management through slash-command support in `omicsclaw/interactive/_memory_command_support.py`.

That lets users:

- list local memory
- write new scoped-memory notes
- switch active scope
- inspect the effective memory context for the current session

## Memory Safety Rules

The prompt/runtime guardrails expect memory to be used conservatively.

Good candidates for memory:

- stable preferences
- confirmed scientific or workflow context
- durable project conventions
- verified analysis lineage

Bad candidates for memory:

- secrets
- raw patient identifiers
- temporary file paths copied from transient environments
- one-off failures
- speculative annotations

## Legacy Compatibility

Older bot memory integrations are still supported through compatibility layers such as `CompatMemoryStore`, which map older interfaces into the graph-memory backend.

## Summary

OmicsClaw's memory model is intentionally layered:

- graph memory for durable, cross-session knowledge
- scoped memory for local workspace knowledge

The runtime can selectively recall both layers and inject only the relevant summaries into prompt context, which is what makes the system useful without letting memory dominate prompt budget.
