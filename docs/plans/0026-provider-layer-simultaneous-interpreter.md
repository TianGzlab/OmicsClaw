# Plan 0026 — Provider layer: the simultaneous interpreter

Step 2 of the staged framework rebuild. Step 1 (ADR 0077) delivered
`omicsclaw/schema/` — vendor-neutral types that nothing can yet turn into
a real request. This step builds the layer that can.

**Status: complete (2026-09-17). See §11 for the outcome.**

## 1. Goal

One interface the Main Loop programs against, so switching or adding an
LLM backend never touches loop logic:

```
Engine ──▶ LLMProvider ──▶ vendor SDK
             (interface)      (OpenAI / Anthropic / DeepSeek / Ollama …)
                  │
                  └── speaks only omicsclaw.schema types
```

The Provider is a **simultaneous interpreter**: schema types go in,
schema types come out, and every vendor-shaped field name lives and dies
inside one adapter file.

### Non-goals

- The Main Loop itself (step 3).
- The Tool Registry / executor (see §9 open question Q3).
- Migrating any existing caller. Nothing is wired to this layer in this
  step; the old `providers/` keeps serving the live code untouched.
- Deleting old code. Removal happens when its replacement is wired.

## 2. The interface

### harness9's shape, which this follows

```go
Generate(ctx, messages []Message, availableTools []ToolDefinition)
    → (*Message, *Usage, error)
GenerateStream(ctx, messages, availableTools)
    → (<-chan StreamChunk, error)
```

Two methods. Note what is *absent* from the signature: model,
temperature, max_tokens, thinking budget. Those live on the provider
instance, set at construction. Only the two things that actually change
every turn — the conversation and the available tools — are parameters.

Two properties fall out of that, both worth keeping:

- **`availableTools=None` strips all tools.** harness9 uses this as the
  Thinking/Action phase switch: pass no tools and the model must reason;
  pass tools and it may act. A separated Thinking phase becomes possible
  without any new interface.
- **The Engine never learns model configuration.** It cannot, because
  there is nowhere to put it.

### Proposed Python form

```python
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion: ...

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    def bind(self, **overrides: Any) -> LLMProvider:
        """Cheap immutable copy with different model / max_tokens / …"""
```

Three deliberate departures from the Go original:

| Departure | Why |
|---|---|
| `async` + `AsyncIterator` | The project is already async (`AsyncOpenAI`). Go's goroutine+channel has no direct Python analogue; an async generator is the idiom. Cancellation rides on task cancellation instead of `ctx`. |
| Returns one `Completion` | Go's `(*Message, *Usage, error)` is multi-return idiom. A frozen 3-field result (`message`, `usage`, `finish_reason`) is the Python equivalent and gives `finish_reason` a home — which the current code reads but has nowhere to put. |
| `bind()` | harness9 fixes the model per instance. OmicsClaw genuinely varies it per request: `MessageEnvelope` carries `model_override`, `max_tokens_override`, and `extra_api_params`, and Desktop title generation pins its own profile. `bind()` admits that without putting model config in the hot-path signature. |

**Alternative considered — a `CompletionRequest` struct per call.** It
makes every knob explicit and loggable, but it moves model configuration
into the Engine's hands, which is the coupling this layer exists to
prevent. Recommendation: `bind()`. Flagged as Q1 for review.

## 3. Files

```
omicsclaw/provider/
├── __init__.py            ~40    public surface
├── base.py                ~120   LLMProvider Protocol, Completion, ProviderError
├── config.py              ~140   ProviderConfig + resolution from presets/env
├── openai_provider.py     ~320   OpenAI-compatible adapter (+DeepSeek/Ollama/…)
├── anthropic_provider.py  ~300   Anthropic Messages adapter
├── _accumulator.py        ~90    shared streaming tool-call accumulator
└── _model_limits.py       ~80    context/output window registry
                          ~1090
tests/provider/
├── test_base.py                  Protocol conformance + a FakeProvider
├── test_openai_provider.py       conversion both directions, no network
├── test_anthropic_provider.py    ditto, incl. tool_result batching
├── test_accumulator.py           streaming fragment reassembly
└── test_model_limits.py
```

