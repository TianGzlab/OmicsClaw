# Architecture

## Overview

OmicsClaw is a local-first, skill-based multi-omics platform with three main execution surfaces:

- CLI commands via `oc` / `python omicsclaw.py`
- Interactive terminal sessions via `oc interactive` or `oc tui`
- Messaging bots backed by the shared `bot/core.py` runtime

The current repository combines:

- Dynamic skill discovery from `skills/`
- A shared prompt/context runtime in `omicsclaw/runtime/`
- Persistent graph memory plus workspace-scoped memory
- Extension packs for prompt rules, output styles, workflows, and tool hooks
- MCP integration for external tool servers in interactive sessions

The skill catalog is discovered dynamically. In the current tree, `registry.load_all()` finds 140+ skills across spatial, single-cell, genomics, proteomics, metabolomics, bulk RNA-seq, and orchestrator domains. Use `oc list` for the current live catalog.

## End-to-End Flow

### High-level request flow

```text
User request
    |
    +--> CLI command surface (`oc run`, `oc list`, `oc interactive`, `oc tui`)
    +--> Interactive CLI / TUI
    +--> Messaging bot channels
            |
            v
     Shared runtime entrypoints
            |
            v
     Context assembly + system prompt construction
            |
            v
     LLM query engine
            |
            v
     Tool execution pipeline
            |
            +--> OmicsClaw skill execution
            +--> Engineering / inspection tools
            +--> Memory tools
            +--> Web / MCP / routing helpers
            |
            v
     Transcript + tool result persistence
            |
            v
     User-facing reply + saved artifacts
```

### Analysis execution flow

```text
Input data / user intent
    -> capability routing or exact skill selection
    -> skill execution (`omicsclaw` tool or direct CLI)
    -> reports / figures / tables / processed datasets
    -> session transcript, memory, and workspace artifacts
```

## Repository Structure

```text
OmicsClaw/
|-- omicsclaw.py                 # Repository-root CLI launcher
|-- omicsclaw/
|   |-- cli.py                   # Package entrypoint for `oc`
|   |-- agents/                  # Agent and pipeline helpers
|   |-- common/                  # Shared utilities, manifests, reports
|   |-- core/                    # Registry, lazy metadata, dependency helpers
|   |-- execution/               # Autonomous and notebook-style execution helpers
|   |-- extensions/              # Extension manifests, loaders, runtime activation
|   |-- interactive/             # CLI/TUI session surfaces and slash commands
|   |-- knowledge/               # Know-how indexing and scientific constraints
|   |-- loaders/                 # File/domain detection helpers
|   |-- memory/                  # Graph memory, scoped memory, API server
|   |-- research/                # Research and web-guided workflows
|   |-- routing/                 # Capability routing and orchestration
|   `-- runtime/                 # Prompt, context, query, policy, tool runtime
|-- skills/                      # Domain-organized analysis skills
|-- bot/                         # Messaging channels + shared chat runtime
|-- frontend/                    # Memory dashboard (React/Vite)
|-- docs/                        # Project documentation
|-- examples/                    # Demo data
|-- templates/                   # Skill and output templates
`-- tests/                       # Runtime, interactive, memory, and skill tests
```

## Skill System

Each OmicsClaw skill is a reusable analysis unit with:

- `SKILL.md` metadata and method contract
- A Python implementation with a stable CLI shape
- Optional tests and demo data

Skills are discovered from `skills/` and indexed through `omicsclaw.core.registry`. Shared domain utilities live under per-domain `_lib/` packages and are not treated as user-callable skills.

Common skill characteristics:

- Standard user inputs such as `--input`, `--output`, and `--demo`
- Reuse of domain-specific helpers under `skills/<domain>/_lib/`
- Standard outputs such as `report.md`, `result.json`, figures, tables, and processed datasets where applicable
- Method and parameter hints surfaced from `SKILL.md` metadata into routing and prompt context

## Execution Surfaces

### CLI

The repository-root `omicsclaw.py` remains the canonical launcher. The package script `oc` resolves and delegates to it through `omicsclaw/cli.py`.

Important CLI entrypoints:

- `oc list`
- `oc run <skill> ...`
- `oc interactive`
- `oc tui`
- `oc app-server`
- `oc mcp list|add|remove|config`
- `oc memory-server`
- `oc onboard` for project `.env` bootstrap across LLM, runtime, memory, and bot-channel configuration

### Interactive CLI / TUI

