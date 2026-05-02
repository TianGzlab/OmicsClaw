# Plans Index

This directory stores dated, multi-step execution plans for durable OmicsClaw
development work.

## Tracked Entries

- [2026-05-02-github-r-package-preflight.md](2026-05-02-github-r-package-preflight.md)
  — audit Tier 3 GitHub-only R package dependency closures and preinstall
  conda-resolvable install-time dependencies to avoid avoidable CRAN/Bioc
  source builds.
- [2026-05-02-mintlify-docs.md](2026-05-02-mintlify-docs.md)
  — implement the Mintlify Chinese docs site (20 pages across 7 groups)
  modeled on `repo_learn/langcli/docs`; archive existing English MDs to
  `docs/_legacy/`.
- [2026-04-30-conda-env-management-plan.md](2026-04-30-conda-env-management-plan.md)
  — implement the four-tier mamba-first conda install (`environment.yml`,
  `0_setup_env.sh`, vendoring stub, removal of `install_r_dependencies.R`).
- [2026-04-16-remote-connection-guide-refresh.md](2026-04-16-remote-connection-guide-refresh.md)
  — refresh the remote connection guide so it matches the current
  `oc app-server` + remote control-plane behavior after the latest backend
  optimizations.
- [2026-04-15-remote-contract-hardening.md](2026-04-15-remote-contract-hardening.md)
  — harden the new remote control-plane contract so session ownership, job
  state transitions, and metadata stay truthful before the real Executor lands.
- [2026-04-14-provider-model-normalization.md](2026-04-14-provider-model-normalization.md)
  — normalize stale cross-provider model leftovers so backend status surfaces
  expose a coherent provider/model pair.
- [2026-04-14-oauth-runtime-hardening.md](2026-04-14-oauth-runtime-hardening.md)
  — harden OAuth logout/runtime cleanup, provider config persistence, and
  ccproxy/app-server port conflict handling.
- [2026-04-11-app-backend-authority-convergence.md](2026-04-11-app-backend-authority-convergence.md)
  — converge notebook file APIs, runtime config ownership, and backend launch
  discovery under the upstream backend contract.
- [2026-04-11-native-app-notebook-backend.md](2026-04-11-native-app-notebook-backend.md)
  — migrate interactive notebook backend ownership into upstream
  `omicsclaw.app.server` and remove OmicsClaw-App wrapper ownership.

## Conventions

- Use this directory only for plans with meaningful coordination or handoff
  value.
- Update this index whenever the directory contents change.