No network in any test. Conversion is pure functions over dicts; the SDK
call is the only thing mocked.

## 4. What migrates from the existing `providers/`

The current package is 2,426 lines and holds real, hard-won configuration
knowledge. This step **copies forward** rather than reinventing:

| Existing file | Lines | Disposition |
|---|---|---|
| `registry.py` | 668 | **Migrate.** 13 presets (deepseek, openai, anthropic, gemini, nvidia, siliconflow, openrouter, volcengine, dashscope, moonshot, zhipu, ollama, custom) + detect order + model lists. Becomes `config.py`'s data. Highest-value asset here. |
| `models.py` | 470 | **Migrate the cache-breakpoint logic** (`apply_prompt_cache_breakpoints`, `_mark_last_tool`) into the adapters, where it belongs — it emits Anthropic `cache_control`, which is vendor-shaped. |
| `timeout.py` | 73 | **Migrate** into `config.py`. |
| `patches.py` | 260 | **Retire the DeepSeek half.** Its own docstring says it exists because "OmicsClaw's autoagent … does not capture `reasoning_content` from past responses". `schema.Message.reasoning_content` now does, so the adapter emits it natively and the patch becomes dead. Verify against a live DeepSeek call before deleting. |
| `chat_completion.py` | 74 | **Superseded** by `openai_provider.py`. |
| `runtime.py` | 319 | **Defer.** Process-global active-provider state; belongs to whatever wires this up, not to the adapter. |
| `ccproxy.py` | 561 | **Defer.** Claude-Code-proxy transport. Assess as its own provider once the two primary adapters are proven. |

Nothing is deleted in this step.

## 5. Traps harness9 already paid for

These are the details that make the difference between a working adapter
and a subtly broken one. Each is a required test case.

1. **Anthropic stream indices are not 0-based.** The streaming index is
   the *content-block* index. With extended thinking or leading text, the
   `thinking`/`text` block occupies index 0 and `tool_use` starts at 1 —
   key set `{1,2,3}`, not `{0,1,2}`. harness9 carries an explicit fix
   note: iterating `for i in range(len(accs))` **silently drops the last
   tool call**. Collect actual keys, sort, then emit.

2. **Reasoning arrives under three different field names.** DeepSeek-R1
   uses `delta.reasoning_content`; OpenRouter proxying GPT uses
   `delta.reasoning`. harness9 reads both out of the raw JSON. Ollama has
   its own. Try each, take the first non-empty.

3. **OpenRouter and Requesty need `include_reasoning=true`** in the
   request body or they return no reasoning at all. harness9 switches on
   the base URL containing `openrouter` / `requesty`. Harmless elsewhere.

4. **Streaming usage needs opting in.** OpenAI only fills `usage` when
   `stream_options.include_usage=true`, and it arrives in a final chunk
   with an **empty `choices` array** — code that skips empty-choice chunks
   before checking usage loses all token accounting.

5. **Anthropic has no `tool` role.** Every tool result for a turn becomes
   a `tool_result` block inside **one** user message. Emitting one user
   turn per result is rejected by the API. Batching is correctness, not
   optimization.

6. **Anthropic needs tool arguments decoded.** The schema keeps
   `arguments` as a raw JSON string; Anthropic wants an object. Parse at
   the boundary, and fail loudly on malformed JSON rather than sending
   `{}`.

7. **Anthropic's `input_tokens` excludes cache reads.** Summing naively
   under-reports input. Add `cache_read_input_tokens` back to reach the
   schema's "total input" meaning.

8. **`is_error` must reach Anthropic's `tool_result.is_error`.** harness9
   notes this explicitly: passing the structured flag strengthens model
   self-correction versus leaving it to guess from a text prefix.

9. **Cancellation must not leak the stream.** In Go this is
   `select { case <-ctx.Done() }` on every send. In Python: `try/finally`
   around the async generator, closing the SDK stream, so a cancelled
   turn does not leave the HTTP connection open.

## 6. Test strategy

