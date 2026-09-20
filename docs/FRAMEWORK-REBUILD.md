# Framework rebuild — status and handoff

A living status document for the staged rebuild of OmicsClaw's agent
framework. Read this first if you are picking the work up mid-stream.

**Last updated: 2026-09-20. Steps 1 through 7 are complete; step 6.11
(`omicsclaw/observability/`, plan 0043) is the most recent addition — the
span tree, the six instruments and an optional OpenTelemetry exporter,
built without adding a seam to the engine. `tests/observability/` = 244
passed, plus 16 on the wiring. Before it, step 6.10
(`omicsclaw/hooks/`, plan 0042) shipped the
tool-call interception seam, plus the audit hook that plan 0031 Q13
deferred. Measured after that step: `schema provider engine tools context skills
entry mcp memory permission planning launch sandbox hooks` = **4,068
passed, 9 skipped**. Before it, step 6.9
(`omicsclaw/planning/`, plan 0039) had landed — the
execution plan the agent keeps outside the conversation and is shown again
before every model call, so a long task survives its own compaction. The
engine gained one optional seam for it (`TurnAugmentor`), consulted after
the compactor and able only to append to the call being made. That step's
own measurement (`schema provider engine tools context skills entry mcp
memory permission planning launch`) was **3,679 passed, 7 skipped**.
What is left before this replaces the old stack: the migration that retires
`omicsclaw/surfaces/`.**

> ⚠️ **Several sessions write this tree at once.** Step 6.9's parity
> evaluation reported six regressions that did not exist; both evaluations
> independently traced them to an unrelated, half-wired
> `omicsclaw/entry/memory.py` another session had left untracked, with a
> real circular import that makes test collection order-dependent. Before
> reading a red suite as evidence about your own change, isolate it.

## Why this rebuild exists

The pre-existing agent framework works but is redundant and tightly
coupled. The owner's decision (2026-09-16) is to rebuild it component by
component rather than refactor in place, taking the layer structure from
a Go reference harness at `/workspace/dataset/private/zhouwg_data/harness9`.

Two rules govern the whole effort. Both have already caught real problems,
so treat them as load-bearing, not ceremony:

1. **One component per step.** A step may create files only inside its own
   new package and its own test directory. Touching a pre-existing file is
   out of scope by default — `git status --porcelain` showing an
   unexplained ` M ` is itself a defect. This is what keeps the boundaries
   real.
2. **Implementation and evaluation are separate agents.** The agent that
   wrote the code does not judge it. Evaluation is read-only: it reports
   findings, and repairs are dispatched as their own task afterwards.

## Target layer structure

Taken from harness9's `internal/`, where `schema` is a flat peer of
`engine`, `provider`, and `tools` — never nested inside one of them.

```
omicsclaw/
├── schema/     ✅ step 1 — the unified contract every layer exchanges
├── provider/   ✅ step 2 — the model adapter layer
├── engine/     ✅ step 3 — the ReAct Main Loop
├── tools/      ✅ step 4 — Tool Registry + adapters; 4.5 — the foundation tools
├── context/    ✅ step 5 — prompt assembly, budget, compaction
├── skills/     ✅ step 5.6 — the Skill loader (plural; the singular is gone)
├── entry/      ✅ step 6 — composition root, sessions, turn, events, approval, 3 surfaces (plan 0031)
├── mcp/        ✅ step 6.5 — MCP client: .mcp.json, stdio + Streamable HTTP (plan 0034)
├── memory/     ✅ step 7 — session state + long-term recall (plan 0033)
├── planning/   ✅ step 6.9 — the execution plan the agent keeps (plan 0039)
├── sandbox/    ✅ step 6.7 — Docker isolation for `bash`, stdlib-only leaf (plan 0036)
├── permission/ ✅ step 6.8 — HITL permission control: rules, modes, danger patterns (plan 0038)
├── hooks/      ✅ step 6.10 — tool-call interception seam + the audit hook (plan 0042)
└── observability/ ✅ step 6.11 — spans, metrics, optional OTEL (plan 0043)
```

`observability/` is the one layer here that is **not** a leaf and says so:
it imports `schema`, `provider`, `engine` and `hooks`, and none of the
four import it — the same one-way shape `internal/observability` has. It
is also the one step that added **no seam to the engine**. The reference
must: a Go loop can only be watched by being called back, so
`internal/engine/observer.go` declares a four-method `EngineObserver`.
This rebuild's loop already publishes those moments as `EngineEvent`, so
the observer consumes an existing stream and `omicsclaw/engine/` is
unchanged — which is what keeps its own "no I/O, no logging" convention
true now that a telemetry layer exists.

`hooks/` is the seam and **not** the four policies the reference bundles
with it. harness9's `internal/hooks` ships one mechanism plus permission,
danger patterns, output offload and plan persistence; three of those four
already have homes in this tree (`permission/`, `context/`'s `Offloader`,
`planning/`), so step 6.10 built the mechanism and the one hook nobody
owned — observability, which plan 0031 Q13 deferred by name. A hook
decorates a **tool**, like the permission gate and for plan 0038 §2's
reason, and the chain is composed *inside* the gate, matching the
reference's chain order.

**`omicsclaw/skill/` — the legacy 40-module skill system — was deleted by
the owner on 2026-09-19.** `omicsclaw/skills/` is the only skill loader.
One casualty worth knowing about because it broke *every* test in the
repository rather than a subset: the root `conftest.py` had an autouse
fixture importing `omicsclaw.skill.resource_scheduler`, so collection
failed everywhere. The fixture is removed — it had nothing left to
isolate.

`skills/` is a peer rather than a part of `context/`, which is where the
reference harness puts the equivalent knowledge — its `internal/context`
imports `internal/skills` directly. Splitting them keeps both leaves: the
loader renders text, the assembly layer places text, and neither imports
the other. A composition root joins them in one line.

`sandbox/` shipped as step 6.7 (plan 0036), through the seam step 4.5
laid down: the tool layer declares `BashEnvironment`, the sandbox package
satisfies it structurally and imports no other `omicsclaw` package, and
only `entry/` knows both. Only `bash` is routed into the container — the
file tools keep their own boundary (`Workspace`) on the host, see below.

⚠️ The bubblewrap isolation under `omicsclaw/autonomous/` and
`omicsclaw/skill/execution/` belongs to the **old architecture being torn
down** (owner, 2026-09-18). Do not reuse it and do not treat it as prior
art for this layer.

Dependency direction is one-way: every layer may import `schema`;
`schema` imports nothing. `provider` imports `schema` and its vendor SDK
and nothing else.

`engine` was taken and had to be evicted first — see step 3 below. The
same problem is still waiting at step 7: `omicsclaw/memory/` **exists and
is live** (28 modules, the graph memory system). Do not assume the name is
free, and check whether its `__init__.py` can even be imported in this
environment before planning around it — that is what settled `engine`.
`skill` did not need settling in the end: the owner deleted it.

## What shipped

### Step 1 — `omicsclaw/schema/` (ADR 0077)

441 lines, 8 types, standard library only. `import omicsclaw.schema`
loads 5 modules in ~9 ms.

```
Message  Role  ToolCall  ToolResult  ToolDefinition  Usage
StreamChunk  StreamChunkType
```

The ReAct moves are fields, not conventions: **Thought** is
`Message.reasoning_content`, **Action** is `Message.tool_calls`,
**Observation** is `ToolResult`. `Message.is_action` is the single branch
the Main Loop turns on.

Decisions worth not re-litigating:

- **Top-level, not under `runtime/`.** Built there first and moved after
  measuring: 62% of the 45 message-payload consumer files live outside
  `runtime/`, `providers/` importing back out of it is a hard import
  cycle, and the nested path cost 166 modules / ~150 ms per import versus
  5 / ~9 ms now.
- **Vendor-neutral.** No vendor field name appears in the package. An
  earlier draft made `Message` OpenAI-wire-shaped with `to_wire()` /
  `from_wire()`; that was reversed, because the stated goal is precisely
  that vendor formats differ and the system needs its own standard.
- **`ToolCall.arguments` stays unparsed JSON text.** Byte-exactness
  matters for prompt-prefix caching and replay evidence.
  `parsed_arguments()` returns `{}` rather than raising, so a truncated
  stream costs one turn instead of the run.
- **Four roles including `tool`**, and **`reasoning_content` persisted** —
  both deliberate deviations from harness9, which has three roles and
  discards thinking after streaming it. The second is required: several
  thinking endpoints reject a conversation whose historical assistant
  turns have lost it.
- **Deliberately excluded** to keep step 1 small: `AgentStep` /
  `Trajectory` / `StopReason` (drafted, then removed — they are Main Loop
  vocabulary and their shape should be decided when the loop is written),
  multimodal content parts, and `SubAgentUpdate`.

### Step 2 — `omicsclaw/provider/` (plan 0026)

~2,800 lines across 7 modules, ~3,900 lines of tests.

```python
from omicsclaw.provider import provider_from_env, provider_for, LLMProvider

llm = provider_from_env()                    # detect backend from env
llm = provider_from_env("anthropic")         # pin the backend
titler = provider_from_env(model="claude-haiku-4-5", max_tokens=64)
```

The interface takes **only** the conversation and the turn's tools:

```python
async def generate(messages, tools=None) -> Completion
def generate_stream(messages, tools=None) -> AsyncIterator[StreamChunk]   # not async def
def bind(**overrides) -> LLMProvider
```

Model, temperature, `max_tokens` and thinking budget are absent from the
signature on purpose — they live on the instance in `ProviderConfig`, so
the Engine cannot acquire model configuration: there is nowhere to put
it. Per-request variation goes through `bind()`.

`tools=None` **strips every tool** rather than meaning "use the default
set". That is how a separated Thinking phase works without a new
interface — pass no tools and the model must reason. An adapter that
substitutes a default list breaks the phase switch.

Two adapters — `OpenAIProvider` (covers DeepSeek, Ollama, OpenRouter and
10 more of the 13 presets) and `AnthropicProvider`. The dialect is carried
on `ProviderPreset.dialect`, not in a table beside the factory: a parallel
table fails *silently* when someone adds a preset and forgets it. Dialect
follows the **endpoint**, never the model name — OpenRouter's default
model is `anthropic/claude-sonnet-4.6` and it still speaks Chat
Completions.

The layer exceeds harness9 on six counts, five of which plan 0026 §5
originally mis-credited as ports: tool-result batching, the cache-read
repair in usage accounting, system-prompt joining, persisted
`reasoning_content`, full JSON-Schema passthrough for tools, and ADR 0024
`cache_control` breakpoints.

### Step 3 — `omicsclaw/engine/` (plan 0027)

~1,500 lines across 6 modules, the ReAct loop that moves step 1's types
using step 2's adapters. `tests/schema/ tests/provider/ tests/engine/` =
**635 passed**.

```python
from omicsclaw.engine import AgentEngine, EngineConfig

engine = AgentEngine(provider, tools, EngineConfig(max_turns=50))
result = await engine.run(messages)               # RunResult
async for event in engine.run_stream(messages):   # EngineEvent
    ...
```

Decisions worth not re-litigating:

- **The name had to be taken by force.** The legacy `omicsclaw/engine/`
  was not merely occupied, it was *unimportable* here: its `__init__.py`
  eagerly imports its `loop.py`, which imports the `openai` SDK at module
  scope. So `omicsclaw.engine.<anything>` raised `ModuleNotFoundError` in
  the rebuild's own test environment, and even with the SDK present the
  new layer would have dragged in the whole legacy agent stack. It moved
  to `omicsclaw/runtime/engine/` — the boundary AGENTS.md already assigns
  it, and where it already behaved: it imports eight symbols from
  `omicsclaw.runtime.*`, so the move turned a cross-package cycle into an
  intra-package one.
