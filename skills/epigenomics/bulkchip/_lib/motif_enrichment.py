"""
motif_enrichment.py — TF motif enrichment analysis for bulk ChIP-seq
                              using HOMER findMotifsGenome.pl.

Performs both **de novo motif discovery** and **known motif enrichment** in
ChIP-seq peak regions.  Can run on the full consensus peak set and/or on
differential-binding peak subsets (up/down from bulkchip-DA).

For a transcription-factor ChIP, the ChIP'd factor's own motif is expected to
top the known-motif ranking (a built-in positive control).  For histone-mark
ChIP, HOMER instead surfaces the co-bound TFs whose motifs are enriched under
the mark.

Pipeline
--------
  1. Prepare input BED (consensus peaks or DA subsets)
  2. HOMER findMotifsGenome.pl  → de novo + known motif enrichment
  3. Parse knownResults.txt     → ranked known motif table
  4. Parse homerResults         → ranked de novo motif table
  5. Summary plots: top known motifs bar chart, de novo motif logos

HOMER motif analysis
--------------------
  HOMER is **sequence-based**: it counts motif occurrences in peaks vs a
  shuffled/GC-matched background and reports enrichment p-values.
  It answers: "Which TF motifs are overrepresented in your ChIP peaks?"

  For TF ChIP, the recovered top motif should match the assayed factor.
  For histone marks, the enriched motifs point to the transcription factors
  recruited to (or co-occupying) those marked regions.

Dependencies
------------
  HOMER ≥ 4.11  (conda install -c bioconda homer)
    findMotifsGenome.pl must be in PATH
    Genome must be installed: configureHomer.pl -install <genome>
      OR provide --genome-fasta for HOMER to use directly

Output
------
  motif_enrichment/
    {peak_set}/                        — "all_peaks", "da_up", "da_down"
      knownResults.txt                 — HOMER known motif enrichment
      knownResults.html                — HOMER known motif HTML report
      homerResults.html                — HOMER de novo motif HTML report
      homerMotifs.all.motifs           — all de novo motifs (HOMER format)
      knownResults/                    — known motif logos (PNG)
      homerResults/                    — de novo motif logos (PNG)
    plots/
      top_known_motifs_{peak_set}.{pdf,png}
      top_denovo_motifs_{peak_set}.{pdf,png}
    top_motif_summary.tsv              — parsed top motifs across peak sets

References
----------
  HOMER  : Heinz et al. 2010, Mol Cell 38(4):576-589
           http://homer.ucsd.edu/homer/ngs/peakMotifs.html
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from omicsclaw.common.runlog import log_tool_output
except Exception:  # pragma: no cover - omicsclaw not importable in isolation
    def log_tool_output(cmd, result):  # type: ignore
        return None

logger = logging.getLogger(__name__)


# ===========================================================================
# Result dataclasses
# ===========================================================================

@dataclass
class KnownMotifHit:
    """One row from HOMER knownResults.txt."""
    motif_name:     str
    consensus:      str   = ""
    p_value:        float = 1.0
    log_p_value:    float = 0.0
    q_value:        float = 1.0
    n_target:       int   = 0
    pct_target:     float = 0.0
    n_background:   int   = 0
    pct_background: float = 0.0


@dataclass
class DeNovoMotifHit:
    """One de novo motif from HOMER homerResults."""
    motif_name:     str
    consensus:      str   = ""
    p_value:        float = 1.0
    log_p_value:    float = 0.0
    pct_target:     float = 0.0
    pct_background: float = 0.0
    best_match:     str   = ""     # best known motif match
    match_score:    float = 0.0


@dataclass
class MotifEnrichmentResult:
    """Output of run_homer_motif_enrichment() for one peak set."""
    peak_set:        str                            # "all_peaks", "da_up", "da_down"
    output_dir:      Path
    n_peaks:         int   = 0
    known_results:   list[KnownMotifHit]  = field(default_factory=list)
    denovo_results:  list[DeNovoMotifHit] = field(default_factory=list)
    known_txt:       Path | None = None
    known_html:      Path | None = None
    denovo_html:     Path | None = None
    homer_succeeded: bool = False


# ===========================================================================
# Helpers
# ===========================================================================

def _count_bed_peaks(bed: Path) -> int:
    """Count non-header, non-empty lines in a BED file."""
    count = 0
    with open(bed) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith(("track ", "browser ", "#")):
                count += 1
    return count


# ===========================================================================
# Tool checks
# ===========================================================================

def _check_tool(name: str) -> str | None:
    return shutil.which(name)


def check_homer() -> bool:
    """Verify HOMER findMotifsGenome.pl is available."""
    return _check_tool("findMotifsGenome.pl") is not None


def _find_configure_homer() -> str | None:
    """Find configureHomer.pl — check PATH first, then next to findMotifsGenome.pl."""
    # 1. Check PATH
    configure = _check_tool("configureHomer.pl")
    if configure:
        return configure

    # 2. Find relative to findMotifsGenome.pl (conda installs HOMER in share/homer/)
    homer_bin = _check_tool("findMotifsGenome.pl")
    if homer_bin:
        import os
        homer_real = Path(os.path.realpath(homer_bin))
        # findMotifsGenome.pl is usually in the same dir as configureHomer.pl
        candidate = homer_real.parent / "configureHomer.pl"
        if candidate.exists():
            return str(candidate)
        # Or in share/homer/ relative to the conda env
        for parent in homer_real.parents:
            share_homer = parent / "share" / "homer" / "configureHomer.pl"
            if share_homer.exists():
                return str(share_homer)

    return None


def install_homer_genome(genome: str) -> bool:
    """Install a HOMER genome via configureHomer.pl -install <genome>.

    Returns True if installation succeeded, False otherwise.
    """
    configure = _find_configure_homer()
    if not configure:
        logger.warning("configureHomer.pl not found — cannot auto-install genome")
        return False

    logger.info("  Installing HOMER genome '%s' (%s -install %s) ...",
                genome, configure, genome)
    try:
        proc = subprocess.run(
            ["perl", configure, "-install", genome],
            capture_output=True, text=True, timeout=1800,  # 30 min timeout
        )
        log_tool_output(["perl", configure, "-install", genome], proc)
        if proc.returncode != 0:
            logger.warning("  HOMER genome install failed (exit %d):\n%s",
                           proc.returncode, (proc.stderr or "")[:1000])
            return False

        # Log progress
        for line in (proc.stderr or "").splitlines():
            if any(kw in line.lower() for kw in ("download", "install", "done", "complete")):
                logger.info("  HOMER install: %s", line.strip())

        logger.info("  HOMER genome '%s' installed successfully", genome)
        return True

    except subprocess.TimeoutExpired:
        logger.warning("  HOMER genome install timed out after 30 minutes")
        return False


def _run_homer_cmd(
    strategy_label: str,
    cmd: list[str],
    output_dir: Path,
    peak_set: str,
    n_peaks: int,
) -> bool:
    """Run one HOMER findMotifsGenome.pl attempt.

    Returns True if HOMER succeeded and produced knownResults.txt,
    False otherwise.  Returns "genome_not_found" string if the genome
    is not installed (special case for auto-install logic).
    """
    # HOMER requires the output directory to NOT exist
    if output_dir.exists():
        shutil.rmtree(output_dir)

    logger.info("  [%s] Running HOMER findMotifsGenome.pl (%d peaks, %s) ...",
                peak_set, n_peaks, strategy_label)
    logger.info("  CMD: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=7200,
        )
    except subprocess.TimeoutExpired:
        logger.error("  HOMER timed out after 2 hours")
        return False

    log_tool_output(cmd, proc)
    stderr = proc.stderr or ""
    genome_not_found = "not found" in stderr and "Genome" in stderr

    if proc.returncode != 0 or genome_not_found:
        reason = f"exit {proc.returncode}"
        if genome_not_found:
            reason = "genome not found in HOMER config"
        logger.warning("  [%s] HOMER failed (%s, %s)",
                       peak_set, strategy_label, reason)
        return False

    # Verify HOMER actually ran (not just printed help and exited 0)
    known_results_file = output_dir / "knownResults.txt"
    if not known_results_file.exists():
        logger.warning("  [%s] HOMER exited 0 but produced no knownResults.txt "
                       "(%s) — trying next strategy",
                       peak_set, strategy_label)
        return False

    # Log HOMER summary lines from stderr
    for line in stderr.splitlines():
        if any(kw in line.lower() for kw in
               ("finding", "found", "complete", "total", "checking",
                "scanning", "optimizing")):
            logger.info("  HOMER: %s", line.strip())

    return True


def _try_homer_strategies(
    initial_strategies: list[tuple[str, list[str]]],
    installed_cmd: tuple[str, list[str]],
    fasta_cmd: tuple[str, list[str]] | None,
    genome: str,
    output_dir: Path,
    peak_set: str,
    n_peaks: int,
) -> bool:
    """Try HOMER strategies in order, with auto-install on failure.

    Order:
      A) Installed genome (fast, HOMER auto-detects motif set)
      B) If A fails with "genome not found" →
         auto-install via configureHomer.pl -install <genome>,
         then retry A
      C) -fasta fallback (no genome install needed)
    """
    # A) Try installed genome (instant fail if not installed)
    if _run_homer_cmd(*installed_cmd, output_dir, peak_set, n_peaks):
        return True

    # If a local genome FASTA is available, use it directly and SKIP the genome
    # auto-install — that install is a large download that hangs for the full
    # timeout on offline / blocked networks (and is unnecessary when we already
    # have the FASTA).
    if fasta_cmd:
        logger.info("  [%s] installed genome unavailable — using local FASTA "
                    "(skipping HOMER genome auto-install)", peak_set)
        return _run_homer_cmd(*fasta_cmd, output_dir, peak_set, n_peaks)

    # No FASTA available: last resort — attempt auto-install, then retry A.
    logger.info("  [%s] no genome FASTA — attempting HOMER genome auto-install '%s' ...",
                peak_set, genome)
    if install_homer_genome(genome):
        if _run_homer_cmd(*installed_cmd, output_dir, peak_set, n_peaks):
            return True

    return False


# ===========================================================================
# Core: run HOMER findMotifsGenome.pl
# ===========================================================================

def run_homer_motif_enrichment(
    peaks_bed: Path,
    genome: str,
    output_dir: Path,
    peak_set: str = "all_peaks",
    *,
    genome_fasta: Path | None = None,
    background_bed: Path | None = None,
    size: int | str = 200,
    mask: bool = True,
    denovo_length: str = "8,10,12",
    n_motifs: int = 25,
    n_processors: int = 8,
    preparsed_dir: Path | None = None,
) -> MotifEnrichmentResult:
    """Run HOMER findMotifsGenome.pl on a peak set.

    Background strategy (critical for correct biological interpretation):
      - all_peaks (consensus):  no -bg → default genomic background
        (GC-matched random regions).  Answers: "Which motifs are
        enriched in ChIP peaks vs the genome?"
      - da_up / da_down:  -bg consensus_peaks.bed -chopify
        Answers: "Which motifs are *specifically* enriched in peaks
        that gained/lost binding vs *all* ChIP peaks?"
        Without -bg, DA subsets would just rediscover generic
        bound-region motifs.

    HOMER auto-removes overlapping regions between target and -bg,
    and applies GC-content normalization + autonormalization to both
    default and custom backgrounds.

    Parameters
    ----------
    peaks_bed       : BED file of peak regions (foreground / target)
    genome          : genome name (e.g. "hg38", "mm10") — requires HOMER
                      genome install unless genome_fasta is provided
    output_dir      : HOMER output directory (must not exist or HOMER errors)
    peak_set        : label for this peak set ("all_peaks", "da_up", "da_down")
    genome_fasta    : genome FASTA file — if provided, passed to HOMER via
                      -fasta flag (no HOMER genome install required)
    background_bed  : custom background peak BED for -bg flag.
                      For DA subsets, pass the consensus peak BED so that
                      enrichment is relative to all ChIP peaks, not
                      random genome.  HOMER auto-removes overlaps with
                      target and applies GC normalization + autonormalization.
    size            : region size for motif finding (default 200 = ±100 bp
                      from peak center; use "given" for exact peak coords)
    mask            : mask repeats (recommended for mammalian genomes)
    denovo_length   : comma-separated motif lengths for de novo discovery
    n_motifs        : max number of de novo motifs to report
    n_processors    : threads for HOMER
    preparsed_dir   : shared preparsed directory (speeds up multiple runs
                      on same genome; only used with installed genome, not
                      with -fasta mode)
    """
    # Count peaks
    n_peaks = sum(1 for line in open(peaks_bed)
                  if line.strip() and not line.startswith("#")
                  and not line.startswith("track"))

    result = MotifEnrichmentResult(
        peak_set=peak_set,
        output_dir=output_dir,
        n_peaks=n_peaks,
    )

    if n_peaks < 10:
        logger.warning("  [%s] Only %d peaks — too few for motif enrichment, skipping",
                        peak_set, n_peaks)
        return result

    # Checkpoint: skip only if the .done marker exists.  The marker is
    # written after HOMER succeeds — a crash mid-run leaves a partial
    # knownResults.txt but no marker, so the next run redoes it.
    known_txt = output_dir / "knownResults.txt"
    done_marker = output_dir / ".homer.done"
    if done_marker.exists() and known_txt.exists():
        logger.info("  [%s] HOMER checkpoint: %s", peak_set, known_txt)
        result.known_results = parse_known_results(known_txt)
        result.denovo_results = parse_denovo_results(output_dir)
        result.known_txt = known_txt
        result.known_html = _if_exists(output_dir / "knownResults.html")
        result.denovo_html = _if_exists(output_dir / "homerResults.html")
        result.homer_succeeded = True
        return result

    # Build shared flags (appended to all attempts).
    # Only use flags documented by findMotifsGenome.pl — internal homer2
    # flags like -nlen are NOT valid here and cause silent failures.
    shared_flags: list[str] = [
        "-size", str(size),
        "-len", denovo_length,
        "-S", str(n_motifs),
        "-p", str(n_processors),
    ]
    if mask:
        shared_flags.append("-mask")

    # Custom background: for DA subsets, use consensus peaks as background
    # so enrichment is relative to all ChIP peaks, not random genome.
    # HOMER auto-removes overlapping regions between target and -bg,
    # and applies GC normalization + autonormalization to custom backgrounds.
    if background_bed and background_bed.exists():
        shared_flags += ["-bg", str(background_bed)]
        # -chopify: chop large background regions to match average target
        # size.  Important when consensus peaks vary in size vs DA subsets.
        shared_flags.append("-chopify")
        logger.info("  [%s] Using custom background: %s (-chopify enabled)",
                    peak_set, background_bed.name)

    # Build attempt strategies (tried in order until one succeeds):
    #   A) installed genome      (preferred — HOMER auto-detects motif set)
    #   B) auto-install genome   (configureHomer.pl -install <genome>, then retry A)
    #   C) -fasta genome.fa      (fallback — no HOMER genome install needed)

    installed_flags = list(shared_flags)
    if preparsed_dir:
        preparsed_dir.mkdir(parents=True, exist_ok=True)
        installed_flags += ["-preparsedDir", str(preparsed_dir)]

    installed_cmd = (
        f"installed genome '{genome}'",
        ["findMotifsGenome.pl", str(peaks_bed), genome, str(output_dir)]
        + installed_flags,
    )

    fasta_cmd = None
    if genome_fasta and genome_fasta.exists():
        # For -fasta mode: rebuild flags WITHOUT -mask (repeat masking
        # requires installed genome data; with -fasta, HOMER may silently
        # fail if -mask is passed but the FASTA has no lowercase repeats).
        # Also skip -preparsedDir (not used with -fasta).
        fasta_flags: list[str] = [
            "-size", str(size),
            "-len", denovo_length,
            "-S", str(n_motifs),
            "-p", str(n_processors),
        ]
        # Re-add background flags
        if background_bed and background_bed.exists():
            fasta_flags += ["-bg", str(background_bed), "-chopify"]
        # Auto-detect motif set from genome name
        mset = _detect_mset(genome)
        if mset:
            fasta_flags += ["-mset", mset]
        # HOMER preparses the custom FASTA; keep the preparsed/ dir under the
        # output tree (shared across subsets) instead of next to the FASTA.
        if preparsed_dir:
            preparsed_dir.mkdir(parents=True, exist_ok=True)
            fasta_flags += ["-preparsedDir", str(preparsed_dir)]
        # findMotifsGenome.pl has NO -fasta flag (it errors "-fasta not
        # recognized"). A custom genome is given by passing the FASTA path as
        # the POSITIONAL <genome> argument. -mask is dropped (raw FASTA has no
        # lowercase repeat masking).
        fasta_cmd = (
            f"FASTA genome {genome_fasta.name} (-mset {mset})",
            ["findMotifsGenome.pl", str(peaks_bed), str(genome_fasta), str(output_dir)]
            + fasta_flags,
        )

    # Strategy A → B (auto-install) → A retry → C (-fasta)
    strategies: list[tuple[str, list[str]]] = [installed_cmd]

    homer_success = False
    homer_success = _try_homer_strategies(
        strategies, installed_cmd, fasta_cmd, genome, output_dir,
        peak_set, n_peaks,
    )

    if not homer_success:
        logger.error(
            "  [%s] HOMER failed with all strategies (including auto-install).\n"
            "    Check network connectivity for genome download, or\n"
            "    manually install: configureHomer.pl -install %s",
            peak_set, genome,
        )
        return result

    # Parse results
    known_txt = output_dir / "knownResults.txt"
    if known_txt.exists():
        result.known_results = parse_known_results(known_txt)
        result.known_txt = known_txt
    result.known_html = _if_exists(output_dir / "knownResults.html")

    result.denovo_results = parse_denovo_results(output_dir)
    result.denovo_html = _if_exists(output_dir / "homerResults.html")
    result.homer_succeeded = True

    done_marker.write_text("")   # success sentinel — HOMER succeeded

    logger.info("  [%s] HOMER complete: %d known motifs, %d de novo motifs",
                peak_set, len(result.known_results), len(result.denovo_results))

    return result


# ===========================================================================
# Parsing HOMER output
# ===========================================================================

def parse_known_results(known_txt: Path) -> list[KnownMotifHit]:
    """Parse HOMER knownResults.txt into structured motif hits.

    File format (tab-separated):
      0: Motif Name
      1: Consensus
      2: P-value
      3: Log P-value
      4: q-value (Benjamini)
      5: # of Target Sequences with Motif
      6: % of Target Sequences with Motif
      7: # of Background Sequences with Motif
      8: % of Background Sequences with Motif
    """
    hits: list[KnownMotifHit] = []
    if not known_txt.exists():
        return hits

    with open(known_txt) as f:
        header = f.readline()  # skip header
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 9:
                continue
            try:
                hit = KnownMotifHit(
                    motif_name=parts[0],
                    consensus=parts[1],
                    p_value=_safe_float(parts[2]),
                    log_p_value=_safe_float(parts[3]),
                    q_value=_safe_float(parts[4]),
                    n_target=_safe_int(parts[5]),
                    pct_target=_safe_pct(parts[6]),
                    n_background=_safe_int(parts[7]),
                    pct_background=_safe_pct(parts[8]),
                )
                hits.append(hit)
            except (ValueError, IndexError):
                continue

    # Sort by p-value (most significant first)
    hits.sort(key=lambda h: h.log_p_value)
    return hits


def parse_denovo_results(homer_output_dir: Path) -> list[DeNovoMotifHit]:
    """Parse HOMER de novo motif results.

    De novo motifs are in homerResults/ directory.  The main summary
    is in homerResults.html, but we parse the individual motif files
    and the all.motifs file for structured data.
    """
    hits: list[DeNovoMotifHit] = []

    # Parse from homerMotifs.all.motifs (most reliable)
    all_motifs = homer_output_dir / "homerMotifs.all.motifs"
    if not all_motifs.exists():
        return hits

    with open(all_motifs) as f:
        for line in f:
            if not line.startswith(">"):
                continue
            # Format: >CONSENSUS\tMOTIF_NAME\tLOG_P\tSCORE,...
            parts = line[1:].strip().split("\t")
            if len(parts) < 2:
                continue

            consensus = parts[0]
            motif_name = parts[1] if len(parts) > 1 else consensus

            # Parse score/p-value from the motif header
            log_p = 0.0
            if len(parts) > 2:
                log_p = _safe_float(parts[2])

            # Try to extract best match from the name field
            # HOMER often includes "BestGuess:MOTIF/score" in the name
            best_match = ""
            match_score = 0.0
            for p in parts:
                if "BestGuess:" in p:
                    bm = p.split("BestGuess:")[-1].strip()
                    if "/" in bm:
                        parts_bm = bm.rsplit("/", 1)
                        best_match = parts_bm[0]
                        match_score = _safe_float(parts_bm[1])
                    else:
                        best_match = bm

            hits.append(DeNovoMotifHit(
                motif_name=motif_name,
                consensus=consensus,
                log_p_value=log_p,
                p_value=10 ** log_p if log_p < 0 else 1.0,
                best_match=best_match,
                match_score=match_score,
            ))

    # Also try to parse pct_target/pct_background from knownResults-style
    # output in homerResults/ directory
    homer_results_dir = homer_output_dir / "homerResults"
    if homer_results_dir.is_dir():
        # The HTML contains this info but is harder to parse.
        # The motif*.info.html files have it.
        pass

    hits.sort(key=lambda h: h.log_p_value)
    return hits


# ===========================================================================
# Run on multiple peak sets (consensus + DA subsets)
# ===========================================================================

def run_motif_enrichment_multi(
    consensus_bed: Path,
    genome: str,
    output_dir: Path,
    *,
    genome_fasta: Path | None = None,
    da_up_bed: Path | None = None,
    da_down_bed: Path | None = None,
    size: int | str = 200,
    mask: bool = True,
    n_processors: int = 8,
    preparsed_dir: Path | None = None,
) -> list[MotifEnrichmentResult]:
    """Run HOMER motif enrichment on consensus peaks and DA subsets.

    Parameters
    ----------
    consensus_bed  : full consensus peak BED from Step 3
    genome         : genome name for HOMER
    output_dir     : root output directory
    genome_fasta   : genome FASTA (optional, avoids HOMER genome install)
    da_up_bed      : DA up peaks BED from bulkchip-DA (optional)
    da_down_bed    : DA down peaks BED from bulkchip-DA (optional)
    size           : HOMER -size parameter
    mask           : HOMER -mask flag
    n_processors   : threads
    preparsed_dir  : shared preparsed directory
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Shared preparsed dir for genome parsing (saves time on repeated runs)
    if preparsed_dir is None:
        preparsed_dir = output_dir / "preparsed"

    results: list[MotifEnrichmentResult] = []

    # Define peak sets to run:
    #   (label, foreground BED, background BED or None)
    #
    # all_peaks: genomic background (no -bg) — "what motifs in ChIP peaks?"
    # da_up/down: consensus peaks as -bg     — "what motifs in *regulated* peaks
    #             vs all ChIP peaks?"         (HOMER auto-removes overlaps,
    #             applies GC norm + autonorm to custom bg)
    peak_sets: list[tuple[str, Path, Path | None]] = [
        ("all_peaks", consensus_bed, None),
    ]
    if da_up_bed and da_up_bed.exists():
        peak_sets.append(("da_up", da_up_bed, consensus_bed))
    if da_down_bed and da_down_bed.exists():
        peak_sets.append(("da_down", da_down_bed, consensus_bed))

    for peak_set, bed, bg_bed in peak_sets:
        homer_dir = output_dir / peak_set
        homer_dir.mkdir(parents=True, exist_ok=True)

        # Check if BED has actual peaks (not just header/empty)
        n_peaks = _count_bed_peaks(bed)
        if n_peaks == 0:
            logger.warning("  [%s] 0 peaks in %s — skipping HOMER, "
                           "creating empty output directory", peak_set, bed)
            (homer_dir / "NOTE_no_peaks.txt").write_text(
                f"No peaks found in {bed.name}.\n"
                f"HOMER was not run for '{peak_set}' because the BED file "
                f"is empty (0 DA peaks at the current thresholds).\n"
                f"Try relaxing --padj or --lfc in bulkchip-DA.\n"
            )
            results.append(MotifEnrichmentResult(
                peak_set=peak_set, n_peaks=0, homer_succeeded=False,
                output_dir=homer_dir,
            ))
            continue

        res = run_homer_motif_enrichment(
            bed, genome, homer_dir,
            peak_set=peak_set,
            genome_fasta=genome_fasta,
            background_bed=bg_bed,
            size=size,
            mask=mask,
            n_processors=n_processors,
            preparsed_dir=preparsed_dir,
        )
        results.append(res)

    return results