| Layer | How |
|---|---|
| Conversion (outbound) | schema → dict, asserted against a literal payload |
| Conversion (inbound) | recorded vendor response dict → schema, asserted field by field |
| Round trip | `decode(encode(m)) == m` over a parametrized message corpus |
| Streaming | a fake async chunk iterator, incl. the Anthropic index-from-1 case |
| Protocol conformance | `isinstance(FakeProvider(), LLMProvider)` via `runtime_checkable` |
| Usage | all four dialects (OpenAI nested, DeepSeek top-level, Anthropic, none) |

Live-API tests are **out of scope** and must not be added; harness9 keeps
its one live test (`orcarouter_live_test.go`) separately gated.

## 7. Acceptance criteria

1. `tests/provider/` passes with no network access.
2. `omicsclaw/provider/` imports nothing from `omicsclaw` except
   `omicsclaw.schema` — enforced by an AST test mirroring
   `tests/schema/test_schema_is_a_leaf_package.py`.
3. No import cycle: `python -c "import omicsclaw.provider, omicsclaw.providers"`
   succeeds in both orders.
4. Both adapters satisfy `LLMProvider` structurally.
5. All nine traps in §5 have a named regression test.
6. Zero changes to existing files. The step is purely additive.

## 8. Subagent task split

Four tasks. A blocks B and C; B and C are independent; D gates the step.

- **A — contract + config** (`base.py`, `config.py`, `_model_limits.py`,
  `test_base.py`, `test_model_limits.py`). Defines `LLMProvider`,
  `Completion`, `ProviderError`, and ports the 13 presets from
  `registry.py`.
- **B — OpenAI adapter** (`openai_provider.py`, `_accumulator.py`, tests).
  Covers traps 1–4, 9.
- **C — Anthropic adapter** (`anthropic_provider.py`, tests). Covers
  traps 5–9.
- **D — independent evaluation.** Runs after B and C. See below.

Each implementation task must read `omicsclaw/schema/` and the
corresponding harness9 file (`internal/provider/openai.go`,
`anthropic.go`, `tool_call_accumulator.go`) before writing code.

### Task D — independent evaluation (the step's gate)

A **separate** subagent, not one that wrote any of the code. Its job is
to judge, not to build. It is **read-only**: it fixes nothing, and it
touches nothing at all outside `omicsclaw/provider/` and
`tests/provider/`. Findings go in its report; repairs are dispatched
afterwards as their own task.

It answers three questions with evidence:

1. **Is it correct?** Does the code do what it claims — conversions
   lossless in both directions, streaming reassembly right, errors
   wrapped, cancellation clean? Does it actually satisfy `LLMProvider`
   structurally? Do the tests genuinely exercise the behavior, or do they
   assert against the implementation's own output?
2. **Does it match harness9's capability?** Trap by trap against §5, and
   feature by feature against `internal/provider/*.go`. Name anything
   harness9 handles that this does not.
3. **Did it stay in its lane?** `git status --porcelain` must show no
   modification to any pre-existing file. Any ` M ` outside
   `omicsclaw/provider/` or `tests/provider/` is a finding in itself —
   the rebuild is component-by-component, and a provider task silently
   editing the loop, the schema, or the old `providers/` defeats that.

Its report must separate **confirmed defects** (with a concrete failure
scenario) from **gaps versus harness9** from **style/consistency notes**,
and must state plainly if it could not verify something rather than
assuming it passes.

## 9. Decisions (reviewed and approved 2026-09-16)

- **Q1 — per-request overrides: `bind()`.** A `CompletionRequest` struct
  would move model configuration into the Engine's hands, which is the
  coupling this layer exists to prevent.
- **Q2 — package name: `omicsclaw/provider/` (singular).** It coexists
  with the existing `omicsclaw/providers/` (plural) during migration.
  **Once the provider layer is substantially complete, the remaining
  content of `providers/` is folded into it as a closing task** — see
  §10.
- **Q3 — tool interface: out of scope.** This step is Provider-only. The
  Tool Registry is its own package and its own step, as in harness9 and
  in the tutorial's next chapter.
