# Spec: Skill Help Contract

## Objective

Every registered primary skill script must support a cheap, deterministic
`--help` path. Maintainers, agents, the app backend, and bot surfaces need to
inspect a skill's CLI shape without providing input data, importing unavailable
runtime-only dependencies unnecessarily, or starting an analysis.

## Commands

```bash
python -m pytest tests/test_skill_help_contract.py -q
```

## Contract

- `python <skill_script.py> --help` exits with status `0`.
- Help output is non-empty and includes either `usage`, `options`, or `--help`.
- The command runs from the repository root with `PYTHONPATH` pointed at the
  repository root, matching how local development invokes scripts directly.
- The command must not require input files, demo data, external bioinformatics
  CLIs, R packages, or a running app/bot service.

## Boundaries

- Always: treat the runtime registry as the list of primary skill scripts.
- Ask first: changing public skill flags or removing legacy flags.
- Never: execute analysis work, mutate output directories, or contact network
  services during `--help`.

## Success Criteria

- A registry-derived contract test covers every primary skill script.
- Failures identify the skill alias, script path, command, and captured output.
- The test stays focused on help introspection, not demo execution.
