# AGENTS.md — OmicsClaw Guide for AI Coding Agents

This guide is for AI coding agents working on the OmicsClaw codebase.

## Repository Working Contract

Before any complex repository maintenance, feature, or refactor task, read
`README.md` first for project context and prior decisions. Then read this
`AGENTS.md`, root `SPEC.md`, and the directly relevant code/docs.

Core rules:

- Reply in the user's language, usually Chinese or English.
- Stay concise, practical, and execution-focused.
- For non-trivial changes, work from a concise plan, keep edits scoped, and
  verify claims with concrete commands or file inspections before reporting
  completion.
- When you make an important decision or complete a meaningful milestone,
  update `README.md` while preserving its existing structure.

## Project Overview

OmicsClaw is a multi-omics analysis platform supporting 96 registered skills
across 8 domains: spatial transcriptomics, single-cell omics, genomics,
proteomics, metabolomics, Bulk RNA-seq, orchestration, and literature. Each
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

# Lightweight alternative (Python-only skills, no R or external CLIs):
# pip install -e .
# pip install -e ".[interactive]" / ".[tui]" / ".[memory]" / ".[channels]" / ".[full]"

oc cli                     # terminal REPL
```

> **`oc` short alias**: After installing OmicsClaw (either path), both
> `omicsclaw` and `oc` commands are available system-wide via the
> `[project.scripts]` entry in `pyproject.toml`.
>
> **Dependency source of truth**:
> - **Python deps** live in `pyproject.toml` (used by both install paths).
> - **R packages, bioinformatics CLIs, build toolchain** live in
>   `environment.yml` (conda path only).
> - **GitHub-only R packages** are installed inline by `0_setup_env.sh`
>   Tier 3 (`devtools::install_github` for spacexr, CARD, CellChat, numbat,
>   SPARK, DoubletFinder).
> - **Optional analysis backends** (cellrank, palantir, scvelo, tangram-sc,
>   …) are catalogued per domain in `skills/<domain>/_lib/dependency_manager.py`
>   `DEPENDENCY_REGISTRY` (canonical PyPI name → module + install_cmd). This is
>   the SSOT for backend name mapping; new algorithms register here.
> - **Per-skill `requires:` frontmatter** is generated/checked from the real
>   import surface by `scripts/audit_skill_requires.py` (`--check` in CI,
>   `--write` to regenerate). Never hand-edit it to "fix" a missing backend —
>   register the backend and run `--write`. See CONTRIBUTING.md.
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
a surface's own flags go after it.

| Command | Purpose |
|---------|---------|
| `oc cli` | Terminal REPL — the default way to use OmicsClaw |
| `oc cli --prompt-file <f>` | One exchange, non-interactive |
| `oc cli -- --session <id>` | Continue a stored conversation |
| `oc desktop` | HTTP backend for the OmicsClaw-App client |
| `oc channel` | Instant-messaging adapters (Telegram, Feishu) |
| `oc <surface> --help` | That surface's own flags |
| `python -m pytest -v` | Deterministic fast suite (excludes demo/slow/eval) |
| `make test` / `test-slow` / `test-all` | Fast / scientific / everything-but-eval |
| `make install-oc` | (Re)install package + activate `oc` alias |

There is **no `oc run <skill>`**. The skill runner and the other 33
subcommands lived in `omicsclaw/surfaces/cli/_main.py`, which the framework
rebuild retired; see "Running a skill" below for what replaced it.

> **Stale Makefile targets.** `make demo`, `demo-all`, `demo-bulkrna`,
> `demo-orchestrator`, `list`, `catalog`, `bot-telegram`, `bot-multi`,
> `bot-list` and `memory-server` still call `omicsclaw.py run|list`,
> `omicsclaw.py memory-server` or `python -m omicsclaw.surfaces.channels`.
> None of those entry points exists any more. Fixing the Makefile is
> outstanding work; do not treat a green target list as evidence.

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
│   ├── entry/          Composition root, sessions, turns, events, approval,
│   │                   plus the cli/, desktop/ and channel/ facades.
│   ├── launch/         `oc` argv grammar; picks a surface and builds the app.
│   │  ── kept from the old stack ──
│   ├── common/         Shared science helpers: report, checksums, runtime_env,
│   │                   workspace. 96 skill scripts import these. NOT legacy.
│   ├── core/           R script runner, dependency managers. Same: NOT legacy.
│   ├── autoagent/      Autonomous coding agent. Kept for a later migration
│   │                   of its ideas; does not import today.
│   ├── runtime/        Only consensus/, workflow/ and output_styles.py remain.
│   │                   Kept for a later migration; consensus.run is broken.
│   ├── remote/         SSH remote execution. Imports.
│   ├── attachments/    Immutable attachment store. Imports; the store half
│   │                   needs the deleted control plane.
│   ├── routing/        Orchestrator routing. Does not import.
│   ├── surfaces/       The old three surfaces + the 35-subcommand CLI. Kept
│   │                   as read-only reference; does not import.
│   └── diagnostics.py  Old `oc doctor`. Does not import.
├── skills/             96 skills across 8 domains, each a SKILL.md plus scripts
│   ├── spatial/ singlecell/ genomics/ proteomics/ metabolomics/ bulkrna/
│   ├── orchestrator/ literature/
│   └── <domain>/_lib/  Domain-shared utilities, not registered as skills
├── tests/              schema/ provider/ engine/ tools/ context/ skills/ entry/
│                       mcp/ memory/ permission/ planning/ launch/ sandbox/
│                       hooks/ observability/ are the rebuilt stack's suite
├── docs/FRAMEWORK-REBUILD.md   Living status of the rebuild — read this first
├── docs/plans/         Numbered plans, one per rebuild step
├── SOUL.md             Persona used by the Channel surface
├── SPEC.md             Repository maintenance + AI development contract
├── CLAUDE.md           Agent routing instructions (Claude Code entry)
└── AGENTS.md           This file
```

