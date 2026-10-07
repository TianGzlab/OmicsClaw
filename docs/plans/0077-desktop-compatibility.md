# Desktop v3 compatibility and release checks

Status: local implementation and independent review complete, 2026-10-07.
Installer publication, hosted CI and Mac installation remain unverified.

## Problem and scope

A Mac App requiring Desktop SSE v2 rejected the current v3 backend. Running
the historical App validator against a real v3 health response reproduced
the user's exact error. The current App accepted it, but both source states
used package version `0.1.7`.

The user approved stable protocol rules, optional capabilities, compatibility
checks across the two repositories, and traceable releases. One agent owns
implementation and a second agent reviews it independently; the coordinating
agent verifies delivery. Native automatic updates remain disabled under App
ADR 0003. This work does not publish installers, change branch protection, or
update the user's Mac installation. The user subsequently authorized pushing
both repositories to their configured `origin/main`, App first.

Backend baseline: `8d8ad9ef5c1eefcf89de7f2871b014c200c63e42`.
App baseline: `a9c50011edcb2efedcb863d736dff6d211da3c9f`.
Pre-existing presentation work and the earlier connection diagnosis are
outside this implementation and must be preserved.

## Compatibility rules

- Desktop request and SSE major version 3, and interrupt version 1, remain
  stable while existing clients can send the same requests and interpret the
  same responses. Internal changes and optional additions do not bump them.
- Removing fields, changing their meaning or types, making optional input
  mandatory, or changing required lifecycle behavior needs a compatibility
  decision and a matching client release. The current major-version refusal
  stays in place.
- Optional capability metadata extends `/health`. Unknown names do not break
  a connection. A v3 backend without that metadata retains the behavior v3
  already guarantees. Known capability values need explicit parsing rules.
- Remote file tree and file serving are the first capability consumers. The
  App must gate actual requests and the corresponding user interface. Resume
  remains part of the established v3 contract in this change.
- Package versions and protocol versions are separate. A healthy connection
  depends on the protocol, not matching application package numbers. Build
  identity distinguishes source states sharing a development version.

## Validation and CI ownership

Behavior tests cover public `/health`, streamed chat, approval and abort
routes. They use a scripted provider and real HTTP, with no model credentials
or live model requests. They must detect a changed mandatory field or broken
approval/stop behavior, not merely compare version constants.

The App repository is private; the backend repository is public. The default
backend workflow token cannot read the App repository, and untrusted public
PR code must not receive private App source or credentials.

1. Public backend CI runs a frozen v3 consumer contract test owned by the
   backend. It contains no copied private App implementation.
2. Private App CI runs real backend pairing against both current App code and
   the immutable App baseline above. The baseline is a known v3 source commit,
   not a claim that a matching installer has been published. The first verified
   release should become the subsequent released-client baseline.
3. The pairing command also accepts a local backend checkout for development.
   CI records exact source revisions. App packaging depends on this check.
4. A trusted backend `main` push, or a manual run restricted to that branch,
   can use the existing `APP_REPO_TOKEN` secret to check out App source in an
   ephemeral sibling directory. The token is limited to checkout, credentials
   are not persisted, and source is not uploaded as a diagnostic artifact.
   Public PRs never run this job. Missing prerequisites must not produce a
   successful compatibility result.
5. Required-status configuration remains separate from the workflows. A
   read-only GitHub check on 2026-10-07 found neither classic protection nor
   rulesets on backend `main`. A push check detects a regression after merge;
   it does not itself prevent that merge. The existing secret's access scope
   has not been exercised by the new workflow.

## Release behavior

Build metadata and the App's version view identify the source revision.
Mismatch guidance names the incompatible protocol and leads to the public
installer destination without claiming an unverified installer is compatible.
The public release API on 2026-10-07 lists `v0.1.7`, published on 2026-05-20,
as latest, with installers and checksums but no source/compatibility manifest.

Formal releases validate package version, tag and source identity before any
platform upload. A new source state must not silently overwrite a released
version. New release metadata must support safe retries of the same release.
The public installer repository and the update-check destination must agree.

## Acceptance

- Existing v3 without capabilities connects; compatible additions and unknown
  capability names connect; unsupported major versions still fail.
- Explicitly unavailable remote file capabilities prevent requests and give a
  useful UI response. Existing v3 file behavior remains usable.
- Real HTTP tests exercise chat text and completion, an approval decision and
  its effect, and stopping an active exchange. Both App revisions are actually
  loaded in the private pairing test.
- Build identity is visible and release checks run before artifact upload.
- Targeted backend tests, App typecheck, relevant lint and tests pass. Any
  unrelated baseline failures are identified with evidence.
- The independent reviewer checks Standards and Spec separately, reports
  reproducible findings, and reviews fixes before delivery.

## Delivery evidence

The implementation agent completed both repositories. The independent reviewer
closed all findings and reported no remaining P1/P2 issues. The coordinating
agent repeated the affected checks and tested that a protocol regression fails.