- **Conversation in, conversation out** — not harness9's `userPrompt
  string`. There is no Session until step 6 and half of one was not worth
  inventing. `RunResult` also keeps the trajectory when the turn ceiling
  is hit; harness9 discards it.
- **Three `StopReason` values, and the absences are the point.** No
  `ERROR`, no `CANCELLED`: failures raise and `CancelledError` propagates
  untouched, so neither is a return value. `AgentStep` and `Trajectory`
  stayed dropped — the trajectory *is* `RunResult.messages`.
- **Everything raises; there is no error event.** harness9 needs
  `EventError` because a Go channel cannot carry an exception; an async
  generator re-raises at the consumer's `async for`. `StreamChunkType.ERROR`
  stopped being dead by *conversion* — the loop turns one into a raised
  `ProviderError`.
- **`ToolExecutor` is a two-method Protocol with no implementation.**
  Step 4 satisfies it structurally, without importing `omicsclaw.engine`.
  But dispatch *policy* — concurrency, per-tool timeout, result ordering —
  lives here, as `tools_exec.go` does in harness9.
- **One declared schema amendment**: `StreamChunk.finish_reason`, so a
  stream truncated by the output ceiling stops being indistinguishable
  from a model that finished. ADR 0077 carries the amendment note.

**Two independent read-only evaluations gated the step** (correctness, and
harness9 parity) and both found real defects, which were then repaired as
their own task. They independently converged on the same two — proof the
gate is not ceremony. Plan 0027 appendix B records the outcome, including
**five errors in the plan itself**; the one worth carrying forward:

> Structure ported from the reference harness is an asset. **Literals
> ported from it are a liability.** Trap 12's transient-network marker
> list was copied verbatim from Go (`x509:`, `dial tcp`, `no such host`)
> and matches *nothing* either Python SDK raises, so the wide retry budget
> was unreachable — a defect the plan introduced and the implementer
> faithfully built. Re-verify every borrowed literal in the target
> language.

### Step 4 — `omicsclaw/tools/` (plan 0028)

10 modules including three reference tools, `tests/tools/` = **315
passed**; all four directories = **950 passed**, with steps 1–3's 635
untouched. Purely additive: the legacy tool layer was not moved and not
edited.

> **The three reference tools were removed on 2026-09-18** (owner), once
> step 4.5's `read_file` / `write_file` / `bash` carried every property
> they were built to prove. They were evidence, not product: a tool
> wrapped from a bare callable, a tool whose arguments a model will get
> wrong, and a tool needing a workspace, a human's consent and somewhere
> to report progress. The foundation tools demonstrate all three while
> also being the hands the agent actually works with, so keeping a
> demonstration beside the real thing bought nothing. Nothing was lost
> with them — see plan 0029's `builtin/__init__.py` for which property
> moved where.

```python
from omicsclaw.tools import ToolRegistry, FunctionTool, ToolPolicy

registry = ToolRegistry()
registry.register(tool, ToolPolicy(approval_mode=ApprovalMode.ASK))
defs = registry.available_tools()        # → provider, in registration order
result = await registry.execute(call)    # → ToolResult
```

`ToolRegistry` satisfies step 3's `ToolExecutor` structurally, without
importing `omicsclaw.engine`.

Decisions worth not re-litigating:

- **The owner cancelled the eviction.** Unlike step 3, `omicsclaw/tools/`
  was free, so renaming the legacy layer would have bought a greppable
  label rather than an unlock. The boundary is enforced by an AST
  layering test instead — see the lesson below, because the first version
  of that test had a hole.
- **Tool-list order is registration order**, deliberately unlike
  harness9, whose `GetAvailableTools` documents that order is
  unspecified. The reason is vendor prompt-prefix caching, and it is not
  an appeal to vendor docs: step 2's `_mark_last_tool` already writes its
  `cache_control` breakpoint onto `tools[-1]`, which only works if the
  list is stable.
- **Policy metadata hangs off the registry**, never on `ToolDefinition`,
  with a test asserting no policy field name survives into a prompt.
  Defaults are the **guarded** values (`HIGH`/`ASK`), not the convenient
  ones — an undeclared tool must not silently acquire full rights.
- **The out-of-band channel is `contextvars`**, with the convention
  written down rather than resting on the coincidence that
  `ensure_future` copies context. Three members: approval callback,
  progress sink, and a values bag replacing the legacy
  `context_params`. Approval is **fail-closed**; progress is a no-op when
  absent — and, after repair, also when the sink *raises*, because a
  broken transport must not turn a finished tool into a failure.
- **MCP naming is invented here, not preserved.** The plan claimed an
  existing convention to match byte-for-byte; there is none — `mcp__`
  appears once in the whole repo, as a read.

**Two independent read-only evaluations gated the step**, and the defects
they found clustered exactly where step 3 said they would: on the lane
seams no implementation task owned. Plan 0028 appendix B records the
outcome, including **20-odd errors in the plan itself**. The two worth
carrying forward:

> **"Has tests" is not "is wired up."** Q5 built a two-source policy with
> a precedence table and four passing tests — while *no production code
> read the resolved policy at all*, so a deployment tightening a tool to
> `ASK` was silently ignored and the tool self-approved. Any design that
> *resolves* a permission must have its acceptance criteria pin
> **resolution and effect**, and pin the effect in the **tightening**
> direction; a loosening test passing proves nothing.

> **Complementary blind spots are not a containment relation.** Skipping
> the eviction was argued on "the AST test is strictly stronger than a
> greppable name." True for static imports, false in reverse:
> `importlib.import_module("omicsclaw.runtime...")` is exactly what grep
> catches and AST does not — and the layering test was the *only*
> enforcement left. A lazy delegation to the legacy validator passed all
> 286 tests. **Static checks inspect spelling; only a behavioural probe
> inspects fact** — the repaired guard runs the real paths in a
> subprocess and *then* asserts no `omicsclaw.runtime*` is in
> `sys.modules`. **Steps 5 and 6 will copy this test; copy the repaired
> version.**

### Step 4.5 — `omicsclaw/tools/builtin/` (plan 0029)

Six tools on two boundaries, `tests/tools/` = **715 passed**. Purely
additive; nothing is wired to production.

```
read_file  write_file  edit_file  bash          ← _workspace.py + _pathlock.py
web_fetch  web_search                           ← _websafety.py + _html.py
```

The first four are the canonical set — what `cmd/harness9/main.go:275-278`
mounts, and what the two other harnesses plan 0029 appendix A compares
against arrive at independently. `web_fetch` and `web_search` were ruled
back into scope by the owner on 2026-09-18, reversing plan 0029 §2.

Decisions worth not re-litigating:

- **`edit_file` ports the four-level cascade, and the level it matched is
  part of the result.** Exact → ignoring line endings → ignoring
  surrounding whitespace → ignoring indentation, with a uniqueness guard
  at every level. Only an exact match is reported as authoritative,
  because L2–L4 can write bytes the model did not send — and the L4
  re-indentation is what stops a correct edit becoming an
  `IndentationError`. Suppressing that doubt is how a self-correcting
  agent stops correcting itself.
- **The approval carries the diff, not the arguments**, so the file is
  read before the prompt and **again** inside the write lock. A file that
  moved while the prompt was open is refused: what was approved was a
  diff against particular bytes. This is plan 0028's rule about resolving
  a permission, applied to a mutation.
- **Two guards the reference lacks**, both found by writing the tests
  against it. An empty anchor is refused by name, since `str.count("")`
  is `len + 1` in both languages and the model would otherwise be told to
  add context to something that has none. An **all-whitespace** anchor is
  refused too, and that one is a real gap: `edit_file.go:292` skips L3 for
  exactly this input, with the right reason in its comment, and guards
  only L3 — L4 then matches every blank line, so a file with exactly one
  has it silently replaced.
- **`_websafety.py` is a peer of `_workspace.py`, not a function in a
  tool.** Scheme allow-list, userinfo rejection, DNS fail-closed, and
  **every** resolved address checked rather than the first — a name with
  one public `A` record and one `127.0.0.1` is a rebinding attack with no
  timing requirement. 14 CIDR ranges: the reference's 8, plus `0.0.0.0/8`
  (`http://0.0.0.0:8080/` reaches this machine and is not inside
  `127.0.0.0/8`), IPv4 multicast and reserved, IPv6 loopback and
  unspecified, and `64:ff9b::/96` NAT64.
- **It pins the socket to the address it validated**, which the reference
  does not: harness9 checks the resolved addresses and hands the
  *hostname* to `http.Client`, which resolves it again. The connector on
  `http.client.HTTPConnection` is replaced per instance, so `Host` and
  TLS SNI still carry the hostname and certificate verification is
  unaffected — and the absence of that private attribute **raises**
  rather than silently falling back to an unchecked resolver.
- **Neither test seam can turn a check off.** `PinnedTransport` takes a
  `resolver` and an `opener`; harness9 instead makes the whole of
  `isSafeURL` replaceable so its tests can reach a local server, which is
  a safety check with an off switch.
- **The gate does not protect the rule that matters most, and says so.**
  `CLAUDE.md`'s first rule is that genetic data never leaves this
  machine; a blocklist of destinations cannot enforce it, because
  `https://example.com/?q=<identifier>` is a public address. That is
  carried by the `ASK` policy on both web tools and by approval prompts
  that show the whole URL and the whole query.
- **`web_search`'s risk level is `MEDIUM` where `web_fetch`'s is
  `HIGH`**, deliberately: risk follows blast radius, and one field to one
  fixed endpoint is a smaller radius than an arbitrary destination with
  an arbitrary path. `ASK` is unchanged on both, because risk level and
  approval mode answer different questions.
- **No readability port, and the gap is named.** `web_content.go` uses
  two third-party Go libraries; this layer may import nothing outside the
  standard library, so boilerplate removal is a fixed tag list rather
  than node scoring. On a documentation page the two are close; on a news
  site this returns more noise. `_html.py` says so.
- **`web_fetch` and `web_search` collide with the legacy names**, unlike
  `read_file`/`write_file`/`edit_file`, which were named away from
  `file_read`/`file_write`/`file_edit` so both layers could be mounted at
  once. The migration has to retire one side of each pair.

Literals re-verified rather than pasted: 16,000 / 45 s / 512 KiB /
0755 / 0644 / head-third-tail-two-thirds (step 4.5's first half), and now
3 context lines, 20 summary lines, 8,000 / 32,000 chars, 1 MiB, 5 results
/ 10 max, 15 s and 20 s, 5 redirects, 10 s dial. Two were **not**
carried: the reference's `harness9/1.0` user agent, which would
misattribute every request in somebody's access log, and its UTF-8
boundary backoff, which is unreachable in a language whose strings are
code points.

**Still true after this step: nothing here has spoken to a real HTTP
endpoint.** Every web test drives an injected transport or a fake opener
under the real gate. That is the same debt the provider adapters carry,
and step 3's evaluation showed its cost is not hypothetical.

#### One independent read-only evaluation gated it, and found 27 things

Every one was repaired as its own round, and the eight that mattered are
worth carrying forward because each is a *shape* of mistake rather than a
one-off:

1. **A prompt that showed a different URL from the one sent.**
   `urlsplit` silently strips `\t`, `\r` and `\n` **for parsing** while
   the raw string is what the human reads, so `?sample=\nHG00123`
   displayed as an empty query with an identifier on its own line looking
   like prose — in the one tool whose entire safety argument is "a person
   reads the URL". Control characters are now refused. **The lesson is
   general: when a human's reading is the control, what they read has to
   be the thing that happens.**
2. **307/308 re-sent the body and every header across origins.** The
   301/302/303 downgrade was there, with a comment giving the right
   reason, and the two statuses that *actually* cross hosts were not
   covered. Worse than the Go reference, which strips sensitive headers
   cross-domain. A cross-origin hop now drops the caller's headers and
   refuses outright rather than re-sending a body.
3. **Transport errors arrived as `is_error=True` with a raw exception
   name**, contradicting this layer's own docstring *and* the reference.
   A connection reset is the commonest real outcome of a web tool, and it
   is a fact about the world. Now `TransportFailed`, reported as output.
4. **`edit_file` said "the file is unchanged" after truncating it to
   zero.** `O_TRUNC` empties before the first byte is written, so an
   ENOSPC was silent data loss under a reassuring sentence. Now a
   temp-file-plus-`os.replace`, which makes the sentence true.
5. **The timeouts were per-socket-operation, not per-request.** A server
   dripping one byte inside the deadline held a request open forever, and
   redirects multiplied the budget by six — while the tests asserted
   arithmetic on constants, which is exactly the failure shape plan 0029
   §8 trap 6(b) was rewritten to avoid. Now one monotonic deadline across
   the whole call, and `read1` instead of `read`, because
   `BufferedReader.read` loops internally and a deadline checked between
   calls is never reached inside one. **The first fix for this was itself
   incomplete and the new test caught it.**
6. **Removing both of `edit_file`'s path locks left the whole suite
   green.** The concurrency test used the local path, where `_get`
   resolves without yielding to the loop, so the tasks never interleaved.
   Under any real `Environment` the mutant silently loses an update. The
   test now injects one that awaits.
7. **Dead code ported from Go**: a version guard before an `ipaddress`
   containment test (Python's `__contains__` already answers `False`
   cross-version), `_line_by_line`'s window guard (both arms subsumed by
   the scan below), and `SafeTarget.family` (stored, never read). All
   three are trap 15's category and all three were written *by* the agent
   that had just been told to look for them.
