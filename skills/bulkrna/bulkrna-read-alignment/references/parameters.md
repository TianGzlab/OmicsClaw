# Parameters

`summarize` defaults to STAR, matching the CLI. Choose `hisat2` or `salmon`
explicitly; filenames do not override that choice. STAR/HISAT2 include unique
and multimapped counts. Salmon meta_info reports total mapped counts only.

The generated API section in `../SKILL.md` lists arguments and defaults.
The CLI `--help` lists file and report options.
