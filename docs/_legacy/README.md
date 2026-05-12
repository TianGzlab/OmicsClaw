# Legacy English Documentation (Archived)

These English Markdown files were the previous **developer-facing** documentation
of OmicsClaw. They have been superseded by the Mintlify Chinese documentation
site at the repository root (`mint.json` → `docs/<group>/*.mdx`).

They are kept here as **internal reference** for contributors and maintainers.
They are excluded from the public docs site via `mint.json`'s `excludes` field.

## New ↔ Legacy Mapping

| Legacy file (English)           | Replaced by (Chinese MDX)                     |
|---------------------------------|-----------------------------------------------|
| `architecture.md`               | `docs/architecture/overview.mdx`              |
| `skill-architecture.md`         | `docs/architecture/skill-system.mdx`          |
| `INSTALLATION.md`               | `docs/introduction/quickstart.mdx`            |
| `METHODS.md`                    | (distributed across `docs/domains/*.mdx`)     |
| `R-DEPENDENCIES.md`             | `docs/engineering/replot.mdx`                 |
| `MEMORY_SYSTEM.md`              | `docs/engineering/memory.mdx`                 |
| `remote-connection-guide.md`    | `docs/engineering/remote-execution.mdx`       |

## Why archive instead of delete

These files contain detail (R package versions, environment troubleshooting,
SSH bootstrap commands, etc.) that the new user-facing docs intentionally
elide. Maintainers may need them when debugging environment or deployment
issues. Treat them as **append-only** — do not edit; update the corresponding
new MDX page instead.