8. **Silent capability loss versus the legacy tools** — `file_edit`'s
   `replace_all`, `web_fetch`'s 100,000-character ceiling and its
   `markdownify` conversion, `web_search`'s `topic` enum and whole-page
   results. Plan 0029 §6's rule is "every row accounted for, a blank is a
   defect", and the rows for these tools were written before the tools
   were. They are now recorded in the modules that replaced them.

Also repaired: five docstrings that confidently described the reference
wrongly (including a claim that neither test seam could weaken a check —
false for `opener`, which is the thing that opens the socket), a
truncation notice that told the model it had seen more than it had, a
literal U+00A0 written as an invisible byte inside a regex, two helpers
of one name with opposite duplicate-attribute semantics, and seven
properties that were correct and unpinned — including the byte ceiling
that is the only thing between a hostile server and unbounded memory.

**The one refinement worth copying into step 5.** Aiming the evaluator at
*the docstrings* paid as well as aiming it at the code. This layer's
prose is dense and makes checkable claims — "the reference does X at
`file.go:NN`", "this is stricter than the reference", "Python cannot do
Y" — and a confidently wrong one is a real defect, because the next
person acts on it. Every `edit_file.go` / `web_*.go` line citation
survived that check; five of the interpretive claims did not.

### Step 5.6 — `omicsclaw/skills/` (plan 0032)

Six modules, `tests/skills/` = **416 passed**. The assembly layer
shipped a *slot* for a skills section and said outright that the
renderer lives outside it (plan 0030 §5.1); this is that renderer, and
step 6 below now fills the slot with it.

```python
from omicsclaw.context import Section
from omicsclaw.skills import load_skills, use_skill_tool

index = load_skills(workdir / "skills")      # absent directory → empty
assembler.with_section(Section("skills", "## Available skills", index.prompt_body))
registry.register(use_skill_tool(index))
```

Measured on this repository, because the numbers are what decide the
design: 96 `SKILL.md` files, index 29,849 characters (≈8.5k tokens),
bodies 437 KB (≈125k tokens), a full rescan 21 ms.

Decisions worth not re-litigating:

- **`skills` is not `skill`.** The legacy 40-module skill system keeps
  the singular name and is on the layering probe's forbidden list, with
  a test asserting the whitelist tells the two apart — one letter is the
  whole distinction and it would look unremarkable in a diff.
- **The whitelist is `schema` + `tools`**, wider than the reference's
  `schema` alone, because `use_skill` declares its own `ToolPolicy`.
  Leaving it to default (`HIGH`/`ASK`, approval fail-closed) would put a
  human prompt in front of every skill load. Notably **not** `context`:
  returning a `Section` from here would make two leaves depend on each
  other instead of on the root that joins them.
- **The scan recurses, and does not prune.** The reference reads one
  level of subdirectories; that finds **2 of the 96** here, where skills
  sit at three depths. The first implementation pruned at each
  `SKILL.md` found — and loaded **95**, because `skills/orchestrator/`
  is both a skill and the parent of `omics-skill-builder`. A ported
  convention is a liability the same way a ported literal is.
- **Order is the sorted relative path**, not the directory walk's. They
  differ whenever one directory name is a prefix of another with a
  separator between (`a-b/` before `a/c/`: `-` sorts before `/`), and
  the index's order is the prompt prefix's order.
- **The frontmatter parser is a stated YAML subset, checked against
  PyYAML on the real corpus.** The reference cuts each line at its first
  colon, which here reads the first line of a description and discards
  the rest — and the discarded part is the "Skip when … use
  <other-skill>" half, the one that prevents a wrong choice. 288
  parameterized assertions compare this module with `yaml.safe_load`
  key by key over all 96 headers. The package itself imports no YAML
  library, and a test blocks the import to keep it that way.
- **Skips are data, not a log line.** The reference `log.Print`s them;
  `SkillIndex.skipped` carries a reason enum instead, so "this tree
  loads cleanly" is assertable. A missing root is still silence (zero
  configuration), but a root that *exists and cannot be read* raises —
  the distinction is configuration versus discovery.
- **Two summaries, and truncation is not one of them.** `summary()` is
  the reference's format at ≈8.5k tokens; `domain_summary()` drops the
  descriptions at ≈600. Shortening a description is a cheaper index that
  routes worse.
- **The model's string never becomes a path.** `use_skill` looks a name
  up in a table of paths the loader wrote; `../../etc/passwd` finds
  nothing rather than reading something.
- **`use_skill` returns the skill's directory**, which the reference does
  not, because only **2 of the 96** bodies say where their own scripts
  live — without it the model gets a methodology and cannot find the
  script that implements it.

