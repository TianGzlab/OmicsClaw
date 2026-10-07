# AGENTS.md — OmicsClaw Guide for AI Coding Agents

This guide is for AI coding agents working on the OmicsClaw codebase.

## Repository Working Contract

Before any complex repository maintenance, feature, or refactor task, read
`README.md` for what the project is and `CHANGELOG.md` for recent decisions
and milestones. Then read this `AGENTS.md`, root `SPEC.md`, and the directly
relevant code/docs.

Core rules:

- Reply in the user's language, usually Chinese or English.
- Stay concise, practical, and execution-focused.
- For non-trivial changes, work from a concise plan, keep edits scoped, and
  verify claims with concrete commands or file inspections before reporting
  completion.
- When you make an important decision or complete a meaningful milestone,
  add an entry at the top of `CHANGELOG.md`. Change `README.md` only when a
  user-facing entry point, install step or headline feature changes; its
  What's New holds at most five items of one sentence each.
- Run the `humanizer` skill (`.claude/skills/humanizer/SKILL.md`, from
  [blader/humanizer](https://github.com/blader/humanizer)) over any prose you
  write: code comments and docstrings, documentation, plans, README text,
  commit messages and PR descriptions. Use its embedded mode and keep code,
  commands, paths and identifiers unchanged. Agents without skill support
  read that file and apply its patterns directly.

## Project Overview

OmicsClaw is a multi-omics analysis platform supporting 88 skills
across 7 domains: spatial transcriptomics, single-cell omics, genomics,
proteomics, metabolomics, bulk RNA-seq, and literature. Each
skill is a self-contained module that performs a specific analysis task via CLI
or Python API. All processing is local-first. Design is inspired by
[ClawBio](https://github.com/ClawBio/ClawBio).

**Note**: OmicsClaw evolved from SpatialClaw. The agent framework was rebuilt
layer by layer during 2026; `docs/FRAMEWORK-REBUILD.md` is the living account
of what shipped, what was deleted, and what is still carried forward.

## Setup

```bash
cd /path/to/OmicsClaw

# Recommended: full conda-primary install (R + CLIs + Python in one shot)
bash 0_setup_env.sh
conda activate OmicsClaw

# pip-only alternative (no R, no CLIs, no science stack):
# pip install -e .                 # enough for `oc cli` to start and call a model
# pip install -e ".[channels]"     # Telegram and Feishu SDKs for `oc channel`

oc cli                     # terminal REPL
```

> **`oc` short alias**: After installing OmicsClaw (either path), both
> `omicsclaw` and `oc` commands are available system-wide via the
> `[project.scripts]` entry in `pyproject.toml`.
>
> **Dependency source of truth**:
> - **Python deps**: `pyproject.toml` holds the core `oc` needs (rich,
>   openai, anthropic, pydantic, ...) and PyPI-only method packages in
>   extras. The science stack, fastapi, uvicorn and prompt-toolkit are in
>   `environment.yml` Tier 4 (conda path only).
> - **R packages, bioinformatics CLIs, build toolchain** live in
>   `environment.yml` (conda path only).
> - **GitHub-only R packages** are installed inline by `0_setup_env.sh`
>   Tier 3 (`devtools::install_github` for spacexr, CARD, CellChat, numbat,
>   SPARK, DoubletFinder).
> - **Optional analysis backends** (cellrank, palantir, scvelo, tangram-sc,
>   …) are catalogued once, in `DEPENDENCIES` in `skills/_sdk/deps.py`: PyPI
>   name (as spelled in `## Dependencies`) → a pure-literal entry with
>   `module`, `kind` (`pip`/`git`/`r`), `install`, `description`, and optional
>   `also` / `alt_env`. Names resolve by key, then PEP 503-normalised key,
>   then `module`. This is the SSOT for backend name mapping; new algorithms
>   register here, and tools outside `skills/` read it with
>   `ast.literal_eval` rather than importing it.
> - **Per-skill dependencies** are the `## Dependencies` section of each
>   `SKILL.md`. They used to live in `skill.yaml`'s `deps.python`, mirrored
>   into a `requires:` frontmatter key and checked by
>   `scripts/audit_skill_requires.py`; the script, the key and `skill.yaml`
>   itself are all gone. The environment files above are what a full
>   install uses. The section is there so an agent about to run a script
>   knows what the script needs, and it is the whitelist of
>   `install_skill_deps`: only when a deployment sets
>   `skill_env=install` and a person approves the call does that tool
>   install names from this section — and only the ones asked for — into
>   an overlay environment, never into the base (see "Running a skill").
>
> The repository does not use a root `requirements.txt` as a primary
> install entrypoint.
>
> **Known `pip check` warning**: the full conda environment keeps
> `jinja2>=3.1.5` for FastAPI/nbconvert even though upstream
> `pygpcca==1.0.4` still pins `jinja2==3.0.3`. Treat that single warning as
> metadata noise when targeted import checks pass.

## Commands

`oc` takes a **surface**, not a subcommand. Deployment flags go before `--`;
a surface's own flags may be written on either side of it. Use `--` when a
value is spelled like a flag: `oc cli -- --prompt --model`.

| Command | Purpose |
|---------|---------|
| `oc cli` | Terminal REPL — the default way to use OmicsClaw |
| `oc cli --prompt-file <f>` | One exchange, non-interactive |
| `oc cli --session <id>` | Continue a stored conversation |
| `oc desktop` | HTTP backend for the OmicsClaw-App client |
| `oc channel` | Instant-messaging adapters (Telegram, Feishu) |
| `oc <surface> --help` | That surface's own flags |
| `python -m pytest -v` | Deterministic fast suite (excludes demo/slow/eval) |
| `make test` / `test-slow` / `test-all` | Fast / scientific / everything-but-eval |
| `make install` / `install-dev` | `pip install -e .` / `.[dev]` into the active environment |
| `make list` | Skill index: count, skipped, names per domain |

There is **no `oc run <skill>`**. The skill runner and the other 33
subcommands lived in `omicsclaw/surfaces/cli/_main.py`, which the framework
rebuild retired; see "Running a skill" below for what replaced it.

> **Makefile status.** `list`, `skill-index`, `demo`, `demo-all` and
> `demo-bulkrna` were rewritten against `omicsclaw.skills` and the real
> script paths, and do run. `catalog`, `audit-requires`, `check-drift`,
> `eval-snapshot` and `demo-orchestrator` were deleted with the old skill
> system. `bot-telegram`, `bot-multi` and `bot-list` were rewritten against
> `oc channel` and do run; `bot-telegram` and `bot-multi` exit 1 unless
> `OMICSCLAW_APPROVAL_TIMEOUT_S` is set. `memory-server`, `venv`, `setup`,
> `setup-full`, `install-full`, `install-spatial-domains`, `install-oc` and
> `oc-link` were deleted.

## Project Structure

`omicsclaw/` is one Python package of one-way layers. **Every layer may
import `schema`; `schema` imports nothing.** `docs/FRAMEWORK-REBUILD.md`
is the living account of how the stack got here and is the file to read
before changing a layer boundary.

```
OmicsClaw/
├── omicsclaw/
│   │  ── the rebuilt stack: this is where new code goes ──
│   ├── schema/         Stdlib-only vendor-neutral leaf. Message, ToolCall,
│   │                   ToolResult, ToolDefinition, Usage, StreamChunk.
│   ├── provider/       Model adapters. LLMProvider + OpenAI-compatible and
│   │                   Anthropic; imports only schema.
│   ├── engine/         The ReAct main loop. Imports schema + provider.
│   ├── tools/          Tool registry, policy, dispatch; builtin/ holds
│   │                   read_file, write_file, edit_file, bash, web_*.
│   ├── context/        Prompt assembly, token budget, progressive compaction.
│   ├── skills/         Skill **loader** (plural). Reads skills/*/SKILL.md into
│   │                   a catalogue; `use_skill` fetches one body on demand.
│   ├── memory/         Session store + long-term recall + MEMORY.md precis.
│   ├── mcp/            MCP client: .mcp.json, stdio + Streamable HTTP.
│   ├── planning/       The execution plan the agent keeps outside the chat.
│   ├── permission/     Rules, modes, danger patterns; decides if a call happens.
│   ├── sandbox/        Docker/Podman isolation for `bash`. Stdlib-only leaf.
│   ├── hooks/          Tool-call interception seam + the audit hook.
│   ├── observability/  Spans, six instruments, optional OpenTelemetry.
│   ├── subagent/       Sub-agent definitions and the `task` tool that
│   │                   delegates one bounded sub-task to one of them.
│   ├── entry/          Composition root, sessions, turns, events, approval,
│   │                   plus the cli/, desktop/ and channel/ facades.
│   ├── launch/         `oc` argv grammar; picks a surface and builds the app.
│   ├── skillenv/       Which packages under a skill's `## Dependencies` the
│   │                   `python` bash runs can import; the note `use_skill`
│   │                   appends (`skill_env=probe`, the default; `off`
│   │                   removes it); with `skill_env=install`, the
│   │                   approval-gated `install_skill_deps` and the overlay
│   │                   venvs it builds. Reads skills/_sdk/deps.py as a file.
│   │  ── kept from the old stack ──
│   ├── common/         Framework-side helpers: report reading/validation,
│   │                   checksums, runtime_env, workspace. Skills no longer
│   │                   import it; they use skills/_sdk/.
│   ├── remote/         SSH remote execution. Partly imports: schemas, auth,
│   │                   storage and routers/{connections,sessions} do (with
│   │                   fastapi installed); routers/{env,jobs,datasets,
│   │                   artifacts}, app_integration, run_wire and
│   │                   runtime_binding reach the deleted `omicsclaw.control`
│   │                   or `omicsclaw.diagnostics` and do not.
│   ├── attachments/    Immutable attachment store. Imports; the store half
│   │                   needs the deleted control plane.
│   ├── routing/        Old keyword router. Does not import; superseded by
│   │                   the prompt index + `use_skill`.
│   └── surfaces/       desktop/ only, kept as the pre-port reference the
│                       wire-contract tests diff against. Does not import.
│                       surfaces/cli/ was deleted once entry/cli/ was
│                       covered on its own; see git log for it.
├── skills/             88 skills across 7 domains, each a SKILL.md plus scripts
│   ├── spatial/ singlecell/ genomics/ proteomics/ metabolomics/ bulkrna/
│   ├── literature/
│   ├── _sdk/           Mechanical helpers every skill shares: result.json and
│   │                   report writers, checksums, R script runner and
│   │                   r_scripts/, the dependency registry (deps.py), conda
│   │                   sub-env calls. Imports no `omicsclaw`; not a skill
│   └── <domain>/_lib/  Domain-shared utilities, not registered as skills
├── tests/              schema/ provider/ engine/ tools/ context/ skills/ entry/
│                       mcp/ memory/ permission/ planning/ launch/ sandbox/
│                       hooks/ observability/ subagent/ are the rebuilt
│                       stack's suite
├── docs/FRAMEWORK-REBUILD.md   Living status of the rebuild — read this first
├── docs/plans/         Numbered plans, one per rebuild step
├── OMICSCLAW.md        Runtime contract of the analysis agent — the top of its
│                       system prompt, read from beside skills/
├── SPEC.md             Repository maintenance + AI development contract
├── CLAUDE.md           Claude Code entry: maintenance contract, issue tracker
└── AGENTS.md           This file
```

`autoagent/` is **gone**: deleted whole with its tests. The `omicsclaw.autoagent`
imports and "autoagent" references left in `omicsclaw/surfaces/desktop/`
(chiefly `server.py`) no longer point at anything.

`surfaces/cli/` is **gone**, not kept: 26 files and 14,936 lines removed
once `entry/cli/` was covered by its own behavioural tests rather than by
comparison against it. The reasoning about what was and was not ported
survives in `omicsclaw/entry/cli/__init__.py`'s docstring; the code
survives only in `git log`.

> **Import convention**: domain-specific skill utilities live in
> `skills/<domain>/_lib/` and are imported as
> `from skills.<domain>._lib.<module> import <name>`. A directory starting
> with `_` is never a skill. The `omicsclaw/` package holds only
> domain-agnostic framework code. Helpers every skill shares live in
> `skills/_sdk/` and are imported as `from skills._sdk.<module> import <name>`,
> using only the names in each module's `__all__` (frozen by
> `tests/sdk/test_public_surface.py`). Skill code never imports `omicsclaw`,
> and `omicsclaw` never imports `skills`: they meet through files
> (`SKILL.md` and the result.json schema `RESULT_SCHEMA` in
> `skills/_sdk/result.py`), and `tests/sdk/` pins both sides.
> `tests/sdk/test_boundary.py` lists no exceptions on either side. `_sdk` imports
> nothing from any `skills/<domain>/`, and a domain `_lib` may import only its
> own domain's `_lib` and `skills._sdk`. Every skill script puts the checkout
> on `sys.path` with the same block, anchored on `skills/_sdk/__init__.py`
> (see `templates/skill/replace_me.py`).
> Framework control-plane credentials are removed where the framework starts
> a process (`bash`'s local shell), never in skill code.

## Skill Architecture

Every skill has a `SKILL.md` with YAML frontmatter + methodology, a Python
script accepting `--input`, `--output`, `--demo`, and optionally `tests/`
and `data/`.

### The frontmatter contract

`omicsclaw/skills/` reads exactly four keys. Anything else in a header is
inert — it is neither validated nor shown to anyone.

| Key | Required | Read by |
|---|---|---|
| `name` | yes | the prompt index, `use_skill` |
| `description` | yes | the prompt index — this is what the model routes on |
| `trigger` | no | `/skills <query>` search only; **never** auto-fires a skill |
| `tags` | no | `/skills <query>` search only |

A header missing `name` or `description` is **skipped**, not indexed, and
the reason lands in `SkillIndex.skipped` as data rather than a log line.
`trigger` may be a comma-separated scalar or a block sequence; both reach
`Skill.triggers` the same way.

`version`, `author`, `license`, `emoji` and `requires` used to sit here.
They were removed from every header because no part of the current stack
read them. The dependency list they mirrored now lives in the body, as
`## Dependencies`.

### Running a skill

The 27 computational single-cell skills expose `_api.py` through
`skills._sdk.notebook.load_skill`. Their CLIs keep reports and file writes;
the function libraries return data or Figures. Each ships an executable
`examples/example_step.py` and an API section generated from its public
functions. `sc-count`, `sc-velocity-prep` and `sc-fastq-qc` stay CLI-only;
steps call them through `run_cli`. See `templates/skill/README.md` for the
library contract and `OMICSCLAW.md` for Python/R module execution.

`oc run <skill>` is gone. A skill script is now invoked **directly**, by a
person or by the agent through `bash`:

```bash
python skills/<domain>/<skill>/<script>.py --input <file> --output <dir>
python skills/<domain>/<skill>/<script>.py --demo --output /tmp/<skill>_demo
```

**Missing packages.** `use_skill` appends an environment check to the body
(`skill_env=probe`, the default): which packages under `## Dependencies` the
`python` that `bash` runs can import, git-only ones with the registry's
command, R packages named but not probed. With `skill_env=install` (set by
the deployment; `oc desktop` refuses it, having no approval channel) the
agent also gets `install_skill_deps(skill, packages)`, mounted only while
`bash` runs on this machine. After the person approves the card it builds
an overlay — `python -m venv --system-site-packages` over that `python`, in
`$XDG_CACHE_HOME/omicsclaw/envs/<key>/` (or `--skill-env-dir`) — installs
only what the base lacks, wheels only and pinned, rolls back on any new
`pip check` problem, and returns the interpreter to run the script with:
`PYTHONNOUSERSITE=1 <overlay>/.venv/bin/python skills/<domain>/<skill>/<script>.py …`.
The base environment is never changed. Things to know:

- Packages come from **this machine's pip configuration**, exactly as with
  your own `pip install`; OmicsClaw does not check where it points (index,
  proxy, certificates), and the card says so. Each result lists every wheel
  with its source, marking plain-http ones. A `pip.conf` under the base
  environment's prefix does not apply to an overlay; use the user-level
  `~/.config/pip/pip.conf` (or `~/.pip/pip.conf`) instead.
- A pip configuration or environment that sets `target`, `prefix`, `root`,
  `user`, `src` or `python` is refused before anything is resolved: it would
  install outside the overlay or into another interpreter, and `prefix`
  pointing at the base would change it. `quiet`, `global`, `site` and `user`
  cannot hide such a setting from the check.
- Do not configure a directory the agent can write to (anything in the
  workspace) as `find-links`: whoever writes there supplies packages.
- Approval works like `bash`'s: asked in the default mode, not under
  auto-approve or `/auto`. A rule on `bash(pip install*)` does **not** reach
  this tool — rules match tool names — so a deployment that wants the same
  control writes `install_skill_deps` rules (`ask: ["install_skill_deps"]`
  asks every time; "always allow" writes `install_skill_deps(<skill>)`).
- Overlay directories can be deleted at any time. A changed base gets a new
  key and a new overlay; the old one is never reused or removed by OmicsClaw.

### Sandbox

With the sandbox on, the repository's `omicsclaw/` and `skills/` are
mounted read-only at their host paths, so `bash` runs the skill code of
this checkout; the repository root is not mounted. An existing
`<workspace>/.env` is covered by `/dev/null` and `<workspace>/.omicsclaw/`
by an empty tmpfs inside the container, with the sandbox's own exchange
directory `.omicsclaw/sandbox` mounted back so `bash` still works. The
container defaults suit several concurrent analyses: memory `auto` (80% of
`MemTotal`), `/tmp` 64g, `/dev/shm` 128g, pids 65536, `nofile` 65536, CPUs
uncapped, GPUs only with `--sandbox-gpus`.

### Reaching a skill's instructions

The model chooses. The system prompt carries one `- name: description`
line per skill instead of the full bodies, and
`use_skill` fetches one body on demand. The tool also returns the skill's
**directory**, which is how the model finds the script beside a body that
rarely names its own path.

A user steers by naming the skill in the request or describing the task.
Skills are **not** slash commands: `oc cli` answers `/spatial-de …` with
"No command named /spatial-de" and a hint, and Tab over a bare `/` lists
only the REPL's commands. `/skills [query]` browses the index.

The model then runs the script itself. What was lost with the old runner is
the deterministic half — the `result.json` envelope check, the run receipt,
the replay capsule and the output-directory claim. Do not describe those as
current behaviour.

### The skill toolchain is gone, and so is `skill.yaml`

The old skill system defined a skill by a `skill.yaml` machine contract and
generated everything else from it. That system was discarded. Deleted with
it: all 21 skill/catalogue scripts under `scripts/` (`generate_skill_md`,
`generate_domain_index`, `generate_routing_table`, `generate_catalog`,
`generate_skill_dag`, `generate_orchestrator_counts`, `generate_parameters_md`,
`skill_lint`, `validate_skills`, `validate_skill_yaml`, `canonicalize_skill_yaml`,
`migrate_to_skill_yaml`, `sync_skill_version`, `sync_skill_docs`,
`audit_skill_requires`, `check_description_drift`, `extract_skip_when_cases`,
`evaluate_routing_oracle`, `check_routing_budget`, `analyze_benchmark_campaign`,
`run_three_suite_skill_lifecycle_benchmark`), their tests, all 96
`skill.yaml` files, `skills/catalog.json`, `skills/skill_dag.json`,
`skills/skill_dag_reviews.yaml` and `omicsclaw/diagnostics.py`.

Treat "auto-generated from skill.yaml" in any older document as historical.
`scripts/` now holds eight files, none of which touch skills.

Nothing was lost in the deletion that a reader needs. The output
inventories in `skill.yaml` were already named in the `SKILL.md` prose at
100%; the dependency lists were not — only 21% appeared in a body, and 36
skills named none of theirs — so `deps.python` was carried into each body
as a `## Dependencies` section first.

**`SKILL.md` is the single source of truth**, hand-edited. One document is
derived from it, and a test rather than a generator keeps it honest:
`skills/<domain>/INDEX.md`, checked by
`tests/skills/test_domain_index_is_current.py` and regenerated with
`OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
The `OMICSCLAW.md` routing table is maintained by hand.

### Skill conventions

Nothing below is enforced mechanically — `skill_lint.py` and the schema
validator went with the rest of the toolchain. They are still the bar for
review, and they are what every gold skill does.

- A `description` says when to **load** and when to **skip**, naming the
  skill to use instead. The skip half prevents a wrong choice; it is the
  more valuable half and the one a naive one-line parser drops.
- `name` is unique across all skills. A duplicate is **skipped** by the
  loader, not merged. Check with the `load_skills` one-liner above.
- Every primary skill script exposes a lightweight direct `--help`.
- The `## Key CLI` section spells the real
  `python skills/<domain>/<skill>/<script>.py` invocation. The body is the
  only place anyone learns a skill's CLI.
- Each `## Gotchas` bullet anchors to a real code path
  (`<script>.py:LINE`), a `result.json` key, or a `tables/` / `figures/`
  filename the script actually writes.
- `## Inputs & Outputs` is an inventory, not a promise. Do not turn an
  optional entry into an unconditional one.

Rules that **lapsed with the shared runner** and are kept here only so
nobody re-derives them from an old document: the `result.json` envelope
check, `reproducibility/replay.json` + `environment.json` + `replay.sh`,
the generated top-level `README.md`, the `security` / `resources.compute` /
`lifecycle.status` blocks, and the routing block that hid a deprecated
skill. Nothing enforces any of them today.

## How to Add a New Skill

1. `cp -r templates/skill skills/<domain>/<your-skill-name>`, then rename
   and fill the placeholders.
2. Write the `SKILL.md` frontmatter by hand: `name` (unique across all 88 —
   a duplicate is skipped, not merged), `description` (say when to **load**
   it *and* when to **skip** it, naming the skill to use instead; the model
   routes on this line alone), and optionally `trigger` / `tags`.
3. Fill in the `SKILL.md` body — including a worked
   `python skills/.../<script>.py` invocation, because that is now the only
   way anyone learns the CLI.
4. Add the Python script, accepting `--input`, `--output`, `--demo`.
5. Add tests under the skill's own `tests/`.
6. Add the test path to `pyproject.toml`'s `[tool.pytest.ini_options]
   testpaths` if it should run in the default suite.
7. Regenerate the domain index:
   `OMICSCLAW_WRITE_SKILL_INDEX=1 pytest tests/skills/test_domain_index_is_current.py`.
8. Update the routing table in `OMICSCLAW.md` by hand — the count and, for a
   new domain, its row.

Check it landed with `python -c "from omicsclaw.skills import load_skills;
i = load_skills('skills'); print(len(i), i.skipped)"` — 0 skipped is the
healthy answer.

## Development Workflow

For repository development work, start with a short plan when the task spans
multiple files, debug from root cause before editing, and verify the affected
behavior before committing, pushing, or opening a PR.

A PR description should be reviewer-oriented: a TL;DR, a recommended review
order, diff buckets, a note on generated or mechanical files, risk notes,
and the verification evidence you actually ran.

### Running the tests

The interpreter matters: the repo needs Python 3.11+ and the default
`python3` on a dev box is often older. The rebuilt stack's own suite is

```bash
python -m pytest tests/schema tests/provider tests/engine tests/tools \
  tests/context tests/skills tests/entry tests/mcp tests/memory \
  tests/permission tests/planning tests/launch tests/sandbox tests/hooks \
  tests/observability tests/subagent -p no:cacheprovider -q -o addopts=""
# 4982 passed, 12 skipped   <- measured 2026-09-21; see the note below
```

Treat that as the regression signal. The old CLI's suites were deleted
with `omicsclaw/surfaces/cli/`.

> **Several sessions write this tree at once.** Before reading a red suite
> as evidence about your own change, check `git status` for files you did
> not touch.

### Architecture Contracts

- [domain input contracts](docs/engineering/domain-input-contracts.md)

## Memory

`omicsclaw/memory/` is a session store plus long-term recall, opened by
`build_app` at `<workspace>/.omicsclaw/memory.db`. It replaced a 28-module
graph memory system (nodes, edges, URIs, namespaces, `ReviewLog`, a
FastAPI dashboard at `oc memory-server`) that the rebuild deleted; if you
find a document describing that, it is historical.

| Piece | Role |
|---|---|
| `SqliteSessionStore` | Conversations, one database per workspace. `list` filters nothing -- the file *is* the isolation boundary. |
| long-term store | Rated entries reached by the `memory_search` / `memory_write` tools. |
| `MEMORY.md` precis | The top-rated entries, rendered into the **last** block of the system prompt behind a closure, so a write during a run is visible on the next turn. |
| extractor | Every compaction hands the messages it is about to summarize to an extractor first, so what was said survives the summary. |

`--memory false` turns all of it off in one switch, and then conversations
are held in memory only.

## Surfaces

Three user-facing surfaces, all under `omicsclaw/entry/`, all reached
through `oc <surface>` and all driving the same `AgentApp` built by
`omicsclaw.entry.build_app`.

| Surface | Code | Entry | Audience |
|---|---|---|---|
| **CLI** | `omicsclaw/entry/cli/` | `oc cli` | Terminal users |
| **Desktop** | `omicsclaw/entry/desktop/` | `oc desktop` | OmicsClaw-App client |
| **Channel** | `omicsclaw/entry/channel/` | `oc channel` | Telegram / Feishu |

These are a **port** of `omicsclaw/surfaces/`, not a rewrite. For Desktop
the pre-port file is still on disk and is the reference -- but it does not
import, so read it rather than running it. For the CLI there is no longer
an original to consult: `surfaces/cli/` was deleted, and `tests/entry/`
is where this surface's behaviour is now defined.

### Desktop surface

```bash
oc desktop            # 127.0.0.1:8765 by default
```

`fastapi` and `uvicorn` come from `environment.yml`; there is no `[desktop]`
extra. Without them `oc desktop` exits 2 and names the `mamba` command.

Serves chat streaming (SSE) and the endpoints the Electron / Next.js client
needs. The wire contract's `*_SCHEMA_VERSION` values are byte-identical to
the pre-port ones because an external client depends on them -- changing one
is a cross-repository milestone, not a refactor.

**Cross-repository ownership**: this repository owns backend policy,
execution, persistence, file mutation and the stable HTTP contracts. The
separate `OmicsClaw-App` repository owns Electron / Next.js proxy routes,
TypeScript view models and UI interaction. Do not add React here, and do not
move backend policy into the App.

**Two known gaps, named rather than hidden**: `/chat/abort` and
`/chat/permission` were not ported, so an approval-gated tool on this
surface waits for its timeout instead of asking. The frontend also has no
`case` for the `event_omitted` frame, so a slow observer's GAP notice never
reaches the UI.

### Channel surface

```bash
pip install -e ".[channels]"     # platform SDKs are extras
oc channel --channels telegram
oc channel --channels feishu
```

Seven platforms can start: Telegram, Feishu, Slack, Discord, DingTalk, QQ
and Email. Every one of them requires an owner allowlist and refuses to
start without it. Prefer **one platform per process** unless you
specifically want them to share a session registry: `--channels` starts
all of them or none, so one mistyped credential stops the others too.

Required environment, beyond the provider keys:

- `TELEGRAM_BOT_TOKEN` — from @BotFather.
- `FEISHU_APP_ID` + `FEISHU_APP_SECRET` — from the Feishu dev console.
- `FEISHU_ALLOWED_SENDERS` — comma-separated owner `open_id` values.
  **Required**: ingress admits nobody else and refuses to start without it.
- `FEISHU_BOT_OPEN_ID` — this bot's own `open_id`. **Required**: ingress
  refuses to start without it, because a group @-mention cannot otherwise be
  attributed to this bot rather than to another mentioned human.

A sender outside the allow-list produces **no turn at all**, not a polite
refusal. The runtime contract every adapter shares is `OMICSCLAW.md`;
per-platform configuration goes in `.env` at the project root, and
`.env.example` section 11 is the full per-platform list.

### CLI surface

```bash
oc cli                          # REPL
oc cli --prompt-file task.md    # one exchange, then exit
oc cli --session <id>           # continue a stored conversation
```

`oc cli --help` lists the REPL's own flags. The deployment flags (provider,
model, workspace, `--permission-mode`, `--skills-index`, `--memory`,
`--subagents`) are read by `omicsclaw.entry.resolve_app_config`; run it with
an unknown one to see the list it refuses.

`--permission-mode read-only` turns delegation off as a side effect, and
that is user-visible rather than internal: `task` cannot honestly declare
itself read-only — a sub-agent does whatever its own tools allow — so the
gate refuses it and every `task` call in that mode comes back as a
read-only refusal. Use the default mode when you want sub-agents.

The Textual TUI was **not** ported. A faithful port drags in twelve modules
that do not import, and keeping only the Textual skeleton would be a
rewrite rather than a port.


### Slash Commands (inside interactive session)

What the rebuilt REPL (`omicsclaw/entry/cli/`, reached by `oc cli`) answers.
The 38-row catalogue in `_constants.py` is the ported table, not the menu:
anything not listed here is answered with "not available in this build"
rather than being sent to the model as a question.

| Command | Description |
|---------|-------------|
| `/skills [domain]` | List indexed skills (optionally filter by domain) |
| `/sessions` | List recent conversations and say whether they are stored |
| `/resume [id\|number]` | Continue an earlier conversation; no argument opens an arrow-key picker (most recently active first, with each one's first question), or lists them when stdin is not a terminal |
| `/current` | Show the current session id and workspace |
| `/new` | Start a new conversation |
| `/clear` | Same as `/new`: a conversation with no history |
| `/compact` | Summarize this conversation now, keeping the recent messages |
| `/plan`, `/tasks` | Show this conversation's plan and task statuses (read-only) |
| `/auto [on\|off\|status]` | Stop asking about ordinary tool calls — now, and for the next `oc cli` start (writes `OMICSCLAW_CLI_PERMISSION_MODE` to `.env`; `oc channel` / `oc desktop` are unaffected). Dangerous commands, `ask` rules and changes to `.omicsclaw/` or `.env` are still asked. Typed at an approval card, it also allows that card |
| `/usage` | Show accumulated input/output tokens |
| `/mcp` | Report the MCP servers this deployment connected |
| `/help` | List these commands |
| `/exit` | Quit OmicsClaw (aliases: `/quit`, `/q`) |

Two non-slash prefixes:

| Prefix | Description |
|---------|-------------|
| `!<cmd>` | Run a shell command in the workspace, bypassing the model and the approval gate; the record is prefixed to the next question. Bounded by `_shell.SHELL_TIMEOUT_S` (60 s) — a separate number from `tool_timeout_s`, because a person is waiting for this one. |

Approval cards take three grants: `y` allows once; `s` stops asking about
that **tool** for the rest of the conversation without writing anything; `a`
writes an `allow` rule for that **exact call** into
`<workspace>/.omicsclaw/settings.json`. Anything else denies, and whatever was
typed becomes the denial reason.

A card shows the tool, its risk and the reason it was asked. The reason
quotes the call where its writer can: the whole `bash` command, an edit's
diff, a URL or search query, an MCP preview. Where it does not — a
dangerous-command match, a rule, a tool's policy, `write_file`, an edit too
large for a diff, an MCP preview that was cut — the arguments follow as
indented JSON with credential-named values hidden. The writer of the reason
declares which (`ApprovalRequest.reason_shows_call`); nothing is inferred by
searching the text. The CLI and every Channel print the same card
(`entry/render.py`), made inert by `entry/display.py`: control and format
characters (ESC, C1, bidi, zero-width) are shown as `\uXXXX`, every line
after the first starts with `│` so none can pass for another card, and runs
of lines holding only spaces and tabs fold to one. The body — reason and
arguments together — is bounded at 400 lines or 12,000 characters
(`MAX_APPROVAL_BODY_*`); a cut line ends in `…`, and a tall, folded or cut
body notes the original's line and character counts on its first line,
which the CLI repeats at the prompt (`approval_body_note`). The card is
shown and never logged.

`s` never answers a question the gate marks `ask_every_time`: a
dangerous-command pattern, an explicit `ask` rule, or a change to a file that
decides what OmicsClaw asks about — those cards print their own legend and `s`
there allows the one call. Changing anything under `.omicsclaw/`, or any
`.env` file, is asked about in every mode but `bypass-all`: a tool that can
write the rule file can write its own next `allow` rule, and one that can
write `.env` can set `OMICSCLAW_PERMISSION_MODE=bypass-all` for the next start
(or point `LLM_BASE_URL`, and the API key, elsewhere). `s` is shared with the sub-agents the conversation delegates
to, and `/resume` brings a conversation's grants back with it.

**What `s` on `bash` means**: for the rest of the conversation `bash` runs
unasked unless a dangerous-command pattern matches, and those patterns are a
deny-list that `python -c "import shutil; …"` walks past — the same posture as
`--permission-mode auto-approve`. The real boundary is the sandbox
(`OMICSCLAW_SANDBOX=docker`). An MCP tool whose argument is not called
`command` gets no danger check at all, so `s` on it opens it fully. See
[plan 0049](docs/plans/0049-session-grant-covers-the-tool.md).

`/plan` and `/tasks` are read-only by decision: the agent decides when a job is
worth planning, so there is no `/approve-plan`, `/resume-task` or
`/do-current-task`. `/run`, `/doctor`, `/context`, `/memory` and the extension
commands belong to families that are each a step of their own.

Sessions live in `<workspace>/.omicsclaw/memory.db`. `SqliteSessionStore.list`
filters nothing — the database file is the only isolation boundary — so a
multi-user surface must not share one file and offer `/resume`.

### MCP servers

Servers are declared in `<workspace>/.mcp.json` and connected by
`open_app(config)` **before** the tool registry is built, so their tools are
in the tool snapshot and the context budget from the first turn. They join
the registry as `mcp__{server}__{tool}` and the main loop runs them with no
special case.

Both transports are supported: stdio and Streamable HTTP. A server that
fails to connect is logged and left out rather than failing start-up.

Two rules worth knowing before adding one:

- **Every MCP call asks for approval** in the default permission mode. The
  card says where the call goes and previews its arguments on one line: at
  most 1,000 characters, control characters escaped, values under
  credential-named keys (`token`, `api_key`, `password`, …) hidden. When
  that preview is cut, the arguments follow it as indented JSON under the
  same redaction. A remote server is a way for data to leave this machine.
  The arguments are shown on the card and never logged.
- **Stdio servers inherit a minimal environment**, so API keys and bot
  tokens stay out of third-party processes.

`/mcp` inside the REPL reports what this deployment actually connected.
There is no `oc mcp add`; edit `.mcp.json`.


### Session Persistence

The rebuilt REPL stores conversations in `<workspace>/.omicsclaw/memory.db`
(SQLite), beside the long-term memory entries — one file per workspace, not one
per machine user. History survives a restart and `oc cli --session <id>` or
`/resume <id>` continues it. With `memory` switched off there is no database and
conversations are held in memory only; `/sessions` says which of the two this
deployment is.

The legacy surface used `~/.config/omicsclaw/sessions.db` — one file per
machine user rather than per workspace. That surface has been deleted; the
path is named here only so an old database found on a dev box is
recognisable for what it is.

### Dependencies

```bash
pip install -e .                  # rich, openai, anthropic: `oc cli` runs
pip install -e ".[channels]"      # Telegram and Feishu SDKs
```

`prompt-toolkit` (REPL line editing) and `fastapi` / `uvicorn` (`oc desktop`)
come from `environment.yml`. Without `prompt-toolkit` the REPL falls back to
plain line input.

Neither vendor SDK is required to run the test suite: both provider adapters
import theirs lazily inside a client factory, and no test may need one.

### Provider Runtime Contract

`LLM_PROVIDER=custom` must honour `LLM_BASE_URL`, `OMICSCLAW_MODEL` and
`LLM_API_KEY`. An explicit `--provider` / `--model` wins over the
environment. A malformed custom endpoint must produce an actionable
diagnostic rather than `(no response)`.

## Safety Boundaries

1. **Local-first**: no data upload. `omicsclaw/tools/_websafety.py` is the
   network half of that rule — scheme allow-list, userinfo rejection, DNS
   checked against 14 CIDR ranges with every resolved address judged,
   fail-closed on lookup failure, re-checked on every redirect hop, and the
   socket pinned to the address that was validated.
2. **Disclaimer required**: every report must carry the OmicsClaw
   disclaimer — research and educational tool, not a medical device.
3. **No hallucinated science**: every parameter traces to a `SKILL.md` or a
   cited tool.
4. **Permission gate**: `omicsclaw/permission/` decides whether a tool call
   happens, from a rule file at `<workspace>/.omicsclaw/settings.json` plus
   the session's `--permission-mode`. 28 built-in patterns escalate a
   dangerous shell command to an approval prompt that says why, five of them
   for data **leaving** the machine (`scp`, remote `rsync`, `ssh`, `curl`
   uploads). `require_approval` fails closed.
5. **Workspace containment**: the file tools resolve every path through
   `omicsclaw/tools/_workspace.py`, which refuses an escape by comparing
   path components and refuses a credential path even inside the workspace.
