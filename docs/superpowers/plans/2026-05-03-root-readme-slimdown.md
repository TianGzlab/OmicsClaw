# Root README Slimdown Plan

**Goal:** Reduce root `README.md` from a long reference document into a concise
project entrypoint while preserving the current install path, core value
proposition, commands, domain coverage, safety notes, and links to detailed
docs.

**Scope and non-goals:**
- Modify `README.md`.
- Update `docs/superpowers/plans/README.md`.
- Do not change code, dependency files, docs site content, or `README_zh-CN.md`
  unless requested separately.
- Keep important repository contracts discoverable through links instead of
  duplicating full instructions in the README.

**Key assumptions:**
- Detailed installation guidance now lives in `docs/_legacy/INSTALLATION.md`
  and `docs/introduction/quickstart.mdx`.
- Remote execution details live in `docs/engineering/remote-execution.mdx`.
- Memory details live in `docs/engineering/memory.mdx` and legacy
  `docs/_legacy/MEMORY_SYSTEM.md`.
- Skill details are better handled by `oc list`, `skills/catalog.json`, and the
  domain docs under `docs/domains/`.

**File map:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/README.md`
- Create: `docs/superpowers/plans/2026-05-03-root-readme-slimdown.md`

**Tasks:**
1. Keep the header, badges, core positioning, and release note, but shorten
   marketing/detail-heavy prose.
2. Collapse installation to the recommended conda path plus a brief venv
   fallback; link detailed install docs for edge cases.
3. Collapse configuration to `oc onboard` and a minimal `.env` example.
4. Collapse quick start, memory, app backend, remote mode, bot channels, MCP,
   and architecture into short operational sections with links.
5. Replace the full skill catalog tables with a compact domain coverage table
   and point to `oc list`, domain docs, and `skills/catalog.json`.
6. Shorten AI-agent/contributing/community/acknowledgment sections to essential
   pointers.
7. Run markdown/link inspections and `git diff --check`.

**Verification strategy:**
- Run `git diff --check -- README.md docs/superpowers/plans/README.md`.
- Search README for removed stale links such as `docs/INSTALLATION.md`,
  `docs/METHODS.md`, and `docs/architecture.md`.
- Verify referenced local paths exist.
- Inspect heading structure with `rg '^#{1,3} ' README.md`.

**Acceptance criteria:**
- README is materially shorter and easier to scan.
- Recommended setup remains `bash 0_setup_env.sh`.
- The README no longer duplicates long dependency-resolution notes or full
  skill tables.
- Important detailed information remains reachable through current docs paths.