**Known limit, named rather than discovered later**: binding
`index.prompt_body` binds a *snapshot*, so a skill written mid-run by
`create_omics_skill` is invisible until a rescan. That contradicts what
`SectionSource` promises elsewhere ("what was written is visible on the
next turn"), so both shapes are pinned by tests and the closure that
rescans is documented at the wiring site.

Thirteen mutations, each confirmed to kill a named test — including the
pruning rule that had already cost a real skill, and the policy
declaration whose absence would turn every skill load into an approval
prompt.

### Step 6 — `omicsclaw/entry/` (plan 0031)

The top layer: the composition root, the prompt, sessions, the turn, the
typed event stream, approval — plus the three surface facades that
consume them. **17,899 lines**, delivered in two waves. Measured
2026-09-20: `tests/entry/` = **620 passed, 1 skipped** (the skip is the
HTTP smoke, which needs `fastapi`), and the rest of the rebuilt stack
(`schema provider engine tools context skills`) = **2,089 passed**.

The one pre-existing file this step touched is
`omicsclaw/tools/__init__.py`, which gained a single
`from ._workspace import Workspace` (plan 0031 Q15). `__all__` was **not**
extended — doing so turns `tests/tools/test_tools_is_a_leaf_layer.py`
red; the reason and the remedy are in that plan's Q15.

#### First wave — the Composer reaching the loop

`tests/entry/` was **196 passed** at this point. Two things landed here
beyond the wiring the entry layer already had.

**The three-tier prompt is complete.** `default_sections` had five
sections — persona (`SOUL.md`), project contract (`CLAUDE.md`), safety,
tool guidance, environment — and the skills tier was deliberately
absent, with a test named `test_no_skills_index_is_injected` pinning it.
The ruling behind that test was that this repository's skills were being
redesigned and a catalogue about to change costs more than none. With
`omicsclaw/skill/` deleted and `omicsclaw/skills/` in its place, the
premise is gone. The test was **rewritten rather than deleted**, which
is the mechanism working, and the prompt is now six sections with
`skills` between the tool guidance and the environment — the catalogue
is the largest and most stable block, so the one section whose text
changes daily stays last and invalidates the cached prefix at the very
end of it.

Measured on this repository, at `--skills-index full`:

| section | tokens |
|---|---|
| persona (`SOUL.md`) | 323 |
| project (`CLAUDE.md`) | 4,163 |
| safety | 133 |
| tool guidance | 104 |
| **skills (96 of them)** | **7,523** |
| environment | 31 |
| **total** | **12,277** |

`--skills-index compact` renders the same catalogue at 547 tokens
(5,301 total) and `off` restores the five-section prompt and unmounts
`use_skill` — one switch with one meaning, because a fetch tool for a
catalogue the model was never shown is a tool it cannot name an argument
for. `OMICSCLAW_SKILLS_DIR` moves the scan.

**One scan, two consumers.** `build_app` calls `build_skill_index` once
and hands the result to both `default_sections` and `foundation_tools`.
Two scans would not raise — they would let the system prompt advertise a
skill `use_skill` cannot load, and the model reads its own correct call
back as its own mistake. The test that pins this had to be built around
a scan that returns a *different* catalogue each call, because two scans
of one unchanged directory produce equal catalogues and no assertion
about content can tell them apart.

**`omicsclaw/entry/turn.py` is where the conversation `AgentEngine.run`
says "arrives assembled" actually arrives from.** Per turn: render the
assembler, `assemble([system, *history, user])`, `measure`, compact if
the pressure reaches `compact_at`, then `engine.run` or `run_stream`.
Three properties worth not re-deriving:

- **The render is per turn, not per process.** `AgentApp.prompt` is the
  *assembler*; holding an `AssembledPrompt` would compile, run, and
  silently stop picking up an edited `SOUL.md` or tomorrow's date.
- **`TurnOutcome.history` is stripped of the system message.**
  `compact(pinned=1)` returns it *inside* the history, and `assemble`
  always adds a fresh one, so carrying it forward stacks a stale persona
  beside the current one and puts the cache breakpoint on index 1.
- **Pressure tiers are compared through `at_least`, never with `>=`.**
  `Pressure` is a `StrEnum`, so `Pressure.EMERGENCY >= Pressure.FULL` is
  `False` — the comparison that matters most, answered backwards, with
  no error anywhere. `PRESSURE_ORDER` is the rank table.

Ten mutations, each killing a named test. **Two of them first survived,
and both were holes in the tests rather than in the code** — worth
recording because each is a shape of mistake:

1. *A test that cannot distinguish the thing it is named after.* "The
   prompt advertises what `use_skill` can load" passed under a mutant
   that scanned twice, because both scans saw the same directory. A test
   for *sharing* has to make the two sources differ.
2. *Testing a guard at a tier where it is a no-op.* `pinned=0` survived
   because the scenario reached `emergency`, whose fallback preserves
   the head whether or not it was pinned. At `full` with a working
   summarizer the same mutation **drops the system message entirely** —
   persona and safety rules gone, message zero comes back a user turn.
   The test now sits at that tier and asserts the record is *not*
   degraded, so it cannot silently slide back into the fallback path.

#### Second wave — sessions, the stream, approval, and the three surfaces

`turn.py` stayed a **functional kernel** — `compose` → `prepare`
(measure + compact) → `run_turn` / `stream_turn`, returning a
`TurnOutcome`. The second wave added session ownership, task isolation,
the event stream, approval and cancellation **on top of it**, rather
than rewriting it into the `TurnRunner`/`TurnHandle` the plan had
sketched. `SessionRegistry` owns one lane per session, so two messages
from the same user queue instead of racing; `TurnStream` is a ring
buffer with reconnectable observers, where a slow observer that loses
deltas gets a `GAP` frame whose `seq` **is** the cursor to resume from.
`TurnEvent` is 15 fields and 14 types, and `to_wire()` uses the
`TurnEventType` values rather than `/chat/stream` frame names — only 5
of the 14 have a published name, and inventing nine more would be
publishing vocabulary to an external client unilaterally.

**The three surfaces are a port, not a rewrite** (owner scope revision,
2026-09-19; plan 0031 §12-5). The original plan judged them rebuilds;
measurement said otherwise — the old surfaces are not half-dead, their
seam is just very thin. `omicsclaw/surfaces/` was the read-only input
and **not one line of it changed**. Acceptance made that falsifiable
rather than aspirational: per sub-package, rewritten lines may not
exceed ported lines; the Desktop wire contract's eight
`*_SCHEMA_VERSION` values must be byte-identical to before the port; a
repeated `source_request_id` must resolve to the **same** `TurnHandle`;
and the reverse-layering probe extends to all three facades, so
`omicsclaw.control*`, `omicsclaw.memory` and `RunRuntime` may not appear
in `sys.modules` — porting a file and quietly porting its imports with
it is the mistake that probe exists to catch.

Two independent read-only evaluations gated the step, neither knowing
the other existed, and they **converged independently on five findings**
— the same signal step 4 got, and, as recorded there, available only
once. Each evaluation's own blocking defects are worth reading as a set,
because the interesting column is not the defect but why the suite was
green anyway:

| Defect | Why it was green |
|---|---|
| `python -m omicsclaw.entry.cli` crashed immediately on `provider.model`, which `LLMProvider` does not have; `/health` had the same illness | The shared provider **test double declared a property the real protocol does not have** |
| A raising `SessionStore` wedged a session permanently — no terminal frame, and `shutdown()` could not recover it | The only implementation, `InMemorySessionStore`, never raises |
| A queued `cancel()` landing inside the `await store.load()` window was silently dropped | The in-memory store does not await, so that window does not exist in the tests |
| The fail-closed gate for a group message with `bot_identity=""` had **zero** tests (the only surviving mutant) | Every test passed a non-empty `bot_identity` |

**The most expensive lesson of this step, and the one it had warned
itself about.** Acceptance criterion 10 was "a runnable command on
delivery day". On delivery day 619 tests were green, the coordinator ran
them personally — and the real command crashed on its first line. This
is step 4's "static checks catch spelling, only a behavioural probe
catches facts", committed again, on the same plan, against the same
criterion. The rule now: **an entry layer's acceptance has to be run by
a real provider through a real `__main__`.** A green produced by a
double that is *wider* than the protocol proves the double. Three AST
discipline tests pin it — this layer reading a provider attribute the
protocol lacks, a double declaring more than the protocol, and the same
rule for the `sitecustomize` shim.

Three more worth not re-deriving:

- **When responsibility moves, its tests have to move with it.**
  Persistence moved from a cancelled Task to the registry — the right
  call — and one trap's responsibility moved with it while its tests
  stayed behind. `TurnRunner.run`'s `finally` ended up with 42 tests
  standing guard, and the loop outside it, the one that calls the
  **only Protocol left for an external implementer**, had none.
- **A grep caliber will lie to you systematically.** The coupling
  density in the plan was corrected three times — 148 / 0.39% → 43 →
  **269 / 0.70%** — always the same cause wearing a different face:
  aliased imports (`import X as Y`, then `Y.*`), relative imports, and
  `from X import Y as Z`. Both evaluators made the same class of error
  themselves, twice, grepping the wrong file.
- **Scope is the defect; the rule was fine.** The evaluation named 2
  adapters that logged user text at INFO. There were **6**. The
  detector's scope widened from four modules to `omicsclaw/entry/**`.

The repair round was a third agent that neither wrote the code nor
judged it. It **rejected 5 of the evaluations' findings** on evidence,
including the two grep errors above, and settled one point where the two
evaluations reached opposite conclusions (the second had read *this
repository's* `AGENTS.md` where it meant harness9's; the citation is now
disambiguated). Full outcome in plan 0031 appendix B.

#### Two rulings the owner was owed, and what came of them

Neither was filed in plan 0031 — they surfaced during implementation.
Both were put to the owner on **2026-09-20**; the first is open as a
design question, the second is settled and landed.

1. 🟡 **Open — the argv source scan and a `python -m` entry point are
   naturally in conflict.** `test_no_other_entry_module_reads_the_environment` forbids
   `os.environ` / `os.getenv` / `sys.argv` anywhere in
   `omicsclaw/entry/**` except `config.py` — but acceptance criterion 10
   requires a `python -m omicsclaw.entry.cli`, and a command line
   necessarily enters through `__main__`. Channel and Desktop never hit
   this **because neither has a `__main__.py`**. The implementation
   widened the exemption to `{config.py, __main__.py}` and **only for
   argv** (both env needles still apply to `__main__.py`), adding a
   stronger compensating test asserting that `__main__.py` reads argv
   exactly twice, no environment at all, and carries exactly its own five
   flag literals. It explicitly refused two detours: letting the test go
   red (the rule is add-only), and using `sys.orig_argv` to dodge the
   string scan (evasion, not a fix). **The owner picks**: ratify the
   exemption, or move the `python -m` entry point out of `entry/` —
   e.g. point it back at the `oc` console script for the migration
   window (plan 0031 §10-1 lists all four entry points). **Owner ruling,
   2026-09-20**: neither — the old launch arrangement is to be redesigned
   against the new framework, keeping the layer's cohesion and its thin
   coupling. The exploration is
   [plan 0037](plans/0037-launch-and-entry-points.md), which reframes the
   conflict: the entry point is *a member of the layer it starts*, and
   `entry/cli/` is the only one of the three facades that is a process as
   well as a library. Its recommendation is a thin `omicsclaw/launch/`
   above `entry/` owning argv, exit codes and signals — which removes
   both exemptions rather than widening them. **The exemption stands
   until that lands.**

   A **second owner ruling the same day** narrowed it further: the
   process entry points are **exactly three — `cli`, `channel`,
   `desktop`** — and `oc run <skill>` is not kept. That **cancels** plan
   0031 §10-4 rather than answering it: there is no longer a division
   between two families of entry to write down, because there is one
   family. Deterministic skill execution does not disappear, it stops
   being *a way in* — it becomes what the agent does in a session, and an
   in-surface command (`entry/cli/_slash_command_support.py` already
   lists `/run` and `/skills`; `entry/channel/commands/builtins.py`
   already registers `/demo` and `/skills`). The bill this hands the
   migration is named in plan 0037 §9-3: `README.md`'s Quick Start,
   `CLAUDE.md`'s whole CLI Reference and CI all invoke
   `oc run <skill> --demo` today, so CI needs a library-level path to
   deterministic execution before that entry point goes.
2. ✅ **Settled — `--prompt-file` meant two different things.**
   `AppConfig` had claimed it for *system-prompt* prefix files, while
   harness9's flag of the same name is the *user* prompt for a single
   execution, which this plan also asked for. Separated by `--` they
   never collided, but `python -m omicsclaw.entry.cli --prompt-file
   task.md` — with the `--` forgotten — turned the task brief into a
   system prompt with nothing raised anywhere. **Owner ruling,
   2026-09-20**: rename the system-prompt one. It is now
   `--system-prompt-file` / `OMICSCLAW_SYSTEM_PROMPT_FILES` /
   `AppConfig.system_prompt_files`, and `--prompt-file` means in this
   repository what it means in the harness. **No alias was kept** — an
   alias would preserve the exact failure the rename removes — so the
   deployment half now *refuses* the old name, pinned by
   `test_the_deployment_half_no_longer_answers_to_the_surface_flag_name`
   and mutation-checked by putting the old name back.

### Step 6.5 — `omicsclaw/mcp/` (plan 0034)

The MCP client layer the tool adapter was waiting for:
`omicsclaw/tools/mcp_tool.py` had shipped in step 4, while harness9's whole
`internal/mcp` (config, transport, handshake, manager) had no counterpart.
Seven modules, standard library only. `tests/mcp/` runs a real subprocess
server and a loopback HTTP server, and the whole rebuilt stack passes.

```python
app = attach_sessions(await open_app(resolve_app_config()))   # connects .mcp.json
...
await app.aclose()        # drains sessions, then stops the servers
```

The engine is untouched. An MCP tool is an `MCPTool` in the registry, so it
gets the scheduler, the timeout, the approval pause and error-as-Observation
the way every tool does. One ReAct exchange driving a real MCP subprocess is
pinned end to end in `tests/entry/test_open_app.py`.

Decisions worth not re-litigating:

- **Servers connect before the registry is built, not injected later.**
  harness9 injects from a goroutine after its TUI is up, but here the tool
  snapshot and `reserve_tool_tokens` are computed once in `build_app`, and
  tool definitions sit in the cached prefix. `open_app` connects every
  server concurrently within `--mcp-connect-timeout` (30 s); a server that
  fails is logged and left out. `build_app` itself connects nothing.
- **Approval was declared and not enforced.** `MCPTool` said `ASK` and
  its `execute` never called `require_approval` — plan 0028's "has tests
  is not wired up", once more. It now checks the payload's shape, then
  asks with the full arguments and where the call goes (`local process …`
  or a redacted `remote <url>`). Absence of a channel refuses.
- **Only `manager.py` touches the tool layer.** The protocol modules speak
  MCP and raise MCP errors; the manager mints `MCPTool` through
  `mcp_tool_name` (one naming rule), caps output at 32k and reports name
  clashes as `skipped`. A layering test pins it.
- **Nine harness9 defects avoided**, each with a test or a Go probe (plan
  0034 §5). The one worth remembering: a stdio server is killed as soon
  as its connect goroutine returns (`exec.CommandContext(connCtx)` plus
  `defer cancel()`). The plan did not see it; the audit's Go probe did.
- **The MCP tools run serially, and that is declared, not fixed.** The
  default `concurrency_safe=False` makes each one a barrier, where harness9
  runs them concurrently. Whether to trust `readOnlyHint` for scheduling
  is an open owner decision.

One independent read-only audit found 4 medium and 10 low defects, plus 8
errors in the plan. All defects are repaired or declared (plan 0034 appendix
A). The implementer made the repairs, which departs from the "third agent
repairs" convention and is recorded there. 30 mutations each kill a named
test.

### Step 6.6 — ProgressiveCompactor in the main loop (plan 0035)

Compaction now runs **before every model call of a run**, not only between
exchanges — plan 0030 §11.B-1, closed. The four harness9 tiers act as a
progression: WARN offloads oversized tool results to files, SOFT summarizes
the older half of the head, FULL the whole head, EMERGENCY truncates
without a model call.

```
engine   HistoryCompactor (optional per-run Protocol: compact(history, tools) -> (messages, keep) | None)
context  compact()            one compaction, a pure function
         ProgressiveCompactor per run: measure every call, trigger, write-back gate, state
         Offloader/OffloadStore  what moves and what the placeholder says; the bytes go elsewhere
memory   FileOffloadStore     <workspace>/.omicsclaw/tool_results/<session>/<key>.txt
         JsonlCompactionLog   <workspace>/.omicsclaw/compaction_records/<session>.jsonl
entry    build_compactor()    wiring only; TurnRunner hands it to run_stream
```

The engine learned nothing about budgets: the Protocol returns a plain
tuple, so `context` satisfies it without importing `engine`. `entry/turn.py`
lost its own measure-then-compact sequence (it had two copies), and
`PRESSURE_ORDER` / `at_least` moved down into `context/budget.py`.

Decisions worth not re-litigating (the full list is plan 0035 §3 and §7):

- **Write-back is gated** (`should_write_back`): a failed summary serves one
  call and is retried on the next; an emergency truncation is kept; a
  compaction that removed nothing is not. The decision is recorded on
  `CompactionRecord.written_back`.
- **Offload first, then re-grade.** Offloading costs no model call, so it
  runs at every tier above NONE and the conversation is graded again; when
  offloading was enough, no summary is paid for.
- **Offload keys include a content digest.** A preset that reuses or omits
  call ids would otherwise point a second result at the first result's file.
- **References are carried deterministically** from one compaction message
  to the next (at most 50), rather than left to the summarizer's memory.
- **Persisted at exchange end, not at the write-back point.** Exchanges are
  atomic here (plan 0031 trap 3); the cost is that a failed exchange's
  compaction is redone next time.
- **`/compact` is a FULL summary queued in the session's lane**
  (`SessionRegistry.compact`), so it cannot race the exchange that owns the
  history; a failed summary is not written into the session. It is in the
  channel command registry, but **no live surface routes slash commands
  through `dispatch()` yet** — Telegram registers five native commands,
  Feishu sends all text to the model, the REPL has its own table.
- **An emergency truncation keeps `usable × full_at`, not all of `usable`.**
  Greedy packing to the whole budget stops just under it (0.98 measured),
  above the 0.95 trigger, so every later call was EMERGENCY again and never
  summarized — issue #117's truncation loop, found by the independent
  evaluation. At the EMERGENCY tier the tail is offloaded too, so a large
  recent result survives as a placeholder instead of being dropped.
- **`compact_at` now defaults to WARN**, because at FULL the offload and
  half-summary tiers never ran.
- **Only compactions that changed something or failed are announced** —
  in an IM channel every announcement is a chat message.

`omicsclaw.memory` moved from the entry probe's "replaced packages" to
`_SUPERSEDED`: the legacy graph memory is deleted and the name now holds
step 7's persistence layer, which `entry/compaction.py` composes.

**One independent read-only evaluation gated it** against harness9's
design doc and source, including a Go probe of the same scenario. It
confirmed the structure and the one-way layering (behaviourally, via
`sys.modules`) and found one high-severity defect — the emergency loop
above — plus three medium and five low; plan 0035 §9 has the table and
what was done with each. The implementer made the repairs, as in plan
0034.

**Verification.** The rebuilt stack (`tests/schema provider engine tools
context skills entry mcp memory`) = **2,996 passed**, 106 of them new,
run on a frozen copy of the tree because another session was mutating
`entry/` at the same time; `tests/tools/test_workspace.py` is excluded for
a pre-existing collection error (it loads a deleted legacy module). Fifteen mutations — ten on the gates, five on the repairs — each kill a
named test. Two survived the first round, both holes in the tests: a
failed `/compact` test whose budget was too loose for the fallback to
remove anything, and no case where a *successful* summary grew the
conversation.

Not done, and named: there is no session-delete entry point for the `purge`
methods; the CLI REPL has no `/compact`. The LTM extractor seam was the
third item here and is closed — plan 0040 opens the memory database in
`build_app` and derives the extractor in `build_compactor`.

### Step 6.7 — `omicsclaw/sandbox/` (plan 0036)

`bash` can now run inside a Docker (or Docker-compatible) container with
no network, no capabilities and the workspace bind-mounted at its own
path. The engine and the tool layer are untouched: the seam step 4.5 laid
down (`BashEnvironment`) is what the sandbox fills.

```
sandbox  SandboxConfig → SandboxManager.create_with_retry(workspace) → DockerEnvironment.run_bash
         Container (5 states), ensure_daemon_ready, reap_orphans, bootstrap   stdlib only, no logging
entry    sandbox_* AppConfig fields → open_sandbox() → SandboxBinding
         open_app: sandbox before MCP; BashTool(environment=…); prompt section; aclose removes it
```

```bash
OMICSCLAW_SANDBOX=docker OMICSCLAW_SANDBOX_IMAGE=<pulled omics image> oc interactive
# optional: _NETWORK, _MEMORY, _CPUS, _GPUS, _USER, _MOUNTS, _BOOTSTRAP, _RUNTIME=podman,
#           _REQUIRED=true (refuse to start without it), _AUTO_APPROVE=true (see below)
```

Decisions worth not re-litigating (plan 0036 §4.5):

- **Only `bash` is routed.** The file tools cannot leave the workspace
  (`Workspace.resolve`), the bind mount makes host and container views the
  same bytes, and `FileReadEnvironment` returns whole files — routing
  `read_file` would load a multi-GB h5ad to sniff its header. harness9's
  `DockerEnvironment.ReadFile/WriteFile` are host-side `os.ReadFile` anyway.
- **`--network none` is the default and the primary control.** The threat
  is data leaving the machine, not the host being damaged; harness9's
  `--add-host` DNS blackhole calls itself a behavioural guard, not a
  boundary. Also recalibrated: no memory/CPU caps by default, pids 4096,
  host `uid:gid`, `--pull=never`, `--init`, no cap re-added.
- **Timeouts and cancellation kill the command inside the container.**
  Killing the `docker exec` client does not; harness9 stops there. The
  wrapper records the command's PID and sends its output to a file (not to
  `exec`'s stdio, so a backgrounded daemon cannot hold the call open).
  Those files live in `<workspace>/.omicsclaw/sandbox/`, which the
  workspace mount already carries — a separate mount under the container's
  `/tmp` tmpfs would have depended on the runtime's mount ordering.
- **Orphan reaping removes only containers whose owner PID on this host is
  dead.** harness9 reaps every labelled container before it owns any, i.e.
  the live containers of a second harness9 beside it.
- **Degradation is loud and can be refused.** A sandbox that cannot start
  leaves `bash` on the host with a warning and an "Execution sandbox"
  prompt section saying so; `sandbox_required` makes start-up fail instead.
  `build_app` (synchronous) never starts one and reports itself degraded.
- **`sandbox_auto_approve` relaxes `bash` to `AUTO` only when the sandbox is
  running, its network is `none`, and the `bash` is the one the assembly
  built.** Degraded, open network, or caller-supplied tools: still `ASK`.
  This is plan 0029 appendix B.5's acceptance criterion — "can approval be
  switched off" — and the tests pin its effect in the tightening direction.

**Verification.** `tests/sandbox/` + `tests/entry/test_sandbox.py`: a fake
`docker` executable whose `exec` really runs the command, so the wrapper,
the PID file and the in-container kill are exercised by real processes,
end to end through `open_app` → ReAct loop → `bash`. A real-Docker
integration test runs where a daemon and image exist (skipped here).
Seventeen mutations each kill a named test; the one that survived the
first round exposed a redundant guard, which was removed.

**Two independent read-only reviews (Sonnet) gated it.** Parity: every
claim about harness9 checked out, no unjustified deviation, and the only
core capability not landed is per-sub-agent sandboxes (seam present).
Correctness: no high-severity defect; the medium one — the exchange
directory mounted under the `/tmp` tmpfs — is fixed as above, and three
low ones are repaired. Plan 0036 §7 has the table.

Open, and named: nothing here has run against a real Docker daemon on this
machine (none installed); `--gpus` with `--cap-drop ALL` is unverified; the
CLI REPL has no `/sandbox` status command (the `on_sandbox_change` listener
and `app.sandbox.manager.list_all()` are the seams); no sub-agent layer
exists yet to call `create(label="sub-1")`; MCP stdio servers and web tools
run on the host.

### Parallel tool calling — the barrier and the pause

A repair round across `engine/` and `tools/`, not a step. It was prompted
by a read-only comparison against the reference harness's
`tools_exec.go`, whose finding was that **the parallel scheduling itself
was already there and already ahead of the reference** — the three
guarantees `tools_exec.go` documents (pre-allocated results written by
index, wait for every worker, a semaphore when a ceiling is configured)
are all in `execute_tool_calls`, which additionally cancels and reaps
in-flight workers on abandonment, keeps `CancelledError` out of
`recover()`'s reach, leaves an empty slot rather than inventing an
Observation for a cancelled call, and can tell an expired engine budget
from a tool's own HTTP timeout. What was missing was not parallelism but
its two safety rails.

**The write barrier.** `ToolPolicy.concurrency_safe` had zero consumers —
plan 0028 §11 debt #1 — so a turn emitting two `write_file` calls to one
path ran them concurrently and lost an update. The engine now asks the
executor, through a **second, optional** Protocol
(`ConcurrencyAwareExecutor`, satisfied structurally by `ToolRegistry`),
and runs a call that has not claimed concurrency safety **alone**:
`_concurrency_groups` splits the turn into batches, a barrier is a batch
of one, and its safe neighbours still run beside each other. Ordering,
event delivery and the slot-per-call contract are untouched, and an
executor that does not implement the Protocol is scheduled exactly as
before. `EngineConfig.serialize_unsafe_tools` defaults to `True`,
matching `ToolPolicy`'s guarded defaults.

This goes past the reference, which has no scheduler-level notion of
concurrency safety at all and relies entirely on `path_locker.go`.
`_pathlock.py` is **not** superseded by the barrier and its docstring now
says why: a barrier orders one turn, and overlapping turns — two Channel
conversations, a sub-agent, a background run — are the shape the Channel
Surface has by construction. `tests/tools/test_pathlock.py` pins all
three cases.

**The approval pause.** `EngineConfig.tool_timeout` wrapped the whole of
`execute`, and the approval `await` sits inside it, so a user who took 61
seconds to tap "approve" had the tool cancelled and the model told
`tool 'X' timed out after 60s` — false, and it sends the model to make
the tool faster. The Go trick does not translate: `asyncio.timeout`
cancels the task rather than being polled, so a closure over a session
context buys nothing and `asyncio.shield` still raises at the await
point. What works is `asyncio.Timeout.reschedule`, and the engine hands
the call a `TimeoutPause` through a second optional Protocol
(`DeadlineAwareExecutor`) that `ToolRegistry` relays into
`omicsclaw/tools/context.py`, where `require_approval` enters it around
the human round trip. **R3 is therefore fixed, and the scheduling
constraint below is cleared.**

The pause stops the clock; it does not bound the wait, so a surface that
posts an approval card still owns the deadline on its own prompt — but
missing it is now that surface's own report rather than a fabricated tool
timeout.

**Also landed:** `EngineEvent.duration_s` on `TOOL_RESULT`, the
engine-side per-tool timing the reference carries as
`ToolResultData.Duration` (plan 0027 evaluation #35); and a test pinning
that each worker gets its own context copy, which
`omicsclaw/tools/context.py` names as the coincidence its approval
isolation rests on.

**Deliberately not done**, and each for a reason: the hook / permission
layer (`hooks/hook.go`, `permission.go`) — the registry's docstring
already reserves the seam *outside* its `try`, and who is asking is step
5's knowledge, not step 4's; and per-batch logging — `omicsclaw/engine/`
states "no I/O, no logging" as a convention in its own module
docstrings, and observability belongs to the Surface. Note what that
second one is **not**: `tests/engine/test_engine_is_a_leaf_layer.py`
checks import boundaries only, and nothing in the suite would fail if
somebody added `logging` to this package. The convention is unenforced,
and a Surface-side decision should not be argued from a test that does
not exist.

**Verification.** `tests/schema/ tests/provider/ tests/engine/
tests/tools/` collects 1,419 and passes them. One caveat, named rather
than rounded off: `test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`
is **pre-existing and order-sensitive** and has failed on some runs —
reproducibly when `test_bash.py` runs immediately before it, never on its
own. Nothing in this round touches `_websafety.py`; the race is between
the socket's own `settimeout` and the module's monotonic deadline check,
and the test hard-codes the wording of the second. Left alone as out of
scope, and open.

Nine mutations, each confirmed to kill a named test: barrier disabled,
every tool reported safe, the registry ignoring its policy, the pause
never lifting the deadline, the pause never restoring it, the engine
never offering it, the registry dropping it, the duration dropped from
the event, and — the one the first mutation round missed — the pause
restoring the **original absolute** deadline instead of the seconds that
were left, which is R3 coming back under a different name.

**Two tests that pinned the old harm were rewritten rather than
deleted**, which is the mechanism working:
`test_the_engine_really_does_run_two_writes_to_one_path_at_once` said in
its own docstring that a failure meant something had started serialising
tool calls, and
`test_a_slow_human_is_reported_to_the_model_as_a_tool_timeout` said the
fix belonged in the engine. Both now assert the fixed behaviour, and each
gained a companion pinning the **tightening** direction — a tool that
really does overrun is still reported as overrunning, and two overlapping
turns still need the path lock.

#### Two independent read-only evaluations gated it

One for correctness, one for harness9 parity, neither told what the other
was looking at. They converged on nothing — and that is informative,
because each found the class of defect the other's brief could not see.
Everything below was repaired.

**The correctness evaluation found the one mutation that mattered most,
and it was the one the implementation's own mutation round had missed.**
Restoring the paused budget to its **original absolute deadline** instead
of the seconds that were left — R3 exactly, under a different name —
survived all 1,014 tests. The reason is worth carrying into step 5:
`asyncio.Timeout` fires only at an `await`, and `__aexit__` cancels its
handler on the way out, so **a test whose tool returns the instant the
pause closes cannot observe a deadline restored into the past.** Both
flagship tests did exactly that. The repair is one `await asyncio.sleep`
in each, and the general rule is: *a test for a deadline must do
something after the deadline is restored, or it is testing that nothing
happened.*

It also found a liveness consequence the implementation had documented
only halfway — a barrier call blocked on a human holds up **every later
batch of the turn**, where before the barrier the siblings would have
finished — and an asymmetry between the two new optional seams: a broken
`is_concurrency_safe` resolved to the guarded value while a broken
`use_timeout_pause` failed *every* tool call in the run. Both are now
guarded the same way, and both consequences are written down.

**The parity evaluation found that the docstrings were wrong about Go**,
which is the refinement step 4.5 paid for and it paid again here. Five
checkable claims were false: `recover()` catches panics rather than
"everything"; `path_locker.go` has three callers, not two; `sync.RWMutex`
is not chosen because goroutines are OS threads (they are not) but
because a goroutine can be preempted anywhere; the reference uses
`context.WithValue` for **seven** keys rather than two — and that
undercount is the interesting one, because two of the five missed encode
a mechanism this layer does not have (`approvedContextKey` makes one tool
call ask a human **at most once** however many hook layers want to ask;
`require_approval` asks every time). A count being wrong and a mechanism
going unnoticed were the same defect.

Both evaluations independently corrected a claim this round introduced:
`asyncio.TaskGroup` does **not** break the per-worker context copy — it
creates Tasks, and a Task copies — and `asyncio.ensure_future` has no
`context=` parameter to withhold. The docstrings were warning readers off
a safe refactor while leaving the two genuinely dangerous ones (awaiting
calls inline, handing several Tasks one shared `Context`) unnamed.

#### Open, and named so it is not rediscovered

- **`EngineConfig.tool_timeout = 60.0` is an unacknowledged ported
  literal**, and in this repository that matters more than it did in the
  reference. `max_turns` in the same dataclass was re-derived against
  local evidence and says so; this one was inherited in silence. A
  `spatial-deconv` or a STAR alignment runs for minutes to hours, and
  `BashTool` has already been pinned *down* to 45 s by it
  (`DEFAULT_TIMEOUT = 60 - ENGINE_TIMEOUT_MARGIN`).
- **`bash`'s `timeout_secs` only shrinks.** `BashTool.max_timeout`
  returns `self.timeout`, so a model can ask for less and never for more
  — while the reference's whole point is asking for *more* (120 s → 600 s
  ceiling). Half the mechanism is present, and it is the half that does
  not help. Note also that the current `TimeoutPause` type cannot express
  it: it takes no arguments, so "give me 600 seconds" needs a wider seam
  rather than a use of this one.
- **Approval has no representation in `EngineEventType`.** Six members,
  no `approval_required`, so a Surface cannot learn from the event stream
  that a human is being asked — which is the structural reason the
  consumer contract above has to be written in prose.

### Step 6.9 — `omicsclaw/planning/` (plan 0039)

Eight modules, `tests/planning/` = **181 passed**, plus 13 in
`tests/engine/` and 23 in `tests/entry/`. The whole rebuilt stack =
**3,679 passed**. The layer structure comes from harness9's
`internal/planning/` + `internal/tools/plan_write.go` + the planning
parts of `internal/engine/loop_phases.go` + `internal/hooks/plan_writer.go`.

```python
from omicsclaw.planning import PlanBook, PlanInjector, plan_write_tool

book = PlanBook(FilePlanArchive(workspace / ".omicsclaw" / "plans"))
registry.register(plan_write_tool(book))                 # once, per app
injector = PlanInjector(book.for_session(session_id))    # per exchange
result = await engine.run(messages, augmentor=injector)
```

**The problem it closes.** Step 6.6 made compaction run before every
model call, which is what a long task needs and also what takes its
memory of *what it set out to do*. A plan is that memory, held outside
the conversation and re-injected at the end of the send view before every
call — so compaction cannot summarize it away and a resumed session does
not start over.

Decisions worth not re-litigating:

- **A second engine seam, not a wider first one.** `TurnAugmentor` is
  consulted after `HistoryCompactor` and may only *append*, to the sent
  copy alone. Decorating the compactor instead was rejected on evidence:
  `entry/turn.py:_outcome` reads three concrete `ProgressiveCompactor`
  attributes, so a wrapper has to forward them and forgetting does not
  fail — it silently drops a run's compaction records. That is defect
  R3's shape, and `build_registry`'s docstring already records what it
  costs.
- **Persistence is files, not the session database.** Following the
  reference would put a `plan` column on `memory.StoredSession` and a
  `PlanItem` import inside `omicsclaw.memory`. Two files per session
  under `<workspace>/.omicsclaw/plans/` instead — the shape this rebuild
  already uses for per-session state the conversation does not carry
  (offloaded results, compaction records). Write-through on every
  accepted write narrows the crash window from the reference's one turn
  to one file write.
- **`PlanBook` exists because harness9 is single-session.** Its `main.go`
  builds one `PlanStore` and injects it into both the engine and the
  tool. Here one `ToolRegistry` serves every conversation, so the tool
  holds a book and resolves the session at call time through
  `context_value("session_id")`.
- **Validation and merge moved out of the tool.** The reference keeps
  both in `plan_write.go` and says its store does not validate; here they
  are pure functions in `rules.py`, so the rule is testable without a
  JSON payload and a second write path cannot reach the store without it.
- **The planning gate is a window over the sent view, not an engine
  counter.** The consequence is named rather than fixed: a compaction
  that shortens the visible history can stop the gate firing where the
  reference's counter would have. Accepted — a compaction has just handed
  the model a fresh summary, which is the worst turn to add an
  instruction to.

Literals re-derived rather than pasted: the gate threshold (the
reference's 12 is 15% of *its* 80-turn budget against a 28-turn median;
50 × the same fraction rounds to **8**) and — the one that would have
been easy to miss — **the prompt-facing text's language**. The reference's
injection header and gate nudge are Chinese because that project's prompt
is; every section of this one is English and `SOUL.md` says to default to
it, so a ported header would be a language switch nobody asked for in the
one message whose job is to be obeyed. Plan 0027's rule about borrowed
literals, applied to a literal that looks like prose.

#### Three defects the implementation found on itself

1. **`run_turn` and `stream_turn` never bound a tool context.** The
   session id reaches the compactor and, before this, nothing else — so
   `plan_write` resolved every such exchange to the anonymous store while
   the injector read the session's. A plan written in one turn, gone by
   the next, nothing raised. `TurnRunner` was always correct; the two
   library functions had no equivalent.
2. **A prompt example named a skill.** `spatial-deconv` in the planning
   guidance put a skill name into the prompt of a deployment running
   `skills_index=off` — caught by an existing probe, not by anything new.
3. **The atomicity test was vacuously green.** It provoked the failure
   inside `dump_items`, before a single byte was written, so it passed
   against an implementation that truncates. Injected at `os.replace`
   now, with a self-check that the injection is reached.

#### Two independent read-only evaluations gated it

One for correctness, one for harness9 parity, neither told what the other
was looking at. Full table in plan 0039 §8. Three findings were repaired
and one was **rejected on evidence**:

- **The duplicate-id false refusal.** `merge` collapsed a repeated id
  while `validate` counted it, so one finished item *resent* was refused
  for completing "2 plan items". The two rules were reading different
  views of the same write; they now share `_first_by_id`. This also fixed
  a quieter inconsistency — `[(a, pending), (a, completed)]` was
  validated as a completion and stored as a pending item.
- **An ordering claim with no test.** `FilePlanArchive.save`'s docstring
  makes JSON-before-Markdown load-bearing; swapping the two writes left
  all 175 tests green. Two tests now pin it, one of which watches the
  filesystem rather than reading the code.
- **Two of three exchange paths untested.** The session-binding repair
  was pinned on `run_turn` only; `stream_turn` and — more importantly —
  `SessionRegistry` → `TurnRunner`, the path every live surface actually
  uses, had nothing. A feature verified only on the library path is a
  feature verified on the path nobody runs.
- **Rejected: "planning on by default broke 6 pre-existing tests."** Not
  reproducible — `tests/entry tests/engine tests/planning` = 1,116
  passed, 0 failed, including every test named. Both evaluations
  independently traced the real cause to an untracked, half-wired
  `omicsclaw/entry/memory.py` left in the working tree by a concurrent
  session, with a genuine circular import against `entry/compaction.py`
  that makes collection order-dependent. **A tree several sessions are
  writing at once is a tree where "the suite is red" is not evidence
  about your own change until you have isolated it.** One observation
  from that finding was kept: mounting a tenth tool does move
  `reserve_tool_tokens`, and budget-tight tests are sensitive to it.

**The parity evaluation's other finding is the one step 4.5 keeps paying
for.** Of 25 Go citations checked, **7 were mislocated** — by 3 to 16
lines, clustered in `plan.go`. Every claim they supported was true; the
line numbers were plausible rather than checked. All 28 citations in the
layer have now been re-verified line by line, and three loose ranges were
tightened (one ended on `package tools`). The rule, restated because it
has now been earned three times: **a file:line citation is a claim, and
an unchecked claim about the reference is a defect even when the sentence
around it is right.**

### Step 6.11 — `omicsclaw/observability/` (plan 0043)

Eleven modules, `tests/observability/` = **257 passed**, plus 17 in
`tests/entry/test_telemetry_wiring.py`. Two independent read-only
evaluations gated the step; both found real defects and **neither found
what the other did**, which is the mechanism working.

**The scope is the reference's `internal/observability` with two
deliberate refusals and one structural difference.**

| harness9 | here |
|---|---|
| `observability/config.go` | `observability/config.py` — plus `capture_content` |
| `observability/attributes.go` | `observability/attributes.py` — instruments declared as a table |
| `observability/setup.go` | `observability/telemetry.py` + `otel.py` |
| `observability/helpers.go` | `observability/serialize.py` |
| `observability/provider.go` | `observability/provider.py` — `TracedProvider` |
| `observability/hook.go` | `observability/hook.py` — `TracingHook` |
| `observability/observer.go` + `engine/observer.go` | `observability/scope.py` — **consumes `EngineEvent`, adds no seam** |
| (OTEL API's own `Span`/`Tracer`/`Meter`) | `observability/contract.py` — ours, stdlib |
| (`stdouttrace` / `stdoutmetric`) | `observability/console.py` — **stdlib, no SDK needed** |

**Refusal 1: payloads are not captured by default.** The reference always
serializes the conversation, the tool arguments and the tool output into
span attributes, so switching OTLP on ships them to a third party. In a
coding harness that is reasonable; here `CLAUDE.md`'s first safety rule
is that genetic data never leaves this machine, and an OmicsClaw prompt
routinely names a cohort or a sequencing run. So
`OMICSCLAW_OTEL_CAPTURE_CONTENT` is off by default, the four `langfuse.*`
attributes are the only ones gated on it, and everything a dashboard
needs is recorded either way.

**Refusal 2 turned out not to be a refusal at all, and that is the more
useful entry.** This section first claimed `main.go` treats a failed
`Setup` as fatal and counted our degradation as a deliberate departure.
The parity evaluation checked it: `cmd/harness9/main.go:127-131` logs and
substitutes `NewNoopProviders()`, and the reference's three other
observability constructors degrade the same way. **The reference is
fail-open from end to end.** The conclusion (degrade, because the run may
be a six-hour alignment) was right and the argument for it was invented —
which is the defect, under the rule this tree has earned three times: an
unchecked claim about the reference is a defect even when the sentence
around it is right.

**The structural difference is the lazy turn span**, and it falls out of
there being no `TURN_START` event. The kernel begins turn *N+1* inside
the very `__anext__` that follows turn *N*'s `TURN_END`, so the only
honest moment to open the next turn span is the instant the previous one
closed — when nobody yet knows whether the run continues. `TurnScope`
holds the *intent* and materialises at the model call, so a finished run
discards an intent rather than exporting an empty phantom.

**What the evaluations found.** The correctness one found a defect
*class* rather than an instance: `RunScope.__aenter__` and
`TracingHook.before_execute` each started a span and *then* decorated it
with a second call, both inside one `try`, so a decoration that raised
left a created span with nobody holding a reference to `end()` it — one
trace gone, silently. Both now pass every attribute to `start_span`, the
way `TracedProvider._start` already did. It also showed that the
`__aexit__` flush argument — the one that cites `hooks/chain.py`'s
cancellation defect by name — was pinned by **no test at all**: moving
the `await` inside the `try`, and widening `except Exception` to
`except BaseException`, both left 260 tests green. And it found that
`hook.py`'s per-call ContextVar had overwrite semantics where `scope.py`'s
next door has stack semantics, which is unreachable today and becomes a
real defect the day a tool runs an agent in its own task.

The parity one found the `Setup` misreading above, one genuinely missing
feature nobody had recorded — `setup.go:57-63` registers a global OTEL
error handler for *runtime* export failures, where this module only
guarded construction, so a key that expires mid-deployment stops the
traces with a clean local log — and a citation to `observer.go` off by
~17 lines and pointing at the wrong function. Five citations in all were
re-verified and corrected, one of which (`entry/assembly.py:711` → `:722`)
**this step's own edit had rotted**.

**Three defects the work found on itself before that, each pinned by a
test written before the fix.** A tracer that went away mid-run let an exception escape
`current_parent()` into `TracedProvider.generate` and killed the
exchange — telemetry may cost a span, never a run. The blocking path
(`AgentEngine.run` drops its events by design) put **every** model call
of a multi-turn run inside one span labelled `agent.turn=1`; that is not
a missing level but a wrong number, and the repair is an explicit
`turn_events=False` that warns when a caller forgets it. And
`ObservabilityConfig(exporter="stdout")` built a silently inactive
deployment, because `StrEnum` compares equal under `==` but not under the
`is` this package uses everywhere.

**One thing the reference could not have warned about.** `setup.go` reads
`tp.Tracer(name)`; the Python SDK spells it `provider.get_tracer(name)`.
The line ported straight across was caught by `test_otel.py` on first
run — the other half of the rule step 4.5 earned: a file:line citation is
a claim, and so is an API shape.

**One pre-existing file changed beyond the wiring**: `hooks/audit.py`'s
private `_outcome_of` was promoted to a public `outcome_of`, so the
tracing hook labels `tool.status` with the same four-value
`AuditOutcome` the audit log files. Re-deriving it would have been two
answers to "did that call fail, or was it refused?".

### Step 6.10 — `omicsclaw/hooks/` (plan 0042)

Four modules, `tests/hooks/` = **117 passed**, plus 18 in
`tests/entry/test_hook_wiring.py`. Whole rebuilt stack = **4,068 passed,
9 skipped**, zero failures.

**The scope was decided by an inventory, not by the reference.**
harness9's `internal/hooks` bundles one mechanism with four policies, and
three of the four already have homes in this tree — so this step is the
mechanism plus the fourth. Re-implementing any of the three would give
one deployment two answers to the same question:

| harness9 | here |
|---|---|
| `hooks/hook.go` | `omicsclaw/hooks/chain.py` — **new** |
| `permission/hook.go`, `hooks/danger_hook.go` | `omicsclaw/permission/` (0038) |
| `hooks/offload.go` | `omicsclaw/context/` `Offloader` — a **narrowing**, see below |
| `hooks/plan_writer.go` | `omicsclaw/planning/` (0039) — not a hook at all |
| `observability/hook.go` | `omicsclaw/hooks/audit.py` — **new** |

The offload row is the one that is not a full cover, and the parity
evaluation was right to push on it: `Offloader` is driven by budget
pressure during compaction where the reference's hook fires
unconditionally on any result over 10,000 characters, and it has no
`read_file`/`write_file`/`edit_file` exclusion list. So a result too
small to push the conversation past `Pressure.WARN` is re-sent whole
every turn, and a placeholder read back can be offloaded again. Both
belong to `context/`; they are recorded rather than fixed here.

Four decisions worth not re-litigating:

- **Decorate a tool, not the registry.** Plan 0038 §2's argument, reused:
  the engine probes the registry with `isinstance` for two optional
  Protocols and a wrapper that forgets one does not fail — defect R3.
- **The chain goes inside the gate**, matching the reference's chain
  order (`main.go:413`). Two consequences are written down rather than
  discovered: a call a rule denied never reaches a hook, and a hook that
  rewrites a payload is **not** re-judged.
- **No `ask`.** Two actions, zero context keys, where the reference has
  three and two. The gate publishes an `AUTO` policy before running the
  tool it settled and `require_approval` reads that first, so a question
  from inside the chain answers itself — which *is* the reference's
  `explicitlyAllowedContextKey`, reached through a mechanism that already
  existed. A test asserts the enum has two members, because a second
  implementation is exactly the change that would leave a docstring alone.
- **Three methods, not two**, and the third buys the pairing invariant:
  every `before_execute` that returned is paired with exactly one closing
  call, including when a later hook denies. `hooks/hook.go:70-75` returns
  on a deny without closing anyone.

**Two independent read-only evaluations gated the step, and the
correctness one found two real defects — both in cancellation, both
reproduced before repair.** `_notify` caught `BaseException` and stopped,
which absorbed a *genuine* `task.cancel()` arriving during notification;
`execute`'s bare `raise` then re-raised the tool's own exception, so a
cancelled turn reached `ToolRegistry.execute` as an ordinary `Exception`
and came back to the model as a retryable Observation — around the side
of the guard at `tools/registry.py:314-321` that exists to forbid exactly
that. The docstring's justification was itself false: catching a
`CancelledError` does **not** make later awaits re-raise. Second, the
decision loop had no `BaseException` handler, so a hook cancelled while
deciding left every hook before it unclosed — breaking the invariant this
package advertises over the reference. The decision loop and the tool
call now share one `except`, and the refusal is raised rather than
returned so it takes the same path. **Neither defect was reachable by the
tests that existed**, all of which raised `CancelledError` by hand; five
now use a real `task.cancel()`, and the test that had pinned the harm was
rewritten rather than deleted.

**Two defects the work found on itself before that, both silent.** `_is_bash`
unwrapped one wrapper — correct while the gate was the only one — so
mounting a chain made `bash` unrecognisable, `bash_policy` was never
consulted, and a sandboxed session asked for approval on every command
with nothing raised. And the audit record's `detail` first carried the
exception *message* to match the model's wording; a `read_file` failure
quotes the path it could not open, so a failure now records the class
name alone. A refusal keeps its reason, because that string was written
by a hook in this deployment's own code.

### Step 6.8 — `omicsclaw/permission/` (plan 0038)

Five modules, `tests/permission/` = **262 passed**, plus 30 in
`tests/entry/`. All rebuild layers together = **3,301 passed**, against a
3,021 baseline taken before the step. The layer structure comes from
harness9's `internal/permission/` + `internal/hooks/` +
`internal/engine/permission.go`.

```python
from omicsclaw.permission import PermissionGate, RuleStore, gate_tools

gate = PermissionGate(mode=config.permission_mode,
                      rules=RuleStore(config.permission_rules_path()))
registry = ToolRegistry(gate_tools(foundation_tools(config), gate))
```

**The approval *transport* already existed and was not touched.** Step 6
shipped `require_approval` (fail-closed), the `ApprovalBroker`, the
`APPROVAL_REQUIRED`/`APPROVAL_SETTLED` events and the timeout pause. What
was missing was everything upstream of the question: granularity finer
than a tool name, any way to say *no* before a tool runs, and one knob
for the session's posture.

Decisions worth not re-litigating:

- **The gate decorates a `Tool`, not the `ToolRegistry`** — unlike
  harness9's `HookRegistry`. `build_registry`'s own docstring says why:
  anything wrapping the registry must forward `use_timeout_pause` *and*
  `is_concurrency_safe`, both are `runtime_checkable`, and forgetting
  either does not fail — it silently charges a human's approval time to
  `tool_timeout` again (defect R3, already repaired once). Decorating a
  tool also puts the gate *inside* `ToolRegistry.execute`, where the
  deployment's resolved policy is already published, and lets
  `use_effective_policy` carry a settled decision down — which is
  harness9's `withApproved`/`withExplicitlyAllowed` pair, built without
  editing one line of `omicsclaw/tools/`.
- **`ToolPolicy` gained a ninth field, `prompts_for_itself`.** The gate
  originally inferred "this tool asks for itself" from `approval_mode`
  being `ASK`. A test of the *tightening* direction caught that as a hole:
  `approval_mode` says what the deployment wants, and a tool that never
  calls `require_approval` runs regardless — so a call went through with
  nobody asked. It is a **claim**, defaulting to `False`, so a tool that
  forgets it costs a plainer prompt rather than a silent pass. The claim
  is checked behaviourally against the real tools in
  `tests/permission/test_foundation_tools_keep_their_prompts.py`.
- **Three things the reference has that were deliberately not ported**,
  each verified against its source first: `DangerHook` is *unreachable* in
  harness9's own default wiring (`main.go:417` puts the permission hook
  first, and every path through it marks the call decided, which
  `hooks/hook.go:87` reads as "stop asking"); `PermissionModeAutoApprove`
  and `ReadOnly` are read nowhere (`stream.go:178` tests only
  `BypassAll`); and `Rules.Evaluate` answering `ask` for an unmatched call
  is what makes both of those true. Here all four modes have a testable
  effect and an unmatched rule set returns `None`.
- **Matching is narrower than the reference in two places, both in the
  loosening direction.** No substring fallback (`allow: ["bash(ls)"]`
  there permits `rm -rf /; ls`) and no per-word pass (`bash(ls*)` there
  permits any command containing such a word). "Always allow" likewise
  remembers the *exact* call rather than harness9's
  `bash(*<first word>*)`.

Literals re-verified rather than pasted: the dangerous-command table.
harness9's 19 substrings became 28 regular expressions — its `| sh` fires
on `sort | shuf`, its `> /dev/` fires on `2> /dev/null`, and its
`chmod -r 777` only works because it lower-cases first. Five patterns for
data *leaving* the machine were added that the reference has none of,
because `CLAUDE.md`'s first rule is the one a destination blocklist
cannot enforce.

#### Two independent read-only evaluations gated it

One for correctness, one for harness9 parity and coupling. Neither found a
way to bypass the gate, prompt twice, or recharge a human's wait to the
tool timeout, and every one of a dozen harness9 line citations in the code
checked out. Six things were repaired as their own round; the three worth
carrying forward:

1. **`Path.mkdir(parents=True, mode=…)` applies the mode to the leaf
   only.** Intermediate directories were `0o755` under a docstring
   promising an owner-only tree. The test missed it because `tmp_path`
   already existed, so only one level was ever created — a one-level
   fixture cannot test a recursive branch.
2. **A capability with no caller is dead code, however well tested.**
   `PermissionGate.remember` had tests and no surface called it, so
   "always allow" was unreachable by any human. The CLI approval prompt is
   now three-way, and `AgentApp.remember_approval` is the seam — on the
   app because the pattern must be built from the tool's own schema, and a
   surface deriving that itself would write rules that never fire.
3. **`\b` treats a hyphen as a word boundary.** `\bsudo\b` matches the
   `sudo` inside `--sudo-mode`; `\bsystemctl\b` matches
   `systemctl-status-checker`. This is the same false-positive class the
   module had already fixed for `| shuf`, on a different set of patterns —
   fixing one instance of a shape is not fixing the shape.

Plan 0038 §7–§8 records all of it, including the reviews' two
non-adopted findings and why.

## Debts carried forward

None of these are defects in what shipped. They are known work the next
steps inherit, and two of them are **schema** changes, not provider fixes:

| Debt | Impact |
|---|---|
| ~~`StreamChunk` has no `finish_reason`~~ **RESOLVED, step 3** | Taken as plan 0027's one declared amendment. Both adapters already read the value and dropped it. `StopReason.TRUNCATED` now exists. |
| `Message` cannot hold an Anthropic thinking-block signature | The Thought is readable in history but **cannot be replayed** to the model that produced it — an unsigned `thinking` block is a 400 on the next turn, so the adapter drops it outbound. Also a schema change. |
| ~~`StreamChunkType.ERROR` is dead~~ **RESOLVED, step 3** | Raising won. The member stays, and the loop *converts* one into a raised `ProviderError` — reachable by contract for a third-party adapter, tested with a fake that yields one. |
| `cache_control` breakpoints reached the OpenAI adapter only | Native Anthropic — the one backend that caches **nothing** without an explicit breakpoint — is the worst-affected. |
| `anthropic` is declared in no manifest | Arrives only transitively. `pyproject.toml` declares `langchain-anthropic`; `environment.yml` declares `openai` but not `anthropic`. |
| Nothing has run against a live endpoint | The client-construction tests build a fake SDK module shaped after the adapter, so they verify plumbing, not vendor compatibility. This is the one place the suite asserts against its own assumptions. **Step 3's evaluation showed the cost is not hypothetical**: the retry classifier was written against Go error strings and matched nothing real, and its six tests passed because they invented the same strings. |
| `LLM_MAX_RETRIES` name collision | `autoagent/constants.py` has a module constant of the same name with a different default (3 vs 5) and different semantics. They do not interfere, but the two subsystems disagree on "how many retries". |
| Output-token ceilings are mostly unknown | `_model_limits.py` entries ported from the repo catalog carry the conservative default 8192, which means "not known", not "known to be 8192". |

Step 6 adds four of its own. Plan 0031 §11 carries the full nine-row
table; these are the ones a reader of this document would otherwise
discover by hitting them:

| Debt | Impact |
|---|---|
| Desktop did not port `/chat/abort` or `/chat/permission` | **A tool that needs approval hangs until timeout on the Desktop surface.** Recorded in `entry/desktop/`'s docstring |
| The frontend has no `case` for the `event_omitted` frame | `useSSEStream.ts` drops it through `default:`, so the GAP notice never reaches the UI. Needs a frontend change; the handover steps are in `desktop/turn_observation.py`'s module docstring |
| The TUI was not ported at all | A faithful port drags in the whole `RunRuntime` and memory families (12 blocked modules imported at module scope), and keeping only the Textual skeleton would be a rewrite, not a port. `textual` is not installed here either. Plan 0031 §1.3, §5.1 |
| None of the three surfaces has spoken to a real provider, a real HTTP client, or a real IM platform | The same debt as the provider layer's, one layer further out. Plan 0031 §11-4 |

Also unfinished by design: plan 0026 §10, the closing task that folds the
pre-existing `omicsclaw/providers/` (plural, 2,426 lines, still live and
untouched) into the singular package — port `ccproxy.py`, decide
`runtime.py`'s active-provider state, verify and delete the now-dead
DeepSeek half of `patches.py`, then collapse the two packages.

## Working conventions

**The interpreter matters.** The repo requires Python 3.11+; the default
`python3` on this machine is 3.10 and will fail. Use:

```bash
/opt/conda/envs/rapids_singlecell/bin/python -m pytest tests/schema/ tests/provider/ \
    -p no:cacheprovider -q -o addopts=""
# 396 passed
```

- **No network, and neither vendor SDK is installed.** No test may need
  either. Both adapters load their SDK lazily inside a client factory.
- **`black` is not installed anywhere on this machine** and cannot be.
  Verify line length with `awk 'length > 88' <files>` (must print nothing)
  and hand-check for constructs black would rewrap.
- **`pytest-asyncio` is not installed** either, despite being declared in
  `pyproject.toml`. Async tests are driven with `asyncio.run`. ~112
  pre-existing failures elsewhere in `tests/runtime/` are this missing
  plugin, not regressions — verified by an A/B run with the new packages
  removed.
- **Vendor SDK imports must be visible.** A plain `import` inside the
  client factory, never `importlib.import_module`. Laziness comes from
  *where* the import sits, not from making it dynamic — a dynamic import
  hides a real dependency from grep, from dependency scanners, and from
  the layering test, which would then pass while enforcing nothing.
- **Verify fixes by mutation, not by green.** Break the line, confirm the
  named test goes red, restore, confirm byte-identical. This is how the
  four blind spots in Anthropic request assembly were found — the adapter
  could send an empty conversation to the wrong model and all 63 tests
  passed.
- **The coordinator does not take a self-report at face value.** Run the
  tests yourself after every delivery and re-check the report's
  falsifiable claims. Step 6 caught a report of "549 passed, 0 failed"
  while the tree actually had a red test belonging to the very lane that
  filed the report.
- **Never write an acceptance criterion as "this must hang".**
  `pytest-timeout` is not installed here, so a hang is a real hang — one
  step-6 mutation wedged the whole suite for 900 seconds. Rewrite every
  such criterion as a fast failure with an asserted upper bound. The
  general shape: **a test that only asserts "it eventually happened"
  cannot test that it happened in time.**
- **`tests/tools/test_workspace.py` fails at collection** — it imports
  `omicsclaw/services/path_validation.py`, deleted by other work. Add
  `--ignore=tests/tools/test_workspace.py` when taking a baseline.
- **Two known load-sensitive flakes**, named exemptions in plan 0030 §9-1
  and plan 0031 §9-1:
  `tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget`
  and `tests/tools/test_bash.py::test_a_cancelled_turn_leaves_no_capture_file_behind`.
  The criterion: if one fails, re-run it alone **and** re-run its whole
  directory before calling it a regression. Do **not** change
  `_websafety.py` to stabilise the first one.

## Reference material

| What | Where |
|---|---|
| Go reference harness | `/workspace/dataset/private/zhouwg_data/harness9/internal/` |
| Its schema (10 types, 109 lines) | `internal/schema/message.go`, `stream.go`, `subagent.go` |
| Its provider layer (1,906 lines) | `internal/provider/` — `interface.go`, `openai.go`, `anthropic.go`, `tool_call_accumulator.go`, `orcarouter.go` |
| Step 1 decision record | `docs/adr/0077-one-top-level-vendor-neutral-schema-package.md` |
| Step 2 plan + outcome | `docs/plans/0026-provider-layer-simultaneous-interpreter.md` (§5 the nine traps, §11 the outcome) |
| Step 3 plan + outcome | `docs/plans/0027-react-main-loop.md` (appendix B) |
| Step 4 plan + outcome | `docs/plans/0028-tool-registry.md` (§5 the capability table, §11 the 16 debts, appendix B) |
| Step 6 plan + outcome | `docs/plans/0031-entry-layer.md` (Q1–Q24, §6 the 14 traps, §9 acceptance, §11 the 9 debts, appendix B the outcome, appendix C the pre-implementation review) |
| Its entry layer | `harness9/cmd/harness9/` — `main.go`, `cli.go`, `stream.go`, `tui.go` |
| Launch / entry-point redesign (exploration, not yet a plan) | `docs/plans/0037-launch-and-entry-points.md` |
| Desktop frontend (external client; it owns the contract) | `/workspace/algorithm/zhouwg_project/OmicsClaw-App/` |
| Repo agent contract | `AGENTS.md`, `CLAUDE.md` |

⚠️ The owner also referenced a tutorial at
`/workspace/algorithm/zhouwg_project/Agent Harness搭建教程/`. **That path's
filesystem was 100% full and 21 of its 22 markdown files were all-NUL
bytes; the directory then disappeared mid-session.** Do not rely on it.
Its chapter-2 reference schema was captured before it vanished and is
reflected in ADR 0077.

## Next step

**Step 7 — session persistence and long-term recall**
(`omicsclaw/memory/`, plan 0033). The name question step 3 had to settle
for `engine` does not arise: the owner deleted the old 28-module graph
memory system, so the name is free. Step 6 already left the two seams,
and this layer lands in them without changing a line of `entry/` — the
`SessionStore` Protocol and `attach_sessions(app, store=)`.

Then the **migration** (plan 0031 §10), which is a separate task and
larger than it looks: four `[project.scripts]` entry points to repoint,
`web_fetch` / `web_search` existing under the same name in both layers
with one side to retire, and the deletion of the old
`omicsclaw/surfaces/` — which cannot happen until the `RunRuntime` and
persistent-memory families land and `_main.py`'s 35 subcommands have
somewhere to live. Plan 0031 §10-2b gives the unlock order by measured
change size rather than by intuition: Channel (13 lines) → Desktop
`/chat/stream` (4 lines) → the CLI REPL's agent half.

~~**Step 5 — the assembly layer** (`omicsclaw/context/`)~~ **shipped**,
and **step 5.6** (`omicsclaw/skills/`) shipped after it. One consequence
worth keeping, since the entry layer is now built on it:

- Plan 0031 §12-1's ruling — "skill 整体预留，工具与索引段都不接" —
  **has lapsed, and was not overturned.** Its premise was that this
  repository's skills were awaiting a redesign; 5.6 *is* that redesign,
  so the premise expired. The catalogue is injected today, graded by
  `AppConfig.skills_index` (`full` / `compact` / `off`). What still
  stands: the layering probe names `omicsclaw.skill` (**singular**, the
  deleted legacy package) as forbidden and allows `omicsclaw.skills`.
  `tests/entry/test_entry_is_the_top_layer.py` keeps that history
  executable in a named `_SUPERSEDED` constant instead of erasing it —
  move the name back into the forbidden list and the probe goes red
  again.

### The question step 4 left open is answered: all four are dropped

**Owner ruling, 2026-09-18.** None of the four capabilities plan 0028 §5
routed to this layer survive the refactor:

| Dropped | Was |
|---|---|
| Surface gating | `spec.surfaces` + `registry.py:109` |
| predicate gating (per-request, fail-closed) | `registry.py:select_tool_specs` |
| per-session frozen tool list | `registry.py` `surface_only` |
| stage-based subsets | `STAGE_TO_TOOL_SUBSETS` |

This is a **decision, not an omission** — which is the whole reason plan
0028 §5 forced the question. Consequences, so nobody re-derives them:

- Plan 0028 §11 debts **5, 6 and 10** are closed by this ruling: the
  `surfaces` fail-open→fail-closed inversion, the `STAGE` permissive
  default, and the predicate event sink all die with their features.
- `ToolPolicy.tags` loses its stated purpose ("labels for the assembly
  layer to filter on"). It stays — `orchestration.py:201` dispatches on
  `"mcp" in policy_tags` — but the docstring should stop promising a
  filter that will not exist.
- The replacement is **a new entry/interaction layer** the owner will
  design separately, taking harness9 plus the existing CLI / Channel /
  Desktop surfaces as input. Tool visibility, if it returns at all,
  returns as that layer's concern — not as four fields on a spec.

### ~~Scheduling constraint the owner has set~~ — **cleared**

**Fix R3 (approval time charged to `tool_timeout`) before any Surface
binds an `ApprovalChannel`.** Done in the parallel-tool-calling round
above, inside the window where nothing bound one and the exposure was
zero. A Surface may now bind an `ApprovalChannel` without inheriting an
intermittent failure nobody could reproduce — it still owes its own
deadline on its own prompt, which is a requirement rather than a debt.

### What step 5 inherits

Plan 0028 §11 carries a **16-row table of debts, every one with
reproducible evidence**, found by step 4's two evaluations. Read it
rather than a summary. Debts **1 and 2 — the write barrier and the
approval timeout — are closed** by the parallel-tool-calling round
above; read that section instead, and note that the path lock survives
the barrier rather than being replaced by it. The one that still bites
here:

3. **Migration cannot be mechanical.** `ToolPolicy`'s defaults are
   inverted relative to `ToolSpec` (`low→HIGH`, `AUTO→ASK`,
   `allowed_in_background True→False`), and `surfaces` gating flipped
   from fail-open to fail-closed. Any existing spec migrated without
   restating its policy changes behaviour silently.

### Named here so it stops being invisible

harness9 has an entire `web_safety.go` — scheme allow-list, userinfo
rejection, DNS resolution checked against eight CIDR ranges including
`169.254.0.0/16` cloud metadata, fail-closed on DNS failure, re-run on
every redirect hop. This repo's `web_fetch` checks whether the URL starts
with `http://` or `https://`, and nothing else. Step 4 not building it
was correct and in scope; the problem was that plan 0028's parity table
folded it into a count of "built-in tools" and so **never asked the
question it asked of `safe_path.go`**. Not a step-4 defect.

> **Half resolved in step 4.5.** `omicsclaw/tools/_websafety.py` now
> answers it for the *new* layer, and goes past the reference by pinning
> the socket to the address it checked. **The legacy `web_fetch` is
> untouched and still open** — `runtime/tools/builders/engineering.py`'s
> URL-prefix check is what every surface uses today, and closing it is
> the migration's work, not this layer's.

Cheap capabilities plan 0027's evaluation found were **not** blocked by
any missing layer: per-tool engine-side duration on the event payload
(#35) **shipped** with the parallel-tool-calling round as
`EngineEvent.duration_s`; context-window reporting (#20) is still open
and still cheap — `usage.input_tokens` is already on `TURN_END`, and
`provider/_model_limits.get_model_limits()` shipped in step 2.

Follow the shape that worked for steps 2, 3 and 4: write a plan **in
Chinese** (`docs/plans/`), get it reviewed, dispatch implementation to
subagents, then dispatch **separate, read-only** evaluation before
declaring it done — one for correctness, one for harness9 parity. Give
the parity evaluator a feature-inventory table to audit rather than
letting it freelance, and tell it to distrust the table. Repairs are
their own task afterwards, by an agent that neither wrote nor judged.

Two refinements step 4 paid for:

- **Never tell an evaluator a defect you already know about.** The
  coordinator had reproduced the policy-override failure before
  dispatching; it stayed unsaid, and one evaluator hit it independently.
  That convergence is worth more than any single report, and it is only
  available once.
- **Aim the evaluation at the seams, explicitly.** Seven of step 4's
  nine repaired defects sat between lanes, exactly as step 3 predicted.
  Every implementation task was self-consistent inside its own lane.
- **Any mutation harness must run `-rfE --continue-on-collection-errors`.**
  A mutation that breaks an import fails at *collection*, and `pytest
  -rf` does not list collection errors — so it gets misreported as a
  surviving mutant. Two agents lost time to this before it was written
  into every dispatch.

Two lessons from step 3 that cost real time:

- **Re-verify every literal borrowed from harness9 in Python.** Ported
  structure is an asset; ported string tables, boundary conditions and
  "structurally impossible" claims are liabilities. Three of step 3's
  eight defects were literals that were correct in Go and inert here.
- **Parallel subagents each stay correct inside their own lane, and the
  defects collect on the boundaries between lanes.** Four of the eight
  sat between the engine and the already-shipped adapters — which no
  implementation task owned. Aim the evaluation there deliberately.
