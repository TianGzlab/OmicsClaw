"""Alignment log summaries with explicit evidence provenance."""
from pathlib import Path
import json
import re
import numpy as np
import pandas as pd
from skills.bulkrna._lib.results import attach_info, read_info

__all__ = ['read_log', 'summarize', 'run_info', 'mapping_figure', 'composition_figure', 'coverage_figure', 'demo_data', 'demo_coverage']


def read_log(path: str | Path) -> str:
    """Read log text; pass this function as reader= to read_input.

    :param path: STAR, HISAT2 or Salmon text/JSON log.
    :returns: File contents without interpreting its filename.
    :raises OSError: The file cannot be read.
    """
    return Path(path).read_text()


def summarize(data: str | pd.DataFrame, *, method: str = 'star') -> pd.DataFrame:
    """Parse alignment counts and return a new mapping summary.

    :param data: Log text or a one-row parsed table, including demo_data output.
    :param method: CLI default star; select hisat2 for paired-end summaries or salmon for meta_info JSON.
    :returns: Mapping counts/rates with quality heuristics in run_info; Salmon reports total mapped, not unique mapped.
    :raises ValueError: Required counts are missing, inconsistent or the method is unsupported.
    """
    if isinstance(data,pd.DataFrame):
        if len(data) != 1:
            raise ValueError('Expected one alignment summary row')
        summary = data.iloc[0].to_dict()
    elif method == 'star':
        values = {}
        for line in data.splitlines():
            if '|' in line:
                key,_,value = line.partition('|')
                values[key.strip()] = value.strip().rstrip('%')
        total = int(values.get('Number of input reads',0))
        unique = int(values.get('Uniquely mapped reads number',0))
        multi = int(values.get('Number of reads mapped to multiple loci',0))
        summary = _rates('STAR',total,unique,multi)
    elif method == 'hisat2':
        def count(pattern):
            match = re.search(pattern,data)
            return int(match.group(1)) if match else 0
        if 'aligned concordantly exactly 1 time' not in data:
            raise ValueError('Expected a paired-end HISAT2 reads summary')
        summary = _rates('HISAT2',count(r'(\d+) reads'),
                         count(r'(\d+) .* aligned concordantly exactly 1 time'),
                         count(r'(\d+) .* aligned concordantly >1 times'))
    elif method == 'salmon':
        meta = json.loads(data)
        total,mapped = int(meta.get('num_processed',0)),int(meta.get('num_mapped',0))
        summary = {'aligner':'Salmon','total_reads':total,'mapped':mapped,'unmapped':total-mapped,
                   'mapped_rate':round(mapped/max(total,1)*100,2),
                   'unmapped_rate':round((total-mapped)/max(total,1)*100,2)}
    else:
        raise ValueError('method must be star, hisat2 or salmon')
    total = summary.get('total_reads',0)
    if total <= 0 or summary.get('unmapped',-1) < 0 or summary['unmapped'] > total:
        raise ValueError('Alignment log must contain positive reads and consistent mapping counts')
    unmapped = summary['unmapped_rate']
    overall = 'EXCELLENT' if unmapped < 10 else 'GOOD' if unmapped < 20 else 'WARNING' if unmapped < 40 else 'FAIL'
    checks = {'unmapped':'PASS' if unmapped < 20 else 'WARN' if unmapped < 40 else 'FAIL'}
    if 'unique_rate' in summary:
        checks = {'unique_mapping':'PASS' if summary['unique_rate'] > 70 else 'WARN',
                  'multi_mapping':'PASS' if summary['multi_rate'] < 15 else 'WARN',**checks}
    return attach_info(pd.DataFrame([summary]),{'quality':{'overall':overall,'checks':checks},
                       'gene_body_coverage_available':False,'strandedness_inferred':False,
                       'mapping_scope':'concordant pairs; unmapped also includes discordant/unpaired mapping'
                       if summary['aligner'] == 'HISAT2' else 'reported alignment counts'})


