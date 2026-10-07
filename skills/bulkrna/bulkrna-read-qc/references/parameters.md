# Parameters

`read_fastq` reads the leading 100000 records by default and accepts `.gz`.
`quality_control` computes per-base quality, Q20/Q30, GC, lengths and adapter
motif hits from sequence/quality strings. It does not trim reads.

The generated API section in `../SKILL.md` lists arguments and defaults.
The CLI `--help` lists file and report options.