**Five packages are kept but do not import**: `autoagent`, `routing`,
`surfaces`, `diagnostics.py` and `runtime/workflow` all reach
`omicsclaw.skill` or `omicsclaw.providers`, which the rebuild deleted.
Their source is intact and readable, which is the point of keeping them —
but never cite one as working prior art without importing it first.

> **Import convention**: domain-specific skill utilities live in
> `skills/<domain>/_lib/` and are imported as
> `from skills.<domain>._lib.<module> import <name>`. A directory starting
> with `_` is never a skill. The `omicsclaw/` package holds only
> domain-agnostic framework code.

## Skill Architecture

Every skill has a `SKILL.md` with YAML frontmatter + methodology, a Python
script accepting `--input`, `--output`, `--demo`, and optionally `tests/`
and `data/`.

### Running a skill

`oc run <skill>` is gone. A skill script is now invoked **directly**, by a
person or by the agent through `bash`:

```bash
python skills/<domain>/<skill>/<script>.py --input <file> --output <dir>
python skills/<domain>/<skill>/<script>.py --demo --output /tmp/<skill>_demo
```

`omicsclaw/skills/` puts a one-line catalogue of all 96 into the system
prompt and lets the model fetch one body with `use_skill`; the model then
runs the script itself. What was lost with the old runner is the
deterministic half — the `result.json` envelope check, the run receipt, the
replay capsule and the output-directory claim. Do not describe those as
current behaviour.

`scripts/generate_skill_md.py` and `scripts/generate_routing_table.py` both
import the deleted `omicsclaw.skill`, so **SKILL.md files cannot be
regenerated today**; edit them by hand and treat "generated from skill.yaml"
in older docs as historical.

### Skill Metadata Rules

`skill.yaml` is the machine-contract source for a skill's metadata —
canonical name, aliases, allowed flags, `saves_h5ad`, param hints. Rules
that still hold:

- `security` is omitted until its three fields have been deliberately
  reviewed. An explicit block is a declarative capability statement
  propagated to audit surfaces, not proof of OS confinement.
- `resources.compute`, when calibrated, must carry the complete reservation
  (`cpu_cores`, `memory_mib`, `gpu_devices`, `threads`,
  `temporary_disk_mib`). Do not invent defaults. These are not OS-enforced
  quotas.
- `lifecycle.status: deprecated` requires one different canonical
  `superseded_by` skill that is `mvp` or `stable`; a non-deprecated skill
  must omit `superseded_by`.
- Every primary skill script must expose a lightweight direct `--help`.
- `interface.outputs.files` is an inventory, not a promise. Do not turn an
  optional entry into an unconditional one.

Rules that **lapsed with the shared runner** and are kept here only so
nobody re-derives them from an old document: the `result.json` envelope
check, `reproducibility/replay.json` + `environment.json` + `replay.sh`,
the generated top-level `README.md`, and the routing block that hid a
deprecated skill. Nothing enforces any of them today.

## How to Add a New Skill

1. `cp -r templates/skill skills/<domain>/<your-skill-name>`, then rename
   and fill the placeholders.
2. Fill in `SKILL.md` — including a worked `python skills/.../<script>.py`
   invocation, because that is now the only way anyone learns the CLI.