- **Q4 — `ccproxy.py`: deferred.** Port it only after the two primary
  adapters are proven.

## 10. Closing task — absorbing `providers/` (after B and C land)

Not part of tasks A–C. Once `LLMProvider` has two working adapters, a
final task folds the plural package in and removes the duplication:

1. Re-point `registry.py`'s remaining consumers at `provider/config.py`.
2. Port `ccproxy.py` as a third adapter (Q4's deferred work).
3. Decide `runtime.py`'s active-provider state — likely moves to whatever
   wires the Engine, not into the adapter layer.
4. Verify the DeepSeek `patches.py` half is genuinely dead against a live
   call, then delete it.
5. Delete `chat_completion.py` and `providers/` once nothing imports it,
   collapsing singular and plural into one package.

Until that task runs, `providers/` stays untouched and live.


## 11. Outcome (2026-09-17)

Tasks A–D ran, plus one repair round. **396 tests pass**, no network, no
change to any pre-existing file.

| Artifact | Lines |
|---|---|
| `omicsclaw/provider/` | ~2,700 |
| `tests/provider/` | ~3,600 |

All nine traps in §5 are handled; eight were confirmed by mutation
(breaking the line and watching the named test go red). Task D ran 71
mutations against the finished layer and 66 were caught.

**The layer exceeds harness9 on six counts**, five of them originally
mis-credited in §5 as ports rather than additions — worth correcting
here, because the plan claimed the reference harness had already paid for
them:

- tool-result batching (harness9 `anthropic.go:286` emits one user turn
  per result — rejected by the API for parallel calls);
- trap 7's cache-read repair (harness9 reads raw `InputTokens`);
- system-prompt joining (harness9 keeps only the last);
- persisted `reasoning_content` on both paths;
- full JSON-Schema passthrough for tools (harness9 flattens to
  `properties` / `required`, dropping `$defs`);
- ADR 0024 `cache_control` breakpoints, which have no counterpart there.

**Two coordinator arbitrations** the implementing agents surfaced rather
than deciding:

1. *Vendor SDK imports must be visible.* One adapter reached its SDK
   through `importlib`, which passed the layering test while enforcing
   nothing against it. Both now use a plain `import` inside the client
   factory: laziness comes from *where* the import sits, not from making
   it dynamic. The layering test was narrowed to the contract modules —
   applying an SDK ban to an adapter forbids the layer's whole purpose —
   and two tests were added: one requiring each adapter to declare its
   SDK visibly, one importing every module with both SDKs blocked.
2. *Claude 4.6 sends the adaptive thinking shape.* `budget_tokens` is
   removed on every later model and deprecated here, and
   `providers/models.get_default_features` already returns adaptive for
   any `4-6` / `4-7` match — so the legacy shape on the preset's default
   model would have been both a latent 400 and a regression against live
   behaviour. Two tests that pinned the old shape were rewritten; the
   legacy path keeps its coverage on Haiku 4.5, where it is not a
   deprecated alternative but the only way to ask for thinking.

### Carried forward, deliberately

Not defects in what shipped — known work the next steps inherit:

- `StreamChunk` has no field for `finish_reason` / `stop_reason`, so a
  stream truncated by the output ceiling is indistinguishable from a
  normal end. `Completion.finish_reason` covers the blocking path only.
- `Message` cannot hold an Anthropic thinking-block signature, so the
  Thought is readable in history but cannot be replayed to the model that
  produced it. A schema change (ADR 0077), not a provider fix.
- `StreamChunkType.ERROR` is dead: both adapters raise `ProviderError`
  rather than yielding an error chunk. A loop written to switch on chunk
  type would carry an unreachable branch.
- The ADR 0024 `cache_control` breakpoints reached the OpenAI adapter
  only — leaving native Anthropic, the one backend that caches nothing
  without an explicit breakpoint, as the worst-affected.
- `anthropic` is declared in no manifest; it arrives only transitively.
- The client-construction tests build a fake SDK module shaped after the
  adapter, so they verify plumbing rather than vendor compatibility.
  Nothing here has been exercised against a live endpoint.