# ===========================================================================
# Summary table
# ===========================================================================

def write_motif_summary(
    enrichment_results: list[MotifEnrichmentResult],
    output_dir: Path,
    *,
    top_n: int = 30,
) -> Path:
    """Write a combined summary TSV of top motifs across peak sets.

    Columns: peak_set, rank, motif_name, consensus, log_p_value,
             q_value, pct_target, pct_background, enrichment_ratio, type
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "top_motif_summary.tsv"

    header = (
        "peak_set\trank\tmotif_name\tconsensus\tlog_p_value\t"
        "q_value\tpct_target\tpct_background\tenrichment_ratio\ttype\n"
    )

    rows: list[str] = []
    for res in enrichment_results:
        if not res.homer_succeeded:
            continue

        # Known motifs
        for i, hit in enumerate(res.known_results[:top_n]):
            enrichment = hit.pct_target / max(hit.pct_background, 0.01)
            rows.append(
                f"{res.peak_set}\t{i+1}\t{hit.motif_name}\t{hit.consensus}\t"
                f"{hit.log_p_value:.1f}\t{hit.q_value:.2e}\t"
                f"{hit.pct_target:.1f}\t{hit.pct_background:.1f}\t"
                f"{enrichment:.2f}\tknown\n"
            )

        # De novo motifs
        for i, hit in enumerate(res.denovo_results[:top_n]):
            rows.append(
                f"{res.peak_set}\t{i+1}\t{hit.motif_name}\t{hit.consensus}\t"
                f"{hit.log_p_value:.1f}\t\t"
                f"{hit.pct_target:.1f}\t{hit.pct_background:.1f}\t"
                f"\tdenovo\n"
            )

    with open(out_path, "w") as f:
        f.write(header)
        f.writelines(rows)

    logger.info("Motif summary: %s (%d entries)", out_path, len(rows))
    return out_path


# ===========================================================================
# Plots
# ===========================================================================

def _setup_plot_style() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 300, "savefig.dpi": 300,
        "font.size": 10, "axes.titlesize": 12,
    })


def _save_figure(fig, name: str, output_dir: Path) -> None:
    import matplotlib.pyplot as plt
    for ext in ("pdf", "png"):
        fig.savefig(output_dir / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


def plot_top_known_motifs(
    enrichment_result: MotifEnrichmentResult,
    output_dir: Path,
    *,
    top_n: int = 20,
) -> Path | None:
    """Horizontal bar chart of top known motifs by -log10(p-value).

    Bars colored by enrichment ratio (pct_target / pct_background).
    """
    if not enrichment_result.known_results:
        return None

    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        import numpy as np
    except ImportError:
        logger.warning("matplotlib not available — skipping known motif plot")
        return None

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    hits = enrichment_result.known_results[:top_n]
    # Reverse for bottom-to-top plotting (most significant at top)
    hits = hits[::-1]

    names = []
    for h in hits:
        # Shorten long HOMER motif names: "MOTIF_NAME(TF_FAMILY)/CELL/SOURCE"
        # → keep "MOTIF_NAME(TF_FAMILY)" part
        short = h.motif_name.split("/")[0] if "/" in h.motif_name else h.motif_name
        if len(short) > 40:
            short = short[:37] + "..."
        names.append(short)

    neg_log_p = [-h.log_p_value for h in hits]  # HOMER log_p is negative
    enrichment = [h.pct_target / max(h.pct_background, 0.01) for h in hits]

    # Color by enrichment ratio
    norm = mcolors.Normalize(vmin=min(enrichment), vmax=max(enrichment))
    cmap = plt.cm.RdYlBu_r
    colors = [cmap(norm(e)) for e in enrichment]

    fig, ax = plt.subplots(figsize=(8, max(4, 0.35 * len(hits))))
    bars = ax.barh(range(len(hits)), neg_log_p, color=colors, edgecolor="none",
                   height=0.7)
    ax.set_yticks(range(len(hits)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("-log10(p-value)")
    ax.set_title(f"Top Known Motifs — {enrichment_result.peak_set}\n"
                 f"({enrichment_result.n_peaks:,} peaks)")

    # Colorbar for enrichment ratio
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, pad=0.02)
    cbar.set_label("Enrichment ratio\n(% target / % background)", fontsize=8)

    plot_name = f"top_known_motifs_{enrichment_result.peak_set}"
    _save_figure(fig, plot_name, output_dir)
    logger.info("  Known motif plot: %s", output_dir / f"{plot_name}.pdf")
    return output_dir / f"{plot_name}.pdf"


def plot_top_denovo_motifs(
    enrichment_result: MotifEnrichmentResult,
    output_dir: Path,
    *,
    top_n: int = 15,
) -> Path | None:
    """Bar chart of top de novo motifs with consensus sequence and best match.

    Shows consensus sequence, -log10(p-value), and best known motif match.
    """
    if not enrichment_result.denovo_results:
        return None

    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("matplotlib not available — skipping de novo motif plot")
        return None

    _setup_plot_style()
    output_dir.mkdir(parents=True, exist_ok=True)

    hits = enrichment_result.denovo_results[:top_n]
    hits = hits[::-1]  # most significant at top

    labels = []
    for h in hits:
        label = h.consensus
        if h.best_match:
            match_short = h.best_match.split("/")[0] if "/" in h.best_match else h.best_match
            label = f"{h.consensus}  ({match_short})"
        if len(label) > 50:
            label = label[:47] + "..."
        labels.append(label)

    neg_log_p = [-h.log_p_value for h in hits]

    fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(hits))))
    ax.barh(range(len(hits)), neg_log_p, color="#4C72B0", edgecolor="none",
            height=0.65)
    ax.set_yticks(range(len(hits)))
    ax.set_yticklabels(labels, fontsize=8, family="monospace")
    ax.set_xlabel("-log10(p-value)")
    ax.set_title(f"De Novo Motifs — {enrichment_result.peak_set}\n"
                 f"({enrichment_result.n_peaks:,} peaks)")

    plot_name = f"top_denovo_motifs_{enrichment_result.peak_set}"
    _save_figure(fig, plot_name, output_dir)
    logger.info("  De novo motif plot: %s", output_dir / f"{plot_name}.pdf")
    return output_dir / f"{plot_name}.pdf"


# ===========================================================================
# Helpers
# ===========================================================================

def _safe_float(s: str) -> float:
    """Parse float, handling HOMER's scientific notation and 1e values."""
    s = s.strip()
    if not s or s == "NA":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _safe_int(s: str) -> int:
    """Parse int from HOMER output (may have decimal point)."""
    s = s.strip()
    if not s or s == "NA":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _safe_pct(s: str) -> float:
    """Parse percentage string like '45.23%' → 45.23."""
    s = s.strip().rstrip("%")
    return _safe_float(s)


