# Spec: Output Ownership Contract

## Objective

Separate scientific/native skill artifacts from shared top-level output UX.
Skill scripts should produce native outputs such as `report.md`, `result.json`,
tables, figures, h5ad files, and reproducibility command files. The shared
runner owns user-navigation artifacts that wrap a completed run:
`README.md` and `reproducibility/analysis_notebook.ipynb`.

## Commands

```bash
python -m pytest tests/test_output_ownership_contract.py -q
python -m pytest tests/test_output_ux.py -q
```

## Project Structure

- `omicsclaw/core/skill_runner.py`: finalizes output directories and writes
  runner-owned README/notebook artifacts.
- `omicsclaw/common/report.py`: native report/result helpers plus runner-owned
  README helper used by the runner.
- `omicsclaw/common/notebook_export.py`: runner-owned notebook generation.
- `skills/**`: skill scripts; should not call runner-owned README/notebook
  helpers directly.

## Code Style

Skill scripts may keep imports for native helpers:

```python
from omicsclaw.common.report import generate_report_header, write_result_json
```

Runner-owned UX belongs in the runner finalization path:

```python
notebook_path = write_analysis_notebook(...)
readme_path = write_output_readme(..., notebook_path=notebook_path)
```

## Testing Strategy

- Add a static corpus contract that fails when files under `skills/` import or
  call `write_output_readme`, `write_analysis_notebook`, or
  `write_standard_run_artifacts`.
- Keep existing runner UX tests proving `run_skill()` produces README and
  notebooks centrally.
- Avoid executing heavy skills in this contract; direct skill demo migration can
  be handled by follow-up tests.

## Boundaries

- Always: preserve native `report.md`, `result.json`, tables, figures, h5ad
  files, and reproducibility command files.
- Ask first: deleting direct script backward compatibility expectations.
- Never: remove scientific outputs to satisfy UX ownership.

## Success Criteria

- No skill script directly imports or calls runner-owned README/notebook helpers.
- `run_skill()` still creates `README.md` and
  `reproducibility/analysis_notebook.ipynb`.
- Existing focused output UX tests remain green.
