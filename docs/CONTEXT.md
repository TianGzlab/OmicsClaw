# OmicsClaw Memory System

The graph-backed agent memory at `omicsclaw/memory/`. It records what each user (or workspace) has told OmicsClaw — sessions, preferences, dataset / analysis / insight lineage — and replays that context across runs and surfaces (CLI, Desktop, Telegram, Feishu) so the agent acts with continuity.

> **Scope.** This file currently documents the Memory System only. If the Skills system, Bot orchestration, or other subsystems acquire enough domain vocabulary to warrant their own CONTEXT, split via a top-level `CONTEXT-MAP.md` per [CONTEXT-FORMAT.md §"Single vs multi-context repos"].

## Language

### Identity & Addressing

**Memory URI**: A `domain://path` string that names a memory's logical location, independent of any row id.
_Avoid_: "memory key", "memory id" (the latter is `Memory.id` — a row id of one content version)

**Domain**: The top-level segment of a Memory URI — one of `core`, `dataset`, `analysis`, `insight`, `preference`, `project`, `session`.
_Avoid_: "namespace" (orthogonal concept, see below), "category"

**Namespace**: The isolation dimension stored as a column on `paths`, `search_documents`, and `glossary_keywords`. Surfaces inject it: CLI/Desktop = workspace path, Bot = `f"{platform}/{user_id}"`, system = `__shared__`.
_Avoid_: "tenant", "scope" (the `ScopedMemory` filesystem layer is a different concept)

**`__shared__`**: The reserved Namespace whose rows are visible to every other Namespace via Read fallback. Holds `core://agent`, `core://kh/*`, and the system glossary.
_Avoid_: "global", "default", "public"

**Read fallback**: The rule that `recall` and `search` automatically include `__shared__` results when the current Namespace doesn't match. `list_children` deliberately does NOT fall back, to prevent cross-user leakage during subtree traversal.
_Avoid_: "merge", "auto-join"

**Display label**: The human-readable string shown for a Memory in desktop tree and listing UIs. For `dataset`, `preference`, `core`, `session` the label equals the URI's last path segment. For `analysis://*` the URI's last segment is a UUID hex (load-bearing for write-collision avoidance, since `analysis://*` is overwrite-mode), so the label is **derived from `Memory.content`** at the API boundary — `<dataset_basename> · <hh:mm or yyyy-mm-dd hh:mm> · <status>`. The Memory URI remains the canonical identity; the label is purely presentation.
_Avoid_: "title", "name" (overloaded — `name` is also the response field that carries this label)

### Layers & Modules

**Hot path**: The high-frequency operations triggered by every chat turn, skill run, or auto-capture — `upsert`, `recall`, `search`, `list_children`, `get_subtree`.
_Avoid_: "agent path", "fast path"

**Cold path**: The low-frequency, human-triggered operations — orphan inspection, version chain audit, rollback, cascade delete, changeset approval.
_Avoid_: "admin path", "slow path"

**MemoryEngine**: The Hot path engine. Single SQLAlchemy-backed module exposing 7 verbs against `(uri, namespace)` pairs; owns transactions and search reindexing.
_Avoid_: "GraphService" (the legacy 1584-line class this replaces), "MemoryStore", "MemoryService"

**ReviewLog**: The Cold path engine. Reads the same DB but is invoked exclusively by the Desktop app's `/memory/review/*` endpoints and bot cleanup paths.
_Avoid_: "audit log", "history"

**MemoryClient**: The strategy layer between Surfaces and `MemoryEngine`. Decides Namespace via `resolve_namespace()` and version policy via `should_version()`; the only handle Surfaces should hold.
_Avoid_: "MemoryAPI", "MemoryFacade"