def _rates(aligner,total,unique,multi):
    if unique < 0 or multi < 0:
        raise ValueError('Mapped reads cannot be negative')
    return {'aligner':aligner,'total_reads':total,'uniquely_mapped':unique,'multi_mapped':multi,
            'unmapped':total-unique-multi,'unique_rate':round(unique/max(total,1)*100,2),
            'multi_rate':round(multi/max(total,1)*100,2),
            'unmapped_rate':round((total-unique-multi)/max(total,1)*100,2)}


def run_info(result: pd.DataFrame, *, keep: bool = True) -> dict:
    """Read mapping assessment and unavailable-evidence diagnostics.

    :param result: Output of summarize.
    :param keep: True preserves attrs; False removes diagnostics before serialization.
    :returns: A separate quality/provenance dictionary.
    :raises TypeError: The result is not a DataFrame.
    """
    return read_info(result,keep=keep)


def _parts(result):
    row = result.iloc[0]
    if 'mapped' in row:
        return ['Mapped','Unmapped'],[row['mapped'],row['unmapped']]
    return ['Unique','Multi','Unmapped'],[row['uniquely_mapped'],row['multi_mapped'],row['unmapped']]


def mapping_figure(result: pd.DataFrame):
    """Plot observed mapping counts as percentages.

    :param result: Output of summarize.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: Mapping counts are absent.
    """
    from matplotlib.figure import Figure
    names,counts = _parts(result)
    fig = Figure(figsize=(6,4)); ax = fig.subplots()
    ax.bar(names,np.asarray(counts)/result.iloc[0]['total_reads']*100)
    ax.set(ylabel='Reads (%)')
    return fig


def composition_figure(result: pd.DataFrame):
    """Plot observed mapping composition.

    :param result: Output of summarize.
    :returns: A matplotlib Figure without writing files.
    :raises KeyError: Mapping counts are absent.
    """
    from matplotlib.figure import Figure
    names,counts = _parts(result)
    fig = Figure(figsize=(6,6)); ax = fig.subplots()
    ax.pie(counts,labels=names)
    return fig


def coverage_figure(coverage: pd.DataFrame):
    """Plot an explicitly supplied gene-body coverage profile.

    :param coverage: position and coverage columns; alignment logs cannot supply these observations.
    :returns: A matplotlib Figure without synthesizing missing measurements.
    :raises KeyError: Coverage columns are absent.
    """
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7,4)); ax = fig.subplots()
    ax.plot(coverage['position'],coverage['coverage'])
    ax.set(xlabel='Gene-body percentile',ylabel='Normalized coverage')
    return fig


def demo_data(*, random_state: int = 42) -> pd.DataFrame:
    """Generate the synthetic STAR summary used by the CLI demo.

    :param random_state: CLI seed 42; change for another simulation.
    :returns: One simulated alignment summary row.
    :raises ValueError: The seed is invalid.
    """
    rng = np.random.RandomState(random_state)
    total = 30000000
    ur,mr = rng.uniform(82,92),rng.uniform(3,8)
    summary = _rates('STAR (demo)',total,int(total*ur/100),int(total*mr/100))
    summary.update(unique_rate=round(ur,2),multi_rate=round(mr,2),unmapped_rate=round(100-ur-mr,2),
                   mean_mapped_length=148.5,mismatch_rate=.32,deletion_rate=.01,insertion_rate=.01,
                   splices_total=int(total*.25),library_type='fr-firststrand')
    return pd.DataFrame([summary])


def demo_coverage(*, random_state: int = 42) -> pd.DataFrame:
    """Generate an illustrative coverage profile, not inferred from an alignment log.

    :param random_state: CLI demo seed 42; change for another simulation.
    :returns: One hundred simulated percentile/coverage rows.
    :raises ValueError: The seed is invalid.
    """
    rng = np.random.RandomState(random_state)
    x = np.linspace(0,1,100)
    y = (.7+.3*x+rng.normal(0,.03,100)).clip(.2,1.3)
    return pd.DataFrame({'position':x*100,'coverage':y/y.max()})