| Check | Result |
| --- | --- |
| Backend Desktop and launch regression | 575 passed, 3 skipped |
| Final build-identity and public consumer tests | 23 passed, 1 skipped |
| App full unit suite, four workers | 2,089 passed, 4 skipped |
| Final App health, About, release and build-identity tests | 26 passed |
| Current and fixed App source against the changed backend | 6 scenarios passed |
| Both App sources against the CI backend baseline | 6 scenarios passed |
| App web and Electron typecheck | Passed |
| App lint | 0 errors, 48 warnings |
| Electron JavaScript bundle | Passed; no native installer produced |

The broad suites ran before the final review fixes; the affected tests and real
pairing were rerun after those fixes. The first App run at default concurrency
had one timing failure in the unchanged jobs-events test. That test passed in
isolation, and the full suite passed with four workers. Tests unset the stale
local `SSH_AUTH_SOCK` so they do not depend on a nonexistent developer socket.

Backend commands, from this repository:

```bash
/opt/conda/envs/OmicsClaw/bin/python -m pytest \
  tests/entry/test_desktop_*.py tests/launch/test_desktop_settings.py \
  -q -o addopts=''
/opt/conda/envs/OmicsClaw/bin/python -m pytest \
  tests/entry/test_desktop_wire_contract.py \
  tests/entry/test_desktop_v3_consumer.py \
  -q -p no:cacheprovider -o addopts=''
```

App commands, from the sibling `OmicsClaw-App` repository:

```bash
env -u SSH_AUTH_SOCK ./node_modules/.bin/tsx \
  --import ./src/__tests__/setup/jsdom-setup.ts \
  --test --test-concurrency=4 \
  src/__tests__/unit/*.test.ts src/__tests__/unit/*.test.tsx
env -u SSH_AUTH_SOCK ./node_modules/.bin/tsx \
  --import ./src/__tests__/setup/jsdom-setup.ts --test \
  src/__tests__/unit/backend-health.test.ts \
  src/__tests__/unit/about-compatibility.test.tsx \
  src/__tests__/unit/release-identity.test.ts \
  src/__tests__/unit/build-env-script.test.ts
npm run typecheck
npm run lint
node scripts/build-electron.mjs
OMICSCLAW_COMPAT_PYTHON=/opt/conda/envs/OmicsClaw/bin/python \
OMICSCLAW_COMPAT_BACKEND=/workspace/dataset/private/zhouwg_data/OmicsClaw \
  node scripts/test-desktop-compatibility.mjs
```

The reviewer independently ran 176 backend tests with one skip, 26 App tests,
the six pairing scenarios, and five release-script scenarios using temporary
Git repositories and a simulated GitHub CLI. Both workflow files passed YAML
and dependency checks, including source SHA binding, upload ordering, event
guards, and private-source log handling. `git diff --check` passed in both
repositories.

Standards review closed one finding: old documentation required a protocol bump
for every field change, contradicting the stable-major rule. Spec review closed
four groups of findings:

- Build identity now includes nonignored, untracked files in its dirty state.
- Approval tests require a successful tool result. Injecting a tool failure now
  fails the consumer test even if the scripted provider emits its final text.
- All release jobs use one resolved source SHA, and manual and tag-triggered
  runs of the same release share a concurrency group.
- A mismatch shows request, SSE and interrupt versions separately, so a request
  mismatch cannot misleadingly appear as matching SSE versions.

The coordinator also found that a new release could use a lower version. The
release check now requires numerical version growth, while allowing retries
of an existing release with the same source identity; the reviewer verified
both cases.

For a negative control, the coordinator changed only the backend SSE major
from 3 to 4 in a temporary worktree. The real historical App route returned
`503 incompatible-contract`, and pairing exited 1. Restoring version 3 made
all six scenarios pass. Temporary worktrees were removed. Local command logs
are under `/tmp/omicsclaw-desktop-compatibility/`; these are session evidence,
not committed artifacts.

Before the authorized push, backend `main` had advanced to `9f49c2b3` through
another task. The Desktop and launch regression was repeated on that base with
these changes: 576 passed, 3 skipped. Both App sources again passed all six
pairing scenarios. The public upstream also resolves the fixed backend SHA
used by App CI. The unrelated presentation files and their changelog entry
are excluded from these commits.

## Rollout and remaining limits

Land the App runner before the backend workflow that calls it. Run hosted CI
on the exact source revisions and verify `APP_REPO_TOKEN` access. Require the
public consumer check in backend branch protection, and inspect the trusted
private pairing result before releasing a backend update. The workflow alone
does not enforce a merge policy.

The App's `0.1.8` is an unreleased candidate. A formal release must pass source
identity checks, publish its manifest and installers, and be tested on a Mac.
The installed v2 client still needs that first manual upgrade. Both source
revisions in the pairing test use the current dependency tree; no historical
binary compatibility claim is made. Native automatic updates stay disabled.