**ScopedMemory**: The filesystem-backed memory layer at `.omicsclaw/scoped_memory/` (markdown + frontmatter). Holds workspace-local hints. Live consumers: the `/memory` slash command in `omicsclaw/interactive/` (CLI/TUI) and `omicsclaw/diagnostics.py`. ScopedMemory now coexists with graph memory on the CLI/TUI Surface — markdown notes (`scope`/`list`/`add`/`prune`) stay on disk while `remember`/`recall`/`search` route to `MemoryEngine`.
_Avoid_: "workspace memory" (would clash with `Namespace=workspace`)

### Write Modes

**Versioned upsert**: A write that appends a new `Memory` row and marks the previous as `deprecated=True` with `migrated_to` pointing to the successor. The only write mode `ReviewLog.rollback_to` operates on.
_Avoid_: "history write", "audit write"

**Overwrite upsert**: A write that updates content in-place on a single active `Memory` row, no deprecation chain. The high-volume default.
_Avoid_: "replace", "update"

**Shared write**: The explicit `MemoryClient.remember_shared(uri, content)` call that pins `namespace='__shared__'` regardless of the caller's current Namespace. Used by the system to seed `core://agent`, KH guards, and shared glossary.
_Avoid_: "global write", "broadcast"

### Surfaces

**Surface**: A user-facing entry point. The wired Surfaces that host a graph `MemoryClient` are: Desktop app (`oc app-server` + `app/server.py`), Telegram bot, Feishu bot, and CLI/TUI (`oc interactive` — via `build_graph_memory_command_view`, wired 2026-05).
_Avoid_: "channel" (the Bot subsystem already uses "channel" for Telegram-vs-Feishu)

### Surface namespace defaults

The wired Surfaces derive their Namespace string consistently:

| Surface | Helper | Namespace |
|---|---|---|
| CLI / TUI | `cli_namespace_from_workspace(workspace_dir)` | absolute workspace path (cwd if unset) |
| Desktop | `desktop_namespace()` | `app/<OMICSCLAW_DESKTOP_LAUNCH_ID>` or `app/desktop_user` |
| Telegram / Feishu bot | `CompatMemoryStore` per-session | `f"{platform}/{user_id}"` |
| System / boot scripts | constant | `__shared__` |

The `app/`, `telegram/`, `feishu/` prefixes are structural — they prevent any cross-surface collision with absolute filesystem paths used by the CLI/TUI Surface.

## Relationships

- A **Surface** holds one **MemoryClient** per request context.
- A **MemoryClient** holds one **MemoryEngine** reference and one **Namespace** string.
- A **MemoryClient** routes each `remember()` call to either a **Versioned upsert** or an **Overwrite upsert** based on the **Memory URI**'s domain.
- A **MemoryEngine** writes a `(domain, path)` row partitioned by **Namespace**; **Read fallback** to `__shared__` happens at query time, not at write time.
- A **ReviewLog** reads the same database as **MemoryEngine** but exposes only **Cold path** verbs.
- A **Memory URI** with domain `core` and path starting with `agent` / `kh` / `my_user_default` is **routed to** `__shared__` by `namespace_policy` whenever something writes there. As of 2026-05, only `core://agent` is wired; `core://kh/*` and `core://my_user_default` are reserved prefixes — the bot's KnowHow guards still come from filesystem markdown via `KnowHowInjector`, not from memory. Everything outside those three prefixes lives in the caller's current **Namespace**.
- A **Versioned upsert**'s `migrated_to` chain is the only structure where **ReviewLog.rollback_to** can operate.

## Example dialogue

> **Dev:** "If a Telegram user updates their `qc_threshold` preference, does the old value disappear?"
> **Architect:** "No — `preference://*` is in `VERSIONED_PREFIXES`, so `MemoryClient.remember()` routes to a **Versioned upsert**. The old `Memory` row stays with `deprecated=True`; **ReviewLog.list_version_chain** can find it; the user can roll back via the Desktop review UI."
>
> **Dev:** "Same user processes `pbmc.h5ad` in two different workspaces — what happens?"
> **Architect:** "Two different **Namespaces**, two independent `paths` rows. The same file produces two `dataset://pbmc.h5ad` entries. **Read fallback** doesn't connect them because `dataset://*` is per-Namespace, not shared."
>
> **Dev:** "I bind the keyword 'TIL' to a shared OmicsClaw concept node — do other users see it?"
> **Architect:** "Only if you call `add_glossary_shared('TIL', node)`. Plain `add_glossary` writes the binding under your current **Namespace**. **Read fallback** surfaces shared bindings to everyone, but your private one stays private."