Interactive sessions are implemented in `omicsclaw/interactive/` and share the same backend loop:

- `interactive.py` provides the prompt_toolkit-based CLI surface
- `tui.py` provides the Textual full-screen TUI
- `_session.py` persists sessions to SQLite
- `_mcp.py` manages MCP server configuration and loading
- `_memory_command_support.py` manages scoped-memory commands
- `_plan_mode_support.py` and `_pipeline_support.py` manage plan and workspace-oriented workflows

Interactive sessions carry explicit workspace state:

- `workspace_dir` for the active session workspace
- `pipeline_workspace` for structured research / pipeline workspaces
- `plan_context` and task state when plan mode or pipeline work is active
- scoped-memory scope selection for local project or dataset heuristics

### Bots

Messaging channels in `bot/channels/` share `bot/core.py`, which provides:

- The LLM tool loop
- Runtime integration with `omicsclaw/runtime/`
- audit logging
- policy state propagation
- skill execution and artifact delivery

The interactive surfaces and bots converge on the same runtime concepts even though their UX differs.

## Runtime Stack

The shared runtime lives in `omicsclaw/runtime/` and is organized into four major layers:

1. Context assembly
2. Query and compaction
3. Tool orchestration and policy
4. Result persistence and transcript replay

### Context assembly

`assemble_chat_context()` in `omicsclaw/runtime/context_assembler.py` prepares the prompt-facing state for each turn. It now performs concurrent preparation of multiple context sources, including:

- session memory
- capability resolution
- prompt-pack rules
- scoped-memory recall
- skill-context prefetch

The assembled prompt is built through ordered context layers from `omicsclaw/runtime/context_layers/`.

Typical system-context layers include:

- base persona from `SOUL.md`
- output format / output style profile
- role guardrails
- execution discipline
- skill contract
- user memory
- on-demand prefetched skill context
- deterministic capability assessment
- scientific know-how constraints
- workspace context
- active MCP instructions

Some layers are injected only when relevant:

- `skill_context` is added only when a concrete skill or strong capability hit is present
- MCP instructions are injected only for active prompt-worthy MCP servers
- workspace context can be placed in the system prompt or message context depending on the request

### Prompt discipline

The prompt layers encode operational rules for OmicsClaw's current design:

- read existing context before changing code or rerunning analysis
- prefer existing skills and workspace artifacts over ad hoc scripts
- avoid speculative abstractions and unnecessary new files
- do not claim tests or outputs were observed unless they actually were
- do not silently switch methods or datasets after a failure

This makes the interactive and bot assistants behave more like a controlled AI engineer / analyst and less like a free-form chat assistant.

## Context Economics

OmicsClaw now includes explicit context-budget controls in the runtime rather than relying on raw transcript growth.

### Multi-stage compaction

`omicsclaw/runtime/context_compaction.py` implements five compaction stages:

1. `snip_compact`
   - truncates oversized older messages and oversized historical tool arguments
2. `micro_compact`
   - replaces older large tool outputs with compact references to persisted tool-result files
3. `context_collapse`
   - collapses older inactive transcript regions into replay summaries
4. `auto_compact`
   - applies a more aggressive collapse when prompt budget pressure is higher
5. `reactive_compact`
   - emergency compaction used after a prompt-too-long API error

The query engine applies light compaction first and escalates only when the prompt is still too large.

### Reactive compact fallback

`omicsclaw/runtime/query_engine.py` tracks `has_attempted_reactive_compact` so a turn only performs one emergency retry after a prompt-too-long response from the model API.

### Token budget continuation

`omicsclaw/runtime/token_budget.py` implements a per-turn token budget tracker. When a budget is configured, the runtime can inject a continuation nudge telling the model to keep working on the same task instead of stopping early. It also stops nudging once progress meaningfully slows down.

### Tool-result budget

Large tool outputs are not kept inline indefinitely.

- `ToolResultStore` persists oversized tool outputs to disk
- the transcript only keeps a compact reference with preview text and the persisted file path
- transcript summaries can replay compacted references without reinflating the entire original output

This is the main mechanism OmicsClaw uses for "tool result budget" management.

## Tool Execution Pipeline

The tool runtime is centered on:

- `tool_spec.py`
- `tool_registry.py`
- `tool_orchestration.py`
- `policy.py`
- `tool_result_store.py`

Every tool call runs through a shared execution pipeline before the underlying executor is invoked.

### Execution stages

For each tool request, OmicsClaw performs:

1. Tool resolution
   - identify the tool spec and executor
2. MCP metadata extraction
   - tag MCP-backed tools and extract server/tool identity
3. Input schema validation
   - validate arguments against the declared schema
4. Tool-level input validation
   - run any tool-specific validator and normalize arguments if needed
5. Speculative classification
   - start a classifier pass in parallel with later steps
6. Pre-tool hooks
   - allow extensions or runtime hooks to inspect, block, or rewrite arguments
7. Policy resolution
   - combine static policy, runtime context, and classifier output
8. Tool execution
   - invoke the executor only if policy allows it
9. Post-tool hooks
   - rewrite or annotate successful outputs
10. Failure hooks
   - run failure handlers when execution raises
11. Trace capture
   - store timings, policy decisions, hook records, and validation state
12. Result persistence
   - store the result through `ToolResultStore` and append a transcript entry

### Concurrency model

`execute_tool_requests()` supports safe batching:

- read-only, concurrency-safe tools may run concurrently
- any write-capable or non-concurrency-safe tool acts as a barrier
- output ordering remains stable

This gives OmicsClaw a Claude-Code-style structured execution path while staying aligned with the project's existing Python runtime.

## Memory Model

OmicsClaw uses two distinct but complementary memory layers.

### 1. Graph memory

Implemented under `omicsclaw/memory/`, graph memory stores durable cross-session context such as:

- session summaries
- user preferences
- confirmed analysis context
- durable metadata and relationships

This layer is backed by SQLite or PostgreSQL and exposed through `MemoryClient` plus an optional REST API server.

### 2. Scoped memory

Scoped memory is workspace-local memory stored under `.omicsclaw/scoped_memory` and indexed separately from the graph store. It is intended for:

- project-specific conventions
- dataset-local caveats
- lab policy notes
- reusable run heuristics tied to a workspace or pipeline

Scoped memory can be recalled into prompt context during interactive or pipeline work without polluting global memory.

See [MEMORY_SYSTEM.md](./MEMORY_SYSTEM.md) for full details.

## Workspace and Pipeline Model

Interactive and research-oriented work is workspace-aware.

Key concepts:

- `daemon` mode keeps using a persistent workspace
- `run` mode creates an isolated per-session workspace
- `pipeline_workspace` tracks structured research / plan artifacts
- plan and task state can be reflected back into prompt context
- the assistant is instructed to treat the active workspace as the source of truth for `plan.md`, reports, and run artifacts

This reduces accidental drift between chat state and files on disk.

## MCP and Extensions

### MCP integration

Interactive sessions can load MCP server definitions from the OmicsClaw config. Prompt injection is budget-aware:

- only active prompt-worthy MCP servers are injected into the prompt
- inactive or unavailable MCP servers do not consume prompt budget
- MCP instructions tell the model to use only tools actually present in the active tool list

### Extension runtime

The extension system under `omicsclaw/extensions/` supports activation surfaces such as:

- prompt packs
- output style packs
- workflow packs
- agent packs
- hook packs
- tool-execution hook packs

Prompt packs can inject additional context during prompt assembly, while tool-execution hook packs can alter the tool pipeline before or after execution.

## Outputs and Artifacts

Typical OmicsClaw outputs include:

- `report.md`
- `result.json`
- figures and tables
- processed datasets such as `.h5ad`
- pipeline workspace artifacts such as plans, task state, and research outputs

The runtime is designed to keep large transient tool output out of the prompt while preserving durable artifacts on disk.

## Testing and Verification

The project includes tests for:

- runtime prompt assembly and compaction
- token-budget behavior
- query-engine orchestration
- tool execution hooks and policy
- interactive session behavior
- memory and scoped-memory utilities
- extension runtime activation
- skill demos and domain-specific outputs

Useful commands:

```bash
python -m pytest -v
python -m pytest tests/test_context_assembler.py -v
python -m pytest tests/test_query_engine.py -v
python -m pytest tests/test_interactive_loop.py -v
```

## Summary

OmicsClaw is no longer just a collection of skills behind a CLI. The current architecture is a layered runtime with:

- dynamic skill routing
- workspace-aware interactive execution
- explicit prompt and context-budget management
- a structured tool execution pipeline
- graph memory plus scoped memory
- extension and MCP integration

That combination is what allows the same codebase to support reproducible omics analysis, interactive AI-assisted workflows, and bot surfaces without maintaining separate reasoning stacks for each surface.
