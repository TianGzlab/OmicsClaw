# Memory System Refactor Plan

**Created**: 2026-05-09 · **Status**: planning · **Reference**: [`docs/CONTEXT.md`](./CONTEXT.md)

## Overview

Replace the 1584-line `GraphService` god class with a layered architecture (`MemoryURI` / `namespace_policy` / `MemoryEngine` / `ReviewLog` / `MemoryClient`) and add a `namespace` isolation dimension to `paths` / `search_documents` / `glossary_keywords`. Lands across **8 PRs** (PR #1 → #6 + #3 splits into a/b/c).

The goal stated by the user: *make OmicsClaw remember each user's Sessions, preferences, and lineage* across CLI/TUI, Desktop App, and Telegram/Feishu surfaces.

## Architecture decisions (frozen — don't re-litigate without updating CONTEXT.md)

| Decision | Choice | Source |
|---|---|---|
| Cleavage axis | hot path / cold path | grilling Q-recommendation, not A/B/C |
| Identity scoping | (c) hybrid: surface-injected `namespace` string | grilling Q1 |
| Read fallback | (c) recall✓ / search✓ / list_children✗ / write strict | grilling Q2 |
| URI namespace assignment | `core://agent`, `core://kh/*`, `core://my_user_default` shared; rest per-namespace | grilling Q3 |
| Strategy location | (β) `MemoryClient` decides; engine takes namespace as required arg | grilling Q3 |
| Migration framework | (c) custom lightweight runner under `omicsclaw/memory/migrations/` | grilling Q4 |
| Version chain | (c) two APIs: `upsert` (overwrite) default; `upsert_versioned` for `core://*` + `preference://*` | grilling Q5 |
| Search reindex semantics | shared writes don't propagate; versioned upsert deletes+reinserts; glossary gets namespace column | grilling Q6 |

## Dependency graph

```
PR #1 ─ MemoryURI + namespace_policy
  │     (pure code, no schema, no behavior change)
  │
  ├──→ PR #2 ─ migrations runner + 001_namespace
  │     │     (schema change; backfill from disclosure)
  │     │
  │     ├──→ PR #3a ─ MemoryEngine WRITE path + SearchIndexer.refresh
  │     │     │     (upsert / upsert_versioned / patch_edge_metadata)
  │     │     │
  │     │     ├──→ PR #3b ─ MemoryEngine READ path
  │     │     │     │     (recall / search / list_children / get_subtree)
  │     │     │     │
  │     │     │     └──→ PR #4a ─ MemoryClient + CompatMemoryStore namespace injection
  │     │     │             │
  │     │     │             └──→ PR #5 ─ Surface integration (CLI + Desktop + Bot)
  │     │     │                     │
  │     │     │                     └──→ PR #6 ─ Cleanup (delete GraphService residue)
  │     │     │
  │     │     └──→ PR #3c ─ Glossary namespace + GraphService transitional shim ║ parallel with #3b
  │     │
  │     └──→ (PR #4b ReviewLog can run parallel with #4a after #3b)
```

**Critical path**: #1 → #2 → #3a → #3b → #4a → #5 → #6 (8 sequential PRs minimum).
**Parallelizable**: #3c with #3b; #4b with #4a; #2 with #1 (truly independent — backfill parses `disclosure`, not URI).

---

## Phase 1: Foundation (PR #1, PR #2)

### PR #1 — `MemoryURI` + `namespace_policy`

**Goal**: Introduce shared vocabulary as pure additions. Zero schema, zero behavior change.

#### Task 1.1: Create `MemoryURI` value object

- **Files**: `omicsclaw/memory/uri.py` (new), `tests/memory/test_memory_uri.py` (new)
- **Acceptance**:
  - [ ] `MemoryURI.parse("core://agent")` returns `MemoryURI(domain="core", path="agent")`
  - [ ] `MemoryURI.parse("agent")` returns `MemoryURI(domain="core", path="agent")` (default scheme)
  - [ ] `MemoryURI.parse("core://")` is `is_root` and `path == ""`
  - [ ] `MemoryURI.parse("dataset://pbmc.h5ad").parent()` returns root URI for that domain (or `None` if root)
  - [ ] `MemoryURI(domain="analysis", path="sc-de").child("run_42")` produces `analysis://sc-de/run_42`
  - [ ] `str(uri)` is the canonical `domain://path` form, idempotent under parse
  - [ ] Frozen dataclass; equality by `(domain, path)`; hashable
  - [ ] Rejects empty domain, control chars, `://` in path
- **Verification**: `pytest tests/memory/test_memory_uri.py -v` passes; `mypy omicsclaw/memory/uri.py` clean
- **Dependencies**: None
- **Scope**: S (1 source + 1 test file)
- **Risk**: low — pure code

#### Task 1.2: Create `namespace_policy` module

- **Files**: `omicsclaw/memory/namespace_policy.py` (new), `tests/memory/test_namespace_policy.py` (new)
- **Acceptance**:
  - [ ] `SHARED_PREFIXES` constant matches CONTEXT.md's namespace ownership table exactly
  - [ ] `VERSIONED_PREFIXES` constant matches CONTEXT.md's versioned-upsert table exactly
  - [ ] `resolve_namespace(uri, current="tg/A")` returns `"__shared__"` for `core://agent`, `"tg/A"` for `analysis://x`
  - [ ] `should_version(uri)` returns `True` for `core://agent`, `core://my_user`, `preference://qc/cutoff`; `False` for `dataset://x`, `analysis://run_42`
  - [ ] All 12 rows from the CONTEXT.md namespace table have a corresponding test case
- **Verification**: `pytest tests/memory/test_namespace_policy.py -v` passes
- **Dependencies**: 1.1 (imports `MemoryURI`)
- **Scope**: S
- **Risk**: low — pure functions

> **Defer**: migrating the 3 existing `_parse_uri` call sites to `MemoryURI.parse` is held for PR #6 (cleanup), so PR #1 is pure addition with zero regression surface.

#### Checkpoint: PR #1 merged

- [ ] `pytest` full suite green
- [ ] `mypy omicsclaw/memory/` clean
- [ ] No existing files modified — verify with `git diff --stat`
- [ ] CONTEXT.md and PR description cross-reference each other

---

### PR #2 — Migrations framework + `001_namespace`

**Goal**: Add `namespace` columns to 3 tables, rebuild PKs, backfill from `disclosure`. **Highest data-risk PR**.

#### Task 2.1: Migrations framework skeleton

- **Files**:
  - `omicsclaw/memory/migrations/__init__.py` (new)
  - `omicsclaw/memory/migrations/runner.py` (new)
  - `omicsclaw/memory/migrations/_registry.py` (new)
  - `tests/memory/test_migration_runner.py` (new)
- **Acceptance**:
  - [ ] `_schema_version` table created on first run (column: `version`, `applied_at`)
  - [ ] `run_pending(db)` discovers migration modules in same dir, sorts by version string, applies pending ones in order
  - [ ] Each migration is a module exposing `VERSION: str`, `DESCRIPTION: str`, `async def apply(db) -> None`
  - [ ] Already-applied migrations are skipped (idempotent at framework level)
  - [ ] Failed migration leaves `_schema_version` untouched (transactional record-after-apply)
- **Verification**: framework tests pass; mock migrations apply in correct order
- **Dependencies**: None (PR #1 not strictly required)
- **Scope**: S
- **Risk**: low — new code only

#### Task 2.2: Wire `init_db()` to call `run_pending()`

- **Files**: `omicsclaw/memory/database.py` (modify)
- **Acceptance**:
  - [ ] After `Base.metadata.create_all`, call `await run_pending(self)`
  - [ ] Fresh DB (created by `create_all`) sees `001_namespace` already-applied via the migration's idempotent guard, OR runner records it as applied without re-executing — **decide via 2.4 design**
  - [ ] Existing `init_db` callers are unaffected (existing tests pass)
- **Verification**: `pytest tests/test_memory_server_security.py` passes (touches init_db); manual init against fresh DB shows expected schema
- **Dependencies**: 2.1
- **Scope**: XS
- **Risk**: low

#### Task 2.3: Write `001_namespace` migration

- **Files**: `omicsclaw/memory/migrations/001_namespace.py` (new)
- **Acceptance**:
  - [ ] `apply()` is **idempotent** — re-running on an already-migrated DB is a no-op (check column existence first)
  - [ ] On legacy DB: adds `namespace VARCHAR(128) NOT NULL DEFAULT '__shared__'` to `paths`, `search_documents`, `glossary_keywords`
  - [ ] Rebuilds `paths` PK to `(namespace, domain, path)`
  - [ ] Rebuilds `search_documents` PK to `(namespace, domain, path)`
  - [ ] Rebuilds `glossary_keywords` UNIQUE to `(namespace, keyword, node_uuid)`
  - [ ] Drops and recreates `search_documents_fts` virtual table with `namespace` column
  - [ ] FTS rebuild repopulates from `search_documents` so search keeps working
  - [ ] **Backfill**: for each row in `paths`/`search_documents`, parse `disclosure` (when available) for session reference; look up `Session` row's `(platform, user_id)`; set `namespace = f"{platform}/{user_id}"`. Rows without parseable disclosure stay at `__shared__`
  - [ ] `glossary_keywords` (currently 0 rows) needs no backfill
- **Verification**: see Task 2.4
- **Dependencies**: 2.1, 2.2
- **Scope**: M
- **Risk**: **HIGH — schema + data**

#### Task 2.4: 001 migration test suite

- **Files**: `tests/memory/test_migration_001_namespace.py` (new)
- **Acceptance**:
  - [ ] `test_001_idempotent_on_fresh_db`: fresh `create_all` DB, run 001, then run 001 again — no errors, no duplicate columns
  - [ ] `test_001_adds_namespace_to_three_tables`: check `paths`/`search_documents`/`glossary_keywords` schema
  - [ ] `test_001_rebuilds_paths_pk_to_composite`: insert two rows with same `(domain, path)` but different namespaces — both succeed
  - [ ] `test_001_backfills_from_session_disclosure`: pre-seed legacy DB with disclosure `"Memory from session app:userX:abc"`; run 001; assert `paths.namespace == "app/userX"`
  - [ ] `test_001_backfills_from_session_path_disclosure`: pre-seed legacy session row with disclosure `"Session for user Y on tg"`; run 001; assert `paths.namespace == "tg/Y"`
  - [ ] `test_001_falls_back_to_shared_when_disclosure_unparseable`: pre-seed row with disclosure `""`; assert `namespace == "__shared__"`
  - [ ] `test_001_preserves_total_row_count`: row count of `paths`/`memories`/`edges` unchanged before/after migration
  - [ ] `test_001_replays_safely`: run 001 twice; assert second run is a no-op (no errors, no duplicate keys)
  - [ ] `test_001_rebuilds_fts_table_with_namespace`: query FTS table after migration, assert `namespace` column exists
  - [ ] `test_001_legacy_data_realistic`: clone `~/.config/omicsclaw/memory.db` to temp; run 001 against it; assert all 42 paths migrate to `namespace="app/desktop_user"`; assert no row lost
- **Verification**: `pytest tests/memory/test_migration_001_namespace.py -v`
- **Dependencies**: 2.3
- **Scope**: M
- **Risk**: medium — test correctness affects production safety

#### Task 2.5: Production-data dry-run

- **Files**: scripts/migrate_dry_run.py (new, **excluded from package**)
- **Acceptance**:
  - [ ] Script copies `~/.config/omicsclaw/memory.db` to `~/.config/omicsclaw/memory.db.pre001.bak`
  - [ ] Runs migration against the copy at a temp path
  - [ ] Prints diff: row counts before/after, namespace distribution after, any unparseable disclosures
  - [ ] Exit code 0 only if all assertions match acceptance criteria
- **Verification**: run `python scripts/migrate_dry_run.py`; produces expected output for current 216KB DB
- **Dependencies**: 2.3, 2.4
- **Scope**: S
- **Risk**: medium — but operates on a copy

#### Checkpoint: PR #2 merged

- [ ] **Backup verified**: `cp ~/.config/omicsclaw/memory.db ~/.config/omicsclaw/memory.db.pre001.bak` documented in PR description
- [ ] Production DB migrated successfully on dev machine (`oc app-server` starts, hits `/health`, queries memory)
- [ ] Migration test suite green
- [ ] All previously passing tests still pass
- [ ] PR description includes: "rollback recipe = `cp memory.db.pre001.bak memory.db`"

---

## Phase 2: Engine (PR #3a, #3b, #3c)

### PR #3a — `MemoryEngine` write path + `SearchIndexer` refresh

**Goal**: Implement hot-path writes. `GraphService` remains untouched; new code lives alongside.

#### Task 3a.1: `MemoryEngine` skeleton

- **Files**: `omicsclaw/memory/engine.py` (new), `tests/memory/test_memory_engine.py` (new — empty placeholder)
- **Acceptance**:
  - [ ] Class `MemoryEngine(db, search)` with `__init__` and type stubs for all 7 verbs (raise `NotImplementedError`)
  - [ ] `MemoryRef` and `VersionedMemoryRef` dataclasses defined
  - [ ] Imports compile; mypy clean
- **Dependencies**: PR #1, PR #2
- **Scope**: XS
- **Risk**: low

#### Task 3a.2: Implement `upsert` (overwrite mode) — TDD

- **Files**: `omicsclaw/memory/engine.py` (modify), `tests/memory/test_memory_engine.py` (modify)
- **Acceptance**:
  - [ ] `await engine.upsert(uri, content, namespace="ns/A")` creates Node + Memory + Edge + Path in given namespace
  - [ ] Re-calling with same `(uri, namespace)` UPDATEs the existing Memory row's content; **no new Memory row, no deprecation chain**
  - [ ] Re-calling with same `uri` but different `namespace` creates a separate `paths` row (independent)
  - [ ] After write, `search_documents` row at `(namespace, domain, path)` is refreshed
  - [ ] Returns `MemoryRef(memory_id, node_uuid, namespace, uri)`
  - [ ] Transaction committed atomically; rollback on exception
- **Test pattern (red-green-refactor)**:
  - [ ] Red: `test_upsert_creates_path_and_memory` (engine doesn't exist → fail)
  - [ ] Green: minimal `upsert` implementation
  - [ ] Refactor: extract `_resolve_or_create_path`, `_get_or_create_node` helpers
- **Dependencies**: 3a.1
- **Scope**: M
- **Risk**: medium — must preserve transaction semantics

#### Task 3a.3: Implement `upsert_versioned` — TDD

- **Files**: `omicsclaw/memory/engine.py` (modify), test file (modify)
- **Acceptance**:
  - [ ] First call: behaves like `upsert` (creates node, single active Memory row)
  - [ ] Subsequent calls with same `(uri, namespace)`: INSERTs new Memory row; sets old `deprecated=True, migrated_to=new_id`; new is `deprecated=False, migrated_to=None`
  - [ ] After versioned write, `search_documents` for `(namespace, domain, path)` is **deleted then re-inserted** with the new `memory_id`
  - [ ] Returns `VersionedMemoryRef(old_memory_id, new_memory_id, ...)`
- **Tests**:
  - [ ] `test_upsert_versioned_first_write_no_chain`
  - [ ] `test_upsert_versioned_creates_chain_on_second_write`
  - [ ] `test_upsert_versioned_old_search_doc_replaced`
  - [ ] `test_upsert_versioned_chain_can_have_3_links`
- **Dependencies**: 3a.2
- **Scope**: M
- **Risk**: medium — chain bookkeeping is the GraphService bug source

#### Task 3a.4: Implement `patch_edge_metadata`

- **Files**: engine.py + tests
- **Acceptance**:
  - [ ] Updates `priority` and/or `disclosure` on the Edge for given `(uri, namespace)` without touching Memory rows
  - [ ] Search_doc refreshed (priority/disclosure are part of search_terms)
- **Dependencies**: 3a.2
- **Scope**: S
- **Risk**: low

#### Task 3a.5: `SearchIndexer.refresh` namespace-aware

- **Files**: `omicsclaw/memory/search.py` (modify)
- **Acceptance**:
  - [ ] `refresh_search_documents_for(namespace, uri)` rebuilds the row at `(namespace, domain, path)` only
  - [ ] Existing `refresh_search_documents_for_node(node_uuid)` is updated to iterate over all `(namespace, path)` pairs pointing to this node
  - [ ] Glossary keyword join filters by `glossary_keywords.namespace IN (current, '__shared__')`
- **Dependencies**: 3a.2
- **Scope**: M
- **Risk**: medium — touches existing code; must keep GraphService callers working

#### Checkpoint: PR #3a merged

- [ ] All Engine write tests pass
- [ ] **GraphService still works** (existing tests green) — verify by running full suite
- [ ] Hand-spot in real DB: `MemoryEngine` and `GraphService` writes can co-exist without corrupting each other

---

### PR #3b — `MemoryEngine` read path

#### Task 3b.1: `recall` with read fallback

- **Files**: engine.py + tests
- **Acceptance**:
  - [ ] `recall(uri, namespace=N)` returns Memory if `(N, domain, path)` exists
  - [ ] If not found AND `fallback_to_shared=True` (default), tries `('__shared__', domain, path)`
  - [ ] If neither, returns `None`
  - [ ] Returned object's `_loaded_namespace` attribute indicates which namespace produced it
  - [ ] Only returns `deprecated=False` Memory rows
- **Tests**: see CONTEXT.md acceptance test list
- **Dependencies**: 3a.2 (need writes to test reads)
- **Scope**: S
- **Risk**: low

#### Task 3b.2: `search` with namespace combination

- **Files**: engine.py, search.py + tests
- **Acceptance**:
  - [ ] FTS5 query with `WHERE namespace IN (current, '__shared__')`
  - [ ] Order: namespace=current results first, namespace=`__shared__` second
  - [ ] `domain` filter optional; `limit` honored
- **Dependencies**: 3b.1
- **Scope**: M
- **Risk**: medium — FTS5 syntax + namespace filter combined

#### Task 3b.3: `list_children` strict-namespace

- **Files**: engine.py + tests
- **Acceptance**:
  - [ ] `list_children(uri, namespace=N)` returns only direct children at namespace N
  - [ ] Does NOT include shared subtree (per CONTEXT.md)
  - [ ] When uri is root, returns top-level paths in namespace
- **Dependencies**: 3b.1
- **Scope**: S
- **Risk**: low

#### Task 3b.4: `get_subtree`

- **Files**: engine.py + tests
- **Acceptance**:
  - [ ] Returns flat list of MemoryRef under `(namespace, prefix)` up to `limit`
  - [ ] Order: deterministic (e.g., by path)
- **Dependencies**: 3b.1
- **Scope**: S
- **Risk**: low

#### Checkpoint: PR #3b merged

- [ ] Engine read+write end-to-end test: `upsert` then `recall` round-trips correctly across 3 namespaces
- [ ] Cross-namespace isolation test: writing to `ns/A` does not appear in `recall(uri, namespace="ns/B")` (without fallback path)
- [ ] Read-fallback test: `recall("core://agent", namespace="ns/A")` returns shared content

---

### PR #3c — Glossary namespace + `GraphService` transitional shim

(Can run parallel with PR #3b after PR #3a lands.)

#### Task 3c.1: Glossary `add` with namespace

- **Files**: `omicsclaw/memory/glossary.py` (modify), tests
- **Acceptance**:
  - [ ] `add_glossary_keyword(keyword, node_uuid, namespace=N)` writes to namespace N
  - [ ] New method `add_glossary_shared(keyword, node_uuid)` writes to `__shared__`
  - [ ] Aho-Corasick automaton scans content per namespace context (search reindex passes `namespace` argument)
- **Dependencies**: PR #2
- **Scope**: M

#### Task 3c.2: `GraphService` shim → delegate to `MemoryEngine`

- **Files**: `omicsclaw/memory/graph.py` (heavy modify)
- **Acceptance**:
  - [ ] Existing `GraphService.create_memory(parent_path, content, ...)` calls `MemoryEngine.upsert_versioned(...)` internally with `namespace='__shared__'` (legacy default)
  - [ ] Existing `GraphService.update_memory(...)` likewise
  - [ ] All currently-passing GraphService tests **continue to pass without modification**
  - [ ] `app/server.py:2552-2570` callers untouched
- **Verification**: full pytest suite green; `tests/test_memory_server_security.py` green
- **Dependencies**: 3a.3, 3b.1
- **Scope**: L (touches large file)
- **Risk**: **HIGH — most likely PR to break existing tests**

#### Checkpoint: end of Phase 2

- [ ] `MemoryEngine` is the source of truth for all memory writes (via shim)
- [ ] All existing tests green; no behavior change observable from API surface
- [ ] Code coverage report on `engine.py` ≥ 90%

---

## Phase 3: Strategy + Cold Path (PR #4a, #4b)

### PR #4a — `MemoryClient` + `CompatMemoryStore` namespace injection

#### Task 4a.1: `MemoryClient` rewrite

- **Files**: `omicsclaw/memory/memory_client.py` (replace)
- **Acceptance**:
  - [ ] Constructor: `MemoryClient(engine, *, namespace: str)`
  - [ ] `remember(uri, content, **kw)` resolves namespace via policy, routes to `upsert` or `upsert_versioned`
  - [ ] `remember_shared(uri, content, **kw)` forces `namespace='__shared__'`
  - [ ] `recall`, `search`, `list_children`, `boot`, `get_recent` delegate to engine with current namespace
  - [ ] No legacy `_parse_uri` (uses `MemoryURI.parse`)
- **Tests**: full mock-engine suite (no DB needed for client tests)
- **Dependencies**: PR #3b
- **Scope**: M
- **Risk**: medium — surface change

#### Task 4a.2: `CompatMemoryStore` namespace injection

- **Files**: `omicsclaw/memory/compat.py` (modify)
- **Acceptance**:
  - [ ] `CompatMemoryStore.save_memory(session_id, mem)` extracts `(platform, user_id)` from session and constructs `namespace = f"{platform}/{user_id}"`
  - [ ] Internal `MemoryClient` instance uses that namespace
  - [ ] All existing CompatMemoryStore tests pass
- **Dependencies**: 4a.1
- **Scope**: M
- **Risk**: **HIGH — production data path for bots**

#### Checkpoint: PR #4a merged

- [ ] `tests/test_autoagent_failure_memory.py` passes
- [ ] Manual: simulate bot save → verify written namespace is `app/desktop_user` for desktop, `tg/<id>` if Telegram session simulated

---

### PR #4b — `ReviewLog` (parallel with #4a)

#### Task 4b.1: `ReviewLog` skeleton

- **Files**: `omicsclaw/memory/review_log.py` (new), tests
- **Acceptance**:
  - [ ] `ReviewLog(db, engine)` class
  - [ ] All 9 method stubs from CONTEXT.md interface signature
  - [ ] mypy clean
- **Dependencies**: PR #3b
- **Scope**: S

#### Task 4b.2: Version-chain operations

- **Files**: review_log.py + tests
- **Acceptance**:
  - [ ] `list_version_chain(uri, namespace)` returns list of memories ordered by `migrated_to` chain
  - [ ] `rollback_to(memory_id, namespace)` makes the target the active version, deprecating others
  - [ ] Raises `NoVersionHistoryError` if uri is in `OVERWRITE_PREFIXES` (i.e., not versioned)
- **Dependencies**: 4b.1
- **Scope**: M

#### Task 4b.3: Orphan + GC operations

- **Files**: review_log.py + tests
- **Acceptance**:
  - [ ] `list_orphans(namespace=None)` returns orphan memories (deprecated, no successor active)
  - [ ] `cascade_delete(uri, namespace)` removes node + all paths/edges/memories
  - [ ] `gc_pathless_edges(namespace=None)` removes edges with no path references
- **Dependencies**: 4b.1
- **Scope**: M

#### Task 4b.4: `browse_shared`

- **Files**: review_log.py + tests
- **Acceptance**:
  - [ ] Returns children of a URI in the `__shared__` namespace specifically
  - [ ] Used by Desktop UI when user wants to browse shared content
- **Dependencies**: 4b.1
- **Scope**: S

#### Task 4b.5: Changeset operations

- **Files**: review_log.py + tests
- **Acceptance**:
  - [ ] `list_pending_changes(namespace=None)` returns pending changeset entries
  - [ ] `approve_changes(change_ids)` marks them approved
  - [ ] `discard_pending_changes()` clears pending queue
- **Dependencies**: 4b.1, integrates with existing `snapshot.py`
- **Scope**: S

#### Checkpoint: end of Phase 3

- [ ] `MemoryClient` is the only entry point; engine is internal
- [ ] `ReviewLog` is independently testable; full suite green

---

## Phase 4: Surface Integration (PR #5)

### PR #5 — CLI / Desktop / Bot namespace injection + route migration

#### Task 5.1: CLI/TUI namespace = workspace path ✅ landed 2026-05-11

- **Files**: `omicsclaw/interactive/_memory_command_support.py` (added `build_graph_memory_command_view` + `is_graph_memory_subcommand`); `omicsclaw/interactive/interactive.py` and `omicsclaw/interactive/tui.py` (dispatch graph subcommands)
- **Acceptance**:
  - [x] `/memory remember|recall|search` resolves the workspace (cwd or `--workspace`) via `cli_namespace_from_workspace(workspace_dir)` and binds a per-call `MemoryClient` to that namespace
  - [x] Each response echoes the active namespace so users can confirm isolation without log scraping (`Remembered <uri> (namespace=...)`, `Namespace: <path>` in recall/search output)
  - [x] Covered by `tests/memory/test_cli_graph_memory_command.py` — round-trip, cross-workspace isolation, FTS hit, URI validation, missing-arg usage, help-text presence (7 cases, all green)
- **Notes**: Open question "what namespace from `~/`?" resolved → `cli_namespace_from_workspace(None)` returns `str(Path.cwd().resolve())`, matching `docs/CONTEXT.md` "`oc interactive` from `~/`" decision.
- **Dependencies**: PR #4a
- **Scope**: S
- **Risk**: low

#### Task 5.2: Desktop FastAPI per-request namespace

- **Files**: `omicsclaw/app/server.py` (modify `_get_graph_service` and similar helpers)
- **Acceptance**:
  - [ ] Memory route handlers extract workspace from request (via Desktop's `OMICSCLAW_DESKTOP_LAUNCH_ID` or workspace picker context)
  - [ ] Inject as namespace into MemoryClient
  - [ ] All existing `/memory/*` endpoints continue to function
- **Dependencies**: PR #4a
- **Scope**: M
- **Risk**: medium

#### Task 5.3: Bot platform/user namespace

- **Files**: `bot/core.py` (modify around lines 1380-1411 init block; lines 829-907 auto-capture; 3780-3950 save/recall/forget)
- **Acceptance**:
  - [ ] CompatMemoryStore receives session and derives namespace
  - [ ] Existing tests (`test_autoagent_failure_memory.py`, `test_interactive_memory_command_support.py`) pass
- **Dependencies**: 4a.2
- **Scope**: M
- **Risk**: **HIGH — bot regression possible**

#### Task 5.4: `/memory/review/*` routes use ReviewLog

- **Files**: `omicsclaw/app/server.py` (modify review/maintenance routes around 2925-3000)
- **Acceptance**:
  - [ ] `_get_review_log()` helper added (parallel to `_get_graph_service()`)
  - [ ] Review endpoints call ReviewLog instead of GraphService where the verb maps cleanly (orphans, version chains, rollback)
- **Dependencies**: PR #4b
- **Scope**: M
- **Risk**: medium

#### Task 5.5: Cross-surface integration test

- **Files**: `tests/integration/test_memory_cross_surface.py` (new)
- **Acceptance**:
  - [ ] Simulate write from CLI namespace, attempt recall from Bot namespace — assert isolation
  - [ ] Simulate `remember_shared` from CLI, recall from Bot — assert visibility (read fallback)
  - [ ] Simulate version chain rollback via desktop ReviewLog, verify CLI sees old content
- **Dependencies**: 5.1, 5.2, 5.3, 5.4
- **Scope**: M

#### Checkpoint: PR #5 merged

- [ ] All 4 surfaces operate with correct namespace isolation
- [ ] Integration test green
- [ ] Manual smoke: open desktop app, save preference, see it persisted across restart

---

## Phase 5: Cleanup (PR #6)

### PR #6 — delete `GraphService` residue + migrate legacy parsers

#### Task 6.1: Migrate legacy `_parse_uri` call sites

- **Files**: `omicsclaw/memory/snapshot.py:349`, anywhere else still using `_parse_uri`
- **Acceptance**:
  - [ ] All `_parse_uri` references replaced with `MemoryURI.parse`
  - [ ] `grep -rn "_parse_uri" omicsclaw/` returns nothing in non-test files
- **Dependencies**: PR #5
- **Scope**: S
- **Risk**: low

#### Task 6.2: Inline GraphService shim into engine

- **Files**: `omicsclaw/memory/graph.py` (delete or shrink to <100 lines), `omicsclaw/memory/__init__.py` (update exports)
- **Acceptance**:
  - [ ] No external file imports `GraphService` (verified via grep)
  - [ ] Public API: `get_memory_engine()`, `get_review_log()`, `get_memory_client(namespace=...)` replace `get_graph_service()` etc.
  - [ ] Module docstring updated
- **Dependencies**: 6.1
- **Scope**: M
- **Risk**: medium — last cross-cutting change

#### Task 6.3: Update README.md and AGENTS.md

- **Files**: `README.md`, `AGENTS.md` (memory section)
- **Acceptance**:
  - [ ] Memory section reflects new architecture: 3-layer, namespace, surfaces
  - [ ] References CONTEXT.md
- **Dependencies**: 6.2
- **Scope**: S

#### Checkpoint: end of refactor

- [ ] `wc -l omicsclaw/memory/*.py` shows total LOC reduced from ~5886 to <4000
- [ ] All tests green
- [ ] `mypy omicsclaw/memory/` clean
- [ ] README + AGENTS.md updated; CONTEXT.md unchanged (means contract held)

---

## Risks and mitigations

| Risk | Phase | Impact | Mitigation |
|---|---|---|---|
| 001 migration corrupts production DB | PR #2 | High | Backup `memory.db.pre001.bak`; dry-run script (Task 2.5) before merge; idempotent migration; replay test (Task 2.4) |
| GraphService shim regresses existing tests | PR #3c | High | Run full pytest suite on every commit in PR #3c; revert immediately if any green-before test fails |
| Bot user data leaks across users post-deploy | PR #5.3 | Critical | Integration test (Task 5.5) explicitly validates isolation; staging deployment with test users before prod |
| FTS5 reindex during 001 corrupts search | PR #2 | Medium | Migration test that searches before+after produces equivalent results for shared content |
| `__shared__` namespace becomes a junk drawer | All | Low | CONTEXT.md flag-ambiguities section; review-time discipline; every `remember_shared` requires reviewer check |
| Mid-refactor halt leaves duplicate logic | Any | Medium | Each PR independently revertable; main branch always working |
| Glossary keyword namespace breaks Aho-Corasick scan | PR #3c | Medium | Test that user A's keyword does not appear in user B's search_terms |

## Open questions (require human input before relevant PR)

| Question | Blocks |
|---|---|
| `OMICSCLAW_MEMORY_DB_URL` env var: should desktop launches with different `OMICSCLAW_DESKTOP_LAUNCH_ID` use different DBs, or same DB with different namespaces? | PR #5.2 |
| `core://kh/*` seed: who runs the bootstrap that writes KnowHow guards to `__shared__`? Is it `oc onboard`, `init_db`, or a separate command? | PR #4a (defines `remember_shared` callsite) |
| Should `_auto_capture_dataset` (`bot/core.py:829`) write to user's namespace OR shared? Currently fixed `dataset://{file_path}` is user-scoped per design, but a researcher with multiple datasets across workspaces gets duplicate writes. Confirm. | PR #5.3 |
| ~~When user runs `oc interactive` from `~/` (no project), what namespace?~~ — **resolved 2026-05-11**: `cli_namespace_from_workspace(None)` returns the resolved cwd; `~/` becomes the absolute home path. | ~~PR #5.1~~ ✅ |

## First-week kickoff (immediately actionable)

**Day 1 (now)** — start PR #1, Task 1.1:
1. `cd /data/beifen/zhouwg_data/project/OmicsClaw`
2. `git checkout -b refactor/memory-uri`
3. Create `omicsclaw/memory/uri.py` with TDD: write `tests/memory/test_memory_uri.py` first (red), implement until green, refactor
4. Land Task 1.1 + 1.2 as **two commits**, single PR
5. Open PR with description quoting CONTEXT.md namespace table

**Day 2-3** — PR #2 in parallel branch:
1. `git checkout -b refactor/memory-migrations` (off main, not off PR #1 — they're independent)
2. Run `cp ~/.config/omicsclaw/memory.db ~/.config/omicsclaw/memory.db.pre001.bak` **before any code**
3. Implement Tasks 2.1-2.4
4. Run dry-run script (2.5) against production DB copy
5. PR description includes dry-run output

**Day 4-5** — review window. Both PRs open, no further code work until merged. Use the time to:
- Validate CONTEXT.md against PR diffs
- Resolve open questions (especially `oc interactive` from `~/` policy)
- Confirm PR #1 truly has zero behavior change by running before/after benchmark on `bot/core.py` save flow

**Week 2** — PR #3a (Engine writes) starts.

## Parallelization opportunities

| Pair | Safe to parallelize? | Notes |
|---|---|---|
| PR #1 ‖ PR #2 | ✅ | Independent — URI parsing not used in 001 backfill |
| PR #3a ‖ PR #3c | ❌ | 3c (GraphService shim) needs 3a (engine writes) |
| PR #3b ‖ PR #3c | ✅ | Both depend on 3a; otherwise independent |
| PR #4a ‖ PR #4b | ✅ | Client and ReviewLog are siblings |
| PR #5.1 ‖ #5.2 ‖ #5.3 | ✅ | Each surface independent; coordinate via shared MemoryClient API |
| PR #5 + PR #6 | ❌ | #6 must come last |

## Verification before starting implementation

- [x] Every task has acceptance criteria
- [x] Every task has a verification step
- [x] Task dependencies are identified and ordered correctly
- [x] No task touches more than ~5 files (except 3c.2 — flagged as risk)
- [x] Checkpoints exist between phases
- [ ] **Human reviewed and approved this plan** ← required before PR #1 begins