def _if_exists(p: Path) -> Path | None:
    return p if p.exists() else None


# Genome name → HOMER motif set mapping.
# When using -fasta, HOMER may not auto-detect the organism,
# so we explicitly pass -mset to select the correct motif database.
_GENOME_TO_MSET: dict[str, str] = {
    "hg38": "vertebrates", "hg19": "vertebrates", "hg18": "vertebrates",
    "mm10": "vertebrates", "mm39": "vertebrates", "mm9": "vertebrates",
    "rn6": "vertebrates",  "rn7": "vertebrates",
    "danRer11": "vertebrates", "danRer10": "vertebrates",
    "galGal6": "vertebrates", "galGal5": "vertebrates",
    "xenTro10": "vertebrates",
    "dm6": "insects", "dm3": "insects",
    "ce11": "worms", "ce10": "worms",
    "sacCer3": "yeast", "sacCer2": "yeast",
    "TAIR10": "plants", "Athaliana": "plants",
}


def _detect_mset(genome: str) -> str:
    """Map genome name to HOMER motif set (-mset flag).

    Priority:
      1. Exact match in _GENOME_TO_MSET
      2. Prefix-based inference (hg* → vertebrates, dm* → insects, etc.)
      3. Fallback to "all" (scans all motif databases — slower but safe)
    """
    # 1. Exact match
    if genome in _GENOME_TO_MSET:
        return _GENOME_TO_MSET[genome]

    # 2. Prefix-based inference
    g = genome.lower()
    _PREFIX_MAP = {
        "hg": "vertebrates", "mm": "vertebrates", "rn": "vertebrates",
        "danrer": "vertebrates", "galgal": "vertebrates", "xentr": "vertebrates",
        "bostau": "vertebrates", "canfam": "vertebrates", "susscr": "vertebrates",
        "equcab": "vertebrates", "oararies": "vertebrates",
        "dm": "insects", "aedes": "insects", "anopheles": "insects",
        "ce": "worms", "caeel": "worms",
        "saccer": "yeast", "calbicans": "yeast",
        "tair": "plants", "oryza": "plants", "zea": "plants",
    }
    for prefix, mset in _PREFIX_MAP.items():
        if g.startswith(prefix):
            logger.info("  Inferred -mset %s from genome prefix '%s'", mset, genome)
            return mset

    # 3. Fallback: scan all databases
    logger.info("  Unknown genome '%s' — using -mset all (scans all motif databases)", genome)
    return "all"