3. Add the Python script, accepting `--input`, `--output`, `--demo`.
4. Add tests under the skill's own `tests/`.
5. Add the test path to `pyproject.toml`'s `[tool.pytest.ini_options]
   testpaths` if it should run in the default suite.

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
  tests/observability -p no:cacheprovider -q -o addopts=""
# 4412 passed, 10 skipped
```

Treat that as the regression signal. `tests/` also still holds suites for
the kept-but-not-importable packages (`tests/test_autoagent_*.py`,
`tests/surfaces/`, `tests/runtime/`, `tests/bot/`); those do not collect and
are not a signal about your change either way.

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

These are a **port** of `omicsclaw/surfaces/`, not a rewrite. When a
behaviour looks odd, the old file is still on disk and is the reference --
but it does not import, so read it rather than running it.

### Desktop surface

```bash
pip install -e ".[desktop]"
oc desktop            # 127.0.0.1:8765 by default
```

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
oc channel -- --channels telegram
oc channel -- --channels feishu
```

Telegram and Feishu are the cut-over adapters; the rest stay gated. Several
channels in one process share one `ControlRuntime`.

Required environment, beyond the provider keys:

- `TELEGRAM_BOT_TOKEN` — from @BotFather.
- `FEISHU_APP_ID` + `FEISHU_APP_SECRET` — from the Feishu dev console.
- `FEISHU_ALLOWED_SENDERS` — comma-separated owner `open_id` values.
  **Required**: ingress admits nobody else and refuses to start without it.
- `FEISHU_BOT_OPEN_ID` — this bot's own `open_id`. Optional, but group chats
  fail closed without it, because a group @-mention cannot otherwise be
  attributed to this bot rather than to another mentioned human.

A sender outside the allow-list produces **no turn at all**, not a polite
refusal. The persona every adapter shares is `SOUL.md`; per-platform
configuration goes in `.env` at the project root.

### CLI surface

```bash
oc cli                          # REPL
oc cli --prompt-file task.md    # one exchange, then exit
oc cli -- --session <id>        # continue a stored conversation
```

`oc cli --help` lists the deployment flags (provider, model, workspace,
`--permission-mode`, `--skills-index`, `--memory`); `oc cli -- --help`
lists the REPL's own.

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
| `/resume [id\|number]` | Continue an earlier conversation; no argument lists them |
| `/current` | Show the current session id and workspace |
| `/new` | Start a new conversation |
| `/clear` | Same as `/new`: a conversation with no history |
| `/compact` | Summarize this conversation now, keeping the recent messages |
| `/plan`, `/tasks` | Show this conversation's plan and task statuses (read-only) |
| `/usage` | Show accumulated input/output tokens |
| `/mcp` | Report the MCP servers this deployment connected |
| `/help` | List these commands |
| `/exit` | Quit OmicsClaw (aliases: `/quit`, `/q`) |

Two non-slash prefixes:

| Prefix | Description |
|---------|-------------|
| `!<cmd>` | Run a shell command in the workspace, bypassing the model and the approval gate; the record is prefixed to the next question. Bounded by `_shell.SHELL_TIMEOUT_S` (60 s) — a separate number from `tool_timeout_s`, because a person is waiting for this one. |

Approval cards take three grants: `y` allows once, `s` allows that exact call
for the rest of the conversation without writing anything, `a` writes an
`allow` rule into `<workspace>/.omicsclaw/settings.json`. Anything else denies,
and whatever was typed becomes the denial reason.

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

- **Every MCP call asks for approval**, showing the arguments and where they
  go. A remote server is a way for data to leave this machine.
- **Stdio servers inherit a minimal environment**, so API keys and bot
  tokens stay out of third-party processes.

`/mcp` inside the REPL reports what this deployment actually connected.
There is no `oc mcp add`; edit `.mcp.json`.


### Session Persistence

The rebuilt REPL stores conversations in `<workspace>/.omicsclaw/memory.db`
(SQLite), beside the long-term memory entries — one file per workspace, not one
per machine user. History survives a restart and `oc cli -- --session <id>` or
`/resume <id>` continues it. With `memory` switched off there is no database and
conversations are held in memory only; `/sessions` says which of the two this
deployment is.

The legacy surface used `~/.config/omicsclaw/sessions.db`; that path belongs to
`omicsclaw/surfaces/cli/`, which does not import today.

### Dependencies

```bash
pip install -e ".[interactive]"   # prompt_toolkit REPL
pip install -e ".[desktop]"       # FastAPI backend
pip install -e ".[channels]"      # platform SDKs
```

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
