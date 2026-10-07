"""FASTQ readers and in-memory quality metrics."""
from pathlib import Path
import gzip
import numpy as np
import pandas as pd
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['read_fastq', 'quality_control', 'run_info', 'quality_figure', 'gc_figure', 'demo_data']
_ADAPTERS = {'Illumina_TruSeq':'AGATCGGAAGAGC', 'Nextera':'CTGTCTCTTATACACATCT', 'Small_RNA':'TGGAATTCTCGG'}


def read_fastq(path: str | Path, *, max_reads: int = 100000) -> pd.DataFrame:
    """Read FASTQ records; pass this function as reader= to read_input.

    :param path: FASTQ path; a .gz suffix selects gzip decompression.
    :param max_reads: CLI limit 100000; increase for a larger leading-read sample.
    :returns: Sequence and Phred+33 quality strings as rows.
    :raises ValueError: Records are truncated, malformed, or have unequal sequence/quality lengths.
    """
    if max_reads <= 0:
        raise ValueError('max_reads must be positive')
    rows = []
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        for _ in range(max_reads):
            header = stream.readline()
            if not header:
                break
            sequence, plus, quality = stream.readline().strip(), stream.readline().strip(), stream.readline().strip()
            if not header.startswith('@') or not plus.startswith('+') or not sequence or not quality:
                raise ValueError('Malformed or truncated FASTQ record')
            if len(sequence) != len(quality):
                raise ValueError('FASTQ sequence and quality length differ')
            rows.append((sequence, quality))
    if not rows:
        raise ValueError('FASTQ contains no reads')
    return pd.DataFrame(rows, columns=['sequence','quality'])


def quality_control(reads: pd.DataFrame, *, max_reads: int = 100000) -> pd.DataFrame:
    """Compute a new one-row quality summary for Phred+33 reads.

    :param reads: sequence and quality string columns; input rows are not changed.
    :param max_reads: CLI default 100000 leading records; increase to inspect more reads.
    :returns: Scalar QC metrics and adapter counts; run_info retains per-base distributions.
    :raises ValueError: Reads, lengths or Phred+33 scores are invalid.
    """
    if max_reads <= 0 or not {'sequence','quality'} <= set(reads.columns) or reads.empty:
        raise ValueError('Nonempty sequence and quality columns and a positive max_reads are required')
    per_position, gc, lengths, n_counts, all_quals = [], [], [], [], []
    hits = dict.fromkeys(_ADAPTERS,0)
    for seq, qual in reads[['sequence','quality']].head(max_reads).itertuples(index=False,name=None):
        if not isinstance(seq,str) or not isinstance(qual,str) or not seq or len(seq) != len(qual):
            raise ValueError('Read sequence and quality length differ or are empty')
        seq = seq.upper()
        scores = [ord(c)-33 for c in qual]
        if min(scores) < 0 or max(scores) > 93:
            raise ValueError('Quality scores must use printable Phred+33 characters')
        lengths.append(len(seq))
        gc.append((seq.count('G')+seq.count('C'))/len(seq))
        n_counts.append(seq.count('N'))
        all_quals.extend(scores)
        while len(per_position) < len(seq):
            per_position.append([])
        for pos,score in enumerate(scores):
            per_position[pos].append(score)
        for name,adapter in _ADAPTERS.items():
            hits[name] += int(adapter[:12] in seq)
    quality = np.asarray(all_quals)
    n_reads = len(lengths)
    summary = {'n_reads':n_reads,'mean_read_length':float(np.mean(lengths)),
               'mean_quality':round(float(quality.mean()),2),
               'q20_rate':round(float(np.mean(quality>=20))*100,2),
               'q30_rate':round(float(np.mean(quality>=30))*100,2),
               'mean_gc':round(float(np.mean(gc))*100,2),
               'mean_n_content':round(float(np.mean(n_counts))/max(np.mean(lengths),1)*100,4),
               'adapter_hits':hits,'adapter_rate':round(sum(hits.values())/n_reads*100,2)}
    per_base = [{'position':i+1,'mean':float(np.mean(q)),'median':float(np.median(q)),
                 'q25':float(np.percentile(q,25)),'q75':float(np.percentile(q,75))}
                for i,q in enumerate(per_position)]
    return attach_info(pd.DataFrame([summary]), {'metrics':{**summary,'per_base':per_base,
                       'gc_fracs':gc,'read_lengths':lengths,'all_quals':all_quals},
                       'sampling':'leading reads','phred_offset':33})


def run_info(result: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read full quality distributions and sampling diagnostics.

    :param result: Output of quality_control.
    :param keep: True preserves attrs; False removes diagnostics before serialization.
    :returns: A separate dictionary containing metrics and sampling provenance.
    :raises TypeError: The result is not a DataFrame.
    """
    return read_info(result, keep=keep)


def quality_figure(result: pd.DataFrame):
    """Plot mean and interquartile quality by read position.

    :param result: QC result retaining its diagnostic attrs.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: Per-base diagnostics are absent.
    """
    from matplotlib.figure import Figure
    table = pd.DataFrame(read_info(result)['metrics']['per_base'])
    fig = Figure(figsize=(8,4)); ax = fig.subplots()
    ax.plot(table['position'],table['mean'])
    ax.fill_between(table['position'],table['q25'],table['q75'],alpha=.3)
    ax.set(xlabel='Read position',ylabel='Phred quality')
    return fig


def gc_figure(result: pd.DataFrame):
    """Plot GC fractions across sampled reads.

    :param result: QC result retaining its diagnostic attrs.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: GC diagnostics are absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6,4)); ax = fig.subplots()
    ax.hist(read_info(result)['metrics']['gc_fracs'],bins=50)
    ax.set(xlabel='GC fraction',ylabel='Reads')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate valid synthetic FASTQ records in memory.

    :param random_state: CLI seed 42; change for another simulation without altering global RNG state.
    :returns: Five thousand 150-base reads with quality strings of the same length.
    :raises ValueError: The seed is invalid.
    """
    rng = np.random.RandomState(random_state)
    records = []
    for _ in range(5000):
        seq = ''.join(rng.choice(list('ACGT'),150,p=[.28,.22,.22,.28]))
        if rng.random() < .05:
            adapter = _ADAPTERS['Illumina_TruSeq']
            seq = seq[:150-len(adapter)] + adapter
        quals = rng.normal(33,5,150).clip(20,42).astype(int)
        quals[:5] -= rng.randint(3,8,5)
        quals[-10:] -= rng.randint(5,12,10)
        records.append((seq,''.join(chr(q+33) for q in quals.clip(2,42))))
    return pd.DataFrame(records,columns=['sequence','quality'])
