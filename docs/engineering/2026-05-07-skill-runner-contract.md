# Spec: Shared Skill Runner Contract

## Objective

Move reusable skill execution behavior out of the root `omicsclaw.py` script so
CLI, interactive, app, bot, and remote execution can share one implementation.
The root script should remain a public CLI wrapper, but `run_skill()` must be
importable from `omicsclaw.core.skill_runner`.

## Contract

`omicsclaw.core.skill_runner` exposes:

```python
def run_skill(
    skill_name: str,
    *,
    input_path: str | None = None,
    input_paths: list[str] | None = None,
    output_dir: str | None = None,
    demo: bool = False,
    session_path: str | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    ...
```

The returned dictionary keeps the existing public shape:

- `skill`
- `success`
- `exit_code`
- `output_dir`
- `files`
- `stdout`
- `stderr`
- `duration_seconds`
- `method`
- `readme_path`
- `notebook_path`

## Behavior Requirements

- Alias resolution and `domain:skill` shorthand keep current behavior.
- `spatial-pipeline` keeps current chained execution behavior.
- Extra args are filtered through per-skill `allowed_extra_flags`.
- Successful runs still generate runner-owned `README.md` and
  `reproducibility/analysis_notebook.ipynb`.
- The root `omicsclaw.py` CLI delegates to this module instead of owning the
  implementation.

## Verification

```bash
python -m pytest tests/test_skill_runner_contract.py tests/test_output_ux.py -q
python omicsclaw.py run literature --demo --output /tmp/omicsclaw_literature_demo
```

## Boundaries

- Do not change skill script CLI flags in this slice.
- Do not migrate app/bot/remote call sites until the core importable runner is
  passing tests.
- Do not remove legacy aliases during runner extraction.
