# Superpowers Docs

This directory holds durable AI-development support materials for OmicsClaw.
It is the documentation-side equivalent of the workflow guidance pattern used
in `feishu_agent`'s `SPEC.md`.

The goal is not to mirror names only. The OmicsClaw playbooks are intended to
preserve the reference skills' core design:

- explicit core principles
- non-negotiable iron laws
- stage gates and stop conditions
- red flags and anti-rationalization checks
- concrete deliverables and verification expectations

## Structure

- [playbooks/README.md](playbooks/README.md) — on-demand workflow playbooks for
  debugging, TDD, verification, planning, parallelization, code review, and
  branch completion
- [plans/README.md](plans/README.md) — dated multi-step implementation plans
- [specs/README.md](specs/README.md) — dated design notes, specs, and
  completion summaries

Recent additions:

- `plans/2026-04-14-provider-model-normalization.md` — normalize stale
  cross-provider model leftovers so backend status surfaces stop exposing
  contradictory provider/model pairs
- `plans/2026-04-14-oauth-runtime-hardening.md` — harden OAuth logout/runtime
  cleanup, provider config persistence, and ccproxy/app-server port conflict
  handling
- `plans/2026-04-11-app-backend-authority-convergence.md` — converge notebook
  file ownership, runtime config authority, and backend launch discovery
  around the upstream backend contract
- `plans/2026-04-11-native-app-notebook-backend.md` — unify notebook backend
  ownership under upstream `omicsclaw.app.server`

## Conventions

- Use date-prefixed filenames for durable records.
- Update the relevant index `README.md` when adding or removing files here.
- Keep playbooks repository-specific, but detailed enough to constrain behavior
  under pressure.
