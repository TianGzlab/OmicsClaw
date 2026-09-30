# CLAUDE.md — OmicsClaw repository

`OMICSCLAW.md` is the runtime contract of the OmicsClaw analysis agent:
`omicsclaw/entry/assembly.py` puts it at the top of that agent's system
prompt, followed by `SAFETY_RULES` and `TOOL_GUIDANCE` from the same module.
Read it when a change affects what that agent is told, and when adding or
removing a skill (its routing table and counts there are kept by hand).

## Repository Maintenance Contract

When you are acting on repository maintenance, refactoring, or other
developer-facing tasks rather than end-user omics analysis:

1. Read `README.md` for what the project is and `CHANGELOG.md` for recent
   decisions and milestones.
2. Then read root `SPEC.md` and `AGENTS.md`.
3. Reply in the user's language and stay concise and execution-focused.
4. Use a concise plan, root-cause debugging, focused tests, and verification
   evidence for non-trivial repository changes.
5. When you make an important repository decision or complete a milestone,
   add an entry at the top of `CHANGELOG.md`. Change `README.md` only when a
   user-facing entry point, install step or headline feature changes; its
   What's New holds at most five items of one sentence each.
6. Run the `humanizer` skill (`.claude/skills/humanizer/SKILL.md`) in
   embedded mode over prose you write: code comments, docstrings, docs,
   plans, README text, commit messages and PR descriptions. Keep code,
   commands, paths and identifiers unchanged.

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues for `zhou-1314/OmicsClaw`. Use the `gh`
CLI (`gh issue create|view|list|comment|edit|close`), and infer the repository
from the current clone unless a command needs an explicit
`--repo zhou-1314/OmicsClaw`. "Publish to the issue tracker" means create an
issue; "fetch the relevant ticket" means read its body, labels and comments.

### Triage labels

Five canonical roles, each mapping to the GitHub label of the same name:

| Label | Meaning |
| --- | --- |
| `needs-triage` | A maintainer must evaluate the issue. |
| `needs-info` | More information is required from the reporter. |
| `ready-for-agent` | Fully specified and safe for an AFK agent. |
| `ready-for-human` | Requires human implementation or judgement. |
| `wontfix` | Will not be actioned. |

The first four may not exist yet. Create one only when a workflow first needs
to apply it; never create or mutate labels during read-only diagnosis.
