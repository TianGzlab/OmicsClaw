# 2026-04-16 Remote Connection Guide Refresh

## Goal

Refresh `docs/remote-connection-guide.md` so it matches the current
`oc app-server` + remote control-plane behavior after the recent remote/app
backend optimizations, while keeping README-level detail out of the guide.

## Scope

- Update the remote connection guide's setup, architecture, and troubleshooting
  language to match the current implementation.
- Remove or rewrite statements that are now outdated after the executor and
  remote route hardening work.
- Keep the guide user-facing; do not turn it into a route-by-route API spec.

## Non-Goals

- No backend code changes.
- No OmicsClaw-App code changes.
- No new remote features beyond documenting what already exists.

## Assumptions / Constraints

- Source of truth is the current Python backend implementation under
  `omicsclaw/app/server.py`, `omicsclaw/remote/`, and the relevant tests.
- README already carries the high-level remote-mode summary, so this guide can
  focus on practical setup and operations.
- Verification for this task is direct inspection of the edited docs and diff.

## File Map

- Modify `docs/remote-connection-guide.md`
- Modify `docs/superpowers/plans/README.md`
- Add `docs/superpowers/plans/2026-04-16-remote-connection-guide-refresh.md`

## Ordered Tasks

1. Compare the existing guide against the current backend behavior.
2. Record the refresh plan and update the plans index.
3. Rewrite the guide sections that are stale:
   - architecture / prerequisites
   - remote server startup
   - connection-profile guidance
   - dataset import / upload advice
   - job execution / logs / artifacts wording
   - troubleshooting entries
4. Re-read the edited sections and inspect the diff for correctness and scope.

## Verification Strategy

- Inspect the exact edited sections in `docs/remote-connection-guide.md`.
- Inspect `git diff -- docs/remote-connection-guide.md docs/superpowers/plans/README.md`.
- Confirm all doc claims line up with:
  - `README.md`
  - `omicsclaw/app/server.py`
  - `omicsclaw/remote/`
  - relevant tests under `tests/test_remote_*.py` and `tests/test_app_server.py`

## Acceptance Criteria

- The guide no longer claims remote execution is stubbed or blocked on
  `executor_not_implemented` as the normal path.
- Startup instructions use the current `oc app-server` flow.
- The guide reflects current workspace/auth behavior and large-file import
  guidance.
- Troubleshooting advice matches current backend behavior and supported routes.