## Resolved-by-default decisions

Decisions that the refactor PRs (#125–#132) chose by sensible default rather than explicit RFC:

- **One database, many Namespaces** — `OMICSCLAW_MEMORY_DB_URL` selects a single SQLite/Postgres database; Namespace columns partition the data inside it. Different desktop launches with different `OMICSCLAW_DESKTOP_LAUNCH_ID` values share the same DB but get distinct Namespaces. Dropping a per-launch DB option keeps cross-launch read-fallback (`__shared__`) working with no extra cross-DB plumbing.
- **`oc interactive` from `~/`** — uses the absolute home path as Namespace. No special-case handling; `~` is a valid string id like any other directory.
- **Read fallback policy is asymmetric** — `recall` and `search` fall back to `__shared__`; `list_children` and `get_subtree` do not. The asymmetry is deliberate: per-row fallbacks give per-user contexts visibility into globally-shared content, but per-listing fallbacks would pollute a user's own inventory with shared structure they didn't author.

## Open questions

Tracked but not yet resolved in code:

- **`core://kh/*` seed bootstrap** — Who runs the script that writes KnowHow guards into `__shared__`? Candidates: `oc onboard` (one-time per workstation), `init_db()` (every start), or a separate `oc seed` command. Until this is decided, KH content lives only as markdown under `knowledge_base/knowhows/` and the `read_knowhow` tool reads it directly from disk; the `__shared__` partition holds no KH rows. The `("core", "kh")` entry in `SHARED_PREFIXES` is forward-looking — it ensures that *if* something later writes a `core://kh/*` URI, it lands in `__shared__` automatically.
- **`_auto_capture_dataset` policy** — When the bot detects a dataset filename, should it write under the user's Namespace or `__shared__`? Today it goes user-scoped (per CompatMemoryStore default), which means the same `pbmc.h5ad` mentioned by two users gets two `dataset://` rows. Whether to deduplicate at `__shared__` is a UX question.

## Flagged ambiguities

- **"user"** is used three ways: (1) the human researcher (`core://my_user`), (2) the chat-side participant (`Session.user_id`), (3) the Linux process owner. In this doc "user" means (1) or (2) — context determines which; never (3).
- **"workspace"** appears in both the **Surface** layer (the directory the user picked, used as the Namespace string) and the `ScopedMemory` layer (a filesystem root). Same physical directory, different concepts; will collapse only if ScopedMemory is integrated into MemoryEngine.
- **GraphService** (legacy) and **MemoryEngine** (target) co-exist during the migration window. PR #6 retired the deeper migration to keep its scope bounded — `MemoryClient.forget` / `MemoryClient.get_recent` and three server endpoints (`/memory/update`, `/memory/children`, `/memory/domains`) still route through `GraphService` because their verbs lack a clean engine equivalent. Use `MemoryEngine` in all new code; only touch `GraphService` from migration PRs.
- **CLI/TUI graph wiring is deferred.** Documentation through PR #132 listed `cli_namespace_from_workspace(workspace_dir)` as the Surface helper, implying CLI/TUI hosted a graph `MemoryClient`. In practice the `/memory` slash command only ever bound to `ScopedMemory`. The helper remains exported for the day CLI/TUI gains cross-Surface continuity; until then `omicsclaw/interactive/` does not construct a `MemoryClient`. Stale `cli/cli_user` and `tui/tui_user` rows in production DBs are migration artifacts with no live writer.
- **"namespace"** vs **"domain"**: domain is the URI prefix (`dataset`, `core`, …); namespace is the user/workspace isolation key. They are orthogonal columns; never use one as a synonym for the other.
