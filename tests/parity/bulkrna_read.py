"""Legacy recordings and public API comparisons for read QC and trajectory placement."""


def register(Case, Skill):
    changed = {f'{file}:{key}':'Repair synthetic FASTQ adapter reads: sequence and quality must both have 150 bases.'
               for file in ('summary.json','tables/qc_summary.csv') for key in ('mean_read_length',)}
    return {
        'bulkrna-read-qc':Skill('skills/bulkrna/bulkrna-read-qc/bulkrna_read_qc.py',
                              'tests.parity.bulkrna_read:api_read_qc',{'default':Case(('--demo',),exclude=changed)}),
        'bulkrna-read-alignment':Skill('skills/bulkrna/bulkrna-read-alignment/bulkrna_read_alignment.py',
                              'tests.parity.bulkrna_read:api_alignment',{'default':Case(('--demo',))}),
        'bulkrna-trajblend':Skill('skills/bulkrna/bulkrna-trajblend/bulkrna_trajblend.py',
                              'tests.parity.bulkrna_read:api_trajblend',{'default':Case(('--demo',),exclude={
                                  key:'PCA now uses explicit random_state=42 instead of the global RNG state left after demo generation; fractions and PC1/PC2 remain strictly compared.'
                                  for key in ('tables/pseudotime_estimates.csv:pseudotime',
                                              'tables/pseudotime_estimates.csv:pseudotime_std',
                                              'tables/pseudotime_estimates.csv:mean_neighbor_dist',
                                              'summary.json:pseudotime_summary.mean')})}),
    }


def api_read_qc(case):
    from skills._sdk.notebook import load_skill
    lib = load_skill('bulkrna-read-qc')
    result = lib.quality_control(lib.demo_data())
    return {'tables':{'qc_summary.csv':result},'summary':result.iloc[0].to_dict()}


def api_alignment(case):
    from skills._sdk.notebook import load_skill
    lib = load_skill('bulkrna-read-alignment')
    result = lib.summarize(lib.demo_data())
    return {'tables':{'alignment_stats.csv':result},
            'summary':{**result.iloc[0].to_dict(),'quality':lib.run_info(result)['quality']}}


def api_trajblend(case):
    from skills._sdk.notebook import load_skill
    lib = load_skill('bulkrna-trajblend')
    bulk,ref,labels,time = lib.demo_data()
    result = lib.map_trajectory(bulk,reference=ref,labels=labels,pseudotime=time)
    fractions = lib.fractions(result)
    # CLI CSVs retain their sample index, whose absent name reads as Unnamed: 0.
    fraction_table = fractions.reset_index().rename(columns={'index':'Unnamed: 0'})
    return {'tables':{'cell_fractions.csv':fraction_table,'pseudotime_estimates.csv':result.reset_index()},
            'summary':{'n_samples':len(fractions),'n_cell_types':len(fractions.columns),
                       'cell_types':list(fractions.columns),'pseudotime_summary':{
                       'min':float(result['pseudotime'].min()),'max':float(result['pseudotime'].max()),
                       'mean':float(result['pseudotime'].mean())}}}
