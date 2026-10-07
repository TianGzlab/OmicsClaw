# Methodology

`read_fastq` reads the leading 100000 records by default and accepts `.gz`.
`quality_control` computes per-base quality, Q20/Q30, GC, lengths and adapter
motif hits from sequence/quality strings. It does not trim reads.

- `read_fastq` rejects truncated FASTQ and unequal sequence/quality lengths.
- `quality_control` assumes Phred+33, not the older Phred+64 encoding.
- `adapter_rate` sums motif hits and can exceed 100% if a read contains multiple adapters.
