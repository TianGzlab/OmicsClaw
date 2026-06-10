# Methodology — bulkhic-mapping

> Implemented (bwa-mem2 + pairtools). See `_lib/mapping.py`.

## Capability

The 4DN upstream: trimmed Hi-C reads → deduplicated, QC'd `.pairs`.

## Workflow

1. **Reference** (`prepare_reference`) — reuse a local `reference_<genome>/<genome>.fa`
   or download the FASTA; build the **bwa-mem2** index; derive **chrom.sizes**
   from `samtools faidx` (offline, no UCSC chrom.sizes dependency).
2. **Per sample** (one streamed pipe + dedup):
   ```
   bwa-mem2 mem -SP5M -t N <index> R1 R2
     | pairtools parse --min-mapq 30 --walks-policy 5unique
                       --max-inter-align-gap 30 --drop-sam --add-columns mapq
                       --chroms-path <chrom.sizes> --assembly <genome>
     | pairtools sort --nproc N --tmpdir <tmp> -o <sorted.pairs.gz>
   pairtools dedup --output-stats <stats> --output <nodups.pairs.gz> <sorted>
   pairix <nodups.pairs.gz>
   ```
3. **QC** — parse the dedup `--output-stats` file into the 4DN library metrics.

## Method notes

- **`bwa mem -SP5M`**: `-S`/`-P` skip mate-rescue and proper-pair logic so each
  mate maps independently (Hi-C reads are chimeric ligation products); `-5`
  reports the 5'-most alignment as primary (canonical for the ligation site);
  `-M` marks split hits secondary. This is the 4DN / distiller / pairtools
  convention.
- **`pairtools parse --walks-policy 5unique`** handles multi-fragment "walks"
  (>2 alignments) by taking the 5'-most unique pair — the recommended default.
- **Dedup** removes PCR duplicates (identical mapped coordinates + strands).
- **QC metrics** (`bulkhic_qc_criteria`): valid-pair fraction (nodups/total),
  duplicate fraction (dups/mapped), cis fraction (cis/(cis+trans)), cis/trans
  ratio, and cis-long fraction (cis pairs > 20 kb / cis) — the single most
  informative library-complexity indicator.

## Resolution / restriction sites

Restriction-fragment assignment (`pairtools restrict`) is **not** run by default
— it is only needed for fragment-level resolution; bin-level Hi-C (the
cooler/cooltools path) does not require it.

## Dependencies

- CLI: bwa-mem2 (or bwa), samtools, pairtools, pairix
- Python: pandas

## References

- 4DN Hi-C processing pipeline — https://data.4dnucleome.org/resources/data-analysis/hi_c-processing-pipeline
- 4dn-dcic/docker-4dn-hic — https://github.com/4dn-dcic/docker-4dn-hic
- pairtools — https://pairtools.readthedocs.io/
