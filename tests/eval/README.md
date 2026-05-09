# Behavioral Parity Eval Suite

Real-LLM evaluation of OmicsClaw's compressed prompt + tool list behavior.
Validates the cumulative −76% per-turn token compression (PRs #106-#111)
did not degrade model behavior on representative queries.

## Why this exists

PR #106-#109 cut the system prompt by 79%; PR #110-#111 cut the tool
list by 74%. Snapshot tests prove the *structural* changes are
intentional, but no test had exercised real LLM behavior. This suite
fills that gap with 18 LLM-driven cases (15 invariant + 3 audit-log
sanity).

## Running

```bash
# Default pytest run — eval cases excluded
pytest

# Run the eval suite (requires LLM_API_KEY)
LLM_API_KEY=... pytest -m eval

# Single case
LLM_API_KEY=... pytest -m eval -k "sc_de_routes_correctly"

# Convenience wrapper that also writes a markdown report
LLM_API_KEY=... python scripts/run_eval.py
```

## Environment contract

The eval suite resolves its endpoint + model from the **same env semantics
that drive `bot/run.py`** (via
`omicsclaw.core.provider_registry.resolve_provider`). When production
runs DeepSeek v4-flash, eval measures DeepSeek v4-flash — no foreign
default that masks regressions on the model users actually hit.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | (auto-detect) | Selects provider preset (`deepseek`, `anthropic`, `openai`, ...) |
| `LLM_API_KEY` | (none) | Generic API key. Alternatively set the provider-specific key (`ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / ...) and the provider auto-detects |
| `LLM_BASE_URL` | (provider preset) | Override endpoint when not using the preset's default |
| `OMICSCLAW_MODEL` | (provider preset) | Production model name; eval inherits this |
| `EVAL_MODEL` | (inherits `OMICSCLAW_MODEL`) | Eval-only override. Lets nightly cron sweep alternate models without touching `.env` — must pair with a compatible provider/base_url, otherwise the runner returns a 4xx |

When no provider key is found in env, all `@pytest.mark.eval` tests skip
gracefully — `pytest -m eval` exits 0 with skipped lines, no errors.

## Cost guard

| | per run | per week (nightly cron) |
|---|---|---|
| 18 cases × production model × temp=0 × N=1 | ~$0.05 (DeepSeek) — ~$0.50 (Anthropic) | one nightly run |

The marker exclusion (`addopts = '-m "not slow and not eval"'`) keeps
PR CI cost-free; only the explicit nightly workflow plus manual
invocations spend tokens.

## Output

Per-run artifacts land in `tests/eval/results/<UTC-timestamp>/`:

```
results/2026-05-09T08:42:00Z/
├── REPORT.md              # human-readable summary
├── routing__sc_de.json    # raw LLM round + invariant outcomes per case
├── routing__spatial.json
└── ...
```

`scripts/run_eval.py` generates `REPORT.md` after pytest exits.

## Layout

| File | Purpose |
|---|---|
| `conftest.py` | `real_llm_runner` async fixture; graceful skip without API key |
| `invariants.py` | 15 `EvalCase` instances covering the 5 categories |
| `assertions.py` | Pure-Python helpers for routing / tool-call / marker checks |
| `test_behavioral_parity.py` | Parametrized eval over the 15 cases |
| `audit_log_sanity.py` | 3 sanity comparisons against `bot/logs/audit.jsonl` history |
| `results/` | Per-run JSON + markdown artifacts (gitignored except `.gitkeep`) |

## Interpreting failures

- **must-priority failure** → real regression; fix before merging downstream prompt changes
- **should-priority failure** → emitted as `UserWarning`; investigate but doesn't block CI
- **skip with "LLM_API_KEY not set"** → expected when running locally without credentials
