# Output contract

The current file inventory and conditional outputs are listed in
[`SKILL.md`](../SKILL.md#inputs--outputs). The `_api.py` functions return AnnData,
tables or Figures; they do not write reports or user output directories.
`examples/example_step.py` saves returned objects with `write_output`.

See the generated API section for argument defaults and return semantics.
CLI filenames are retained where their meaning remains valid; intentional
statistical/naming corrections are explained in the skill's Gotchas section.
