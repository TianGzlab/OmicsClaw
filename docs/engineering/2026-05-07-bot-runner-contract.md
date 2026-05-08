# Spec: Bot Skill Runner Contract

## Objective

Bot skill execution should share the same runner contract as CLI, interactive,
agent tools, app, and remote default jobs. Bot-specific code may own chat
preflight, media collection, memory capture, and user-facing formatting, but it
must not independently assemble `omicsclaw.py run ...` subprocess commands for
normal skill runs.

## Commands

```bash
python -m pytest tests/test_bot_runner_contract.py tests/test_bot_batch_key_preflight.py -q
```

## Project Structure

- `bot/core.py`: bot preflight, execution adapter, output collection, and chat
  formatting.
- `omicsclaw/core/skill_runner.py`: canonical skill execution contract.
- `tests/test_bot_runner_contract.py`: bot runner ownership guardrail.

## Code Style

Bot code should map tool args into `run_skill()` kwargs:

```python
result = await asyncio.to_thread(
    skill_runner.run_skill,
    skill_name,
    input_path=input_path,
    output_dir=str(out_dir),
    demo=mode == "demo",
    extra_args=extra_args or None,
)
```

## Testing Strategy

- Add static tests proving `_run_omics_skill_step()` and `execute_omicsclaw()`
  do not call `asyncio.create_subprocess_exec`.
- Add behavior tests proving bot execution invokes the shared runner adapter and
  still formats successful `report.md` output.
- Keep replot, upload, and non-skill subprocess helpers out of scope.

## Boundaries

- Always: preserve preflight pause behavior, output media collection, memory
  capture, and environment error classification.
- Ask first: changing bot public tool schemas.
- Never: duplicate CLI argument filtering outside the shared runner path.

## Success Criteria

- Normal bot skill execution routes through a shared-runner adapter.
- `_run_omics_skill_step()` and `execute_omicsclaw()` no longer start
  `omicsclaw.py run` subprocesses.
- Existing bot preflight tests continue to pass.
