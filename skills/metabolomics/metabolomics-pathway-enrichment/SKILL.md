---
name: metabolomics-pathway-enrichment
description: >-
  Metabolomics pathway analysis using MetaboAnalystR (KEGG, Reactome),
  pathview visualization, MSEA, mummichog, and network-based topology analysis.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [metabolomics, pathway, KEGG, enrichment, MetaboAnalyst, pathview]
metadata:
  omicsclaw:
    domain: metabolomics
    emoji: "🗺️"
    trigger_keywords: [metabolomics pathway, KEGG, MetaboAnalyst, enrichment, mummichog]
    allowed_extra_flags:
    - "--method"
    legacy_aliases: [met-pathway]
    saves_h5ad: false
    script: met_pathway.py
    param_hints: {}
    requires_preprocessed: false
---

# 🗺️ Metabolomics Pathway Analysis

Map metabolites to biological pathways and perform enrichment, topology, and network analysis.

## Core Capabilities

1. **KEGG pathway enrichment**: Over-representation analysis (ORA) using MetaboAnalystR
2. **Quantitative enrichment analysis (QEA)**: For continuous data (fold changes)
3. **Topology-based analysis**: Considers pathway structure (betweenness, degree)
4. **pathview visualization**: KEGG pathway maps with metabolite data overlay
5. **Network-based analysis**: Metabolite-pathway bipartite networks
6. **MSEA**: Metabolite Set Enrichment using SMPDB or HMDB sets

## CLI Reference

```bash
python omicsclaw.py run met-pathway --demo
python omicsclaw.py run met-pathway --input <metabolites.csv> --output <dir>
```

## Algorithm / Methodology

### KEGG Pathway Enrichment (MetaboAnalystR)

```r
library(MetaboAnalystR)

mSet <- InitDataObjects('conc', 'pathora', FALSE)
mSet <- SetOrganism(mSet, 'hsa')  # Human

# Load metabolite list (HMDB IDs or compound names)
metabolites <- c('HMDB0000001', 'HMDB0000005', 'HMDB0000010')

mSet <- Setup.MapData(mSet, metabolites)
mSet <- CrossReferencing(mSet, 'hmdb')  # Or 'name', 'kegg', 'pubchem'

# Pathway analysis
mSet <- SetKEGG.PathLib(mSet, 'hsa', 'current')
mSet <- SetMetabolomeFilter(mSet, FALSE)
mSet <- CalculateOraScore(mSet, 'rbc', 'hyperg')

pathway_results <- mSet$analSet$ora.mat
```

### Quantitative Enrichment Analysis (QEA)

```r
mSet <- InitDataObjects('conc', 'pathqea', FALSE)
mSet <- SetOrganism(mSet, 'hsa')

metabolite_data <- data.frame(
    compound = c('Glucose', 'Lactate', 'Pyruvate'),
    fc = c(1.5, 2.3, 0.7)
)

mSet <- Setup.MapData(mSet, metabolite_data)
mSet <- CrossReferencing(mSet, 'name')
mSet <- SetKEGG.PathLib(mSet, 'hsa', 'current')
mSet <- CalculateQeaScore(mSet, 'rbc', 'gt')

qea_results <- mSet$analSet$qea.mat
```

### Topology-Based Analysis

```r
mSet <- InitDataObjects('conc', 'pathinteg', FALSE)
mSet <- SetOrganism(mSet, 'hsa')
mSet <- Setup.MapData(mSet, metabolites)
mSet <- CrossReferencing(mSet, 'hmdb')
mSet <- SetKEGG.PathLib(mSet, 'hsa', 'current')
mSet <- SetMetabolomeFilter(mSet, FALSE)
mSet <- CalculateHyperScore(mSet)  # Combined ORA + topology

topo_results <- mSet$analSet$topo.mat
```

### Pathview Visualization

```r
library(pathview)

metabolite_data <- c('C00031' = 1.5, 'C00186' = 2.3, 'C00022' = 0.7)

pathview(cpd.data = metabolite_data,
         pathway.id = '00010',  # Glycolysis
         species = 'hsa',
         cpd.idtype = 'kegg',
         out.suffix = 'glycolysis_mapped')
# Output: hsa00010.glycolysis_mapped.png
```

### KEGG Mapper (Direct API)

```r
library(KEGGREST)

pathway_info <- keggGet('hsa00010')  # Glycolysis

kegg_ids <- c('C00031', 'C00186', 'C00022')

find_pathways <- function(kegg_id) {
    pathways <- keggLink('pathway', kegg_id)
    return(pathways)
}

all_pathways <- lapply(kegg_ids, find_pathways)
```

### Network-Based Analysis

```r
library(igraph)

build_network <- function(pathway_results) {
    edges <- data.frame()
    for (i in 1:nrow(pathway_results)) {
        pathway <- rownames(pathway_results)[i]
        metabolites <- strsplit(pathway_results$Metabolites[i], '; ')[[1]]
        for (met in metabolites) {
            edges <- rbind(edges, data.frame(from = met, to = pathway))
        }
    }
    g <- graph_from_data_frame(edges, directed = FALSE)
    V(g)$type <- ifelse(V(g)$name %in% edges$from, 'metabolite', 'pathway')
    return(g)
}

network <- build_network(pathway_results)
plot(network, vertex.size = ifelse(V(network)$type == 'pathway', 15, 5))
```

### Metabolite Set Enrichment (MSEA)

```r
mSet <- InitDataObjects('conc', 'msetora', FALSE)
mSet <- SetMetaboliteFilter(mSet, FALSE)
mSet <- SetCurrentMsetLib(mSet, 'smpdb_pathway', 2)
mSet <- Setup.MapData(mSet, metabolites)
mSet <- CrossReferencing(mSet, 'hmdb')
mSet <- CalculateHyperScore(mSet)
msea_results <- mSet$analSet$ora.mat
```

### Export Results

```r
export_pathways <- function(results, output_file) {
    results_df <- as.data.frame(results)
    results_df$pathway <- rownames(results)
    results_df <- results_df[, c('pathway', 'Total', 'Expected', 'Hits',
                                   'Raw p', 'Holm adjust', 'FDR', 'Impact')]
    results_df <- results_df[order(results_df$FDR), ]
    write.csv(results_df, output_file, row.names = FALSE)
    return(results_df)
}
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `ora` | ora, qea, topology, msea, mummichog |
| `--species` | `hsa` | KEGG organism code |
| `--id-type` | `hmdb` | hmdb, kegg, name, pubchem |
| `--fdr-cutoff` | `0.05` | FDR threshold |

## Why This Exists

- **Without it**: Finding 50 significant metabolites offers loose biological intuition but lacks systemic proof
- **With it**: Validates functional perturbations by mapping features onto definitive KEGG/Reactome architectures
- **Why OmicsClaw**: Runs fast local enrichment caches utilizing rigorous topology metrics (Degree/Betweenness)

## Workflow

1. **Calculate**: Map chemical IDs (HMDB/PubChem) to target Database indices.
2. **Execute**: Hypergeometric tests and pathway impact score calculations.
3. **Assess**: Perform FDR multiple testing adjustments.
4. **Generate**: Output structural network graphs.
5. **Report**: Tabulate key functionally enriched terms.

## Example Queries

- "Perform KEGG pathway analysis on these significant metabolites"
- "Run mummichog enrichment directly on m/z features"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── pathways.csv
├── figures/
│   ├── pathway_overview.png
│   ├── pathway_map.png
│   └── metabolite_network.png
├── tables/
│   ├── pathway_enrichment.csv
│   └── topology_scores.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Safety

- **Local-first**: Local database matching where possible; transparent interactions for external APIs (like KEGG).
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `met-diff` — Upstream source of significant feature hits

## Version Compatibility

Reference examples tested with: MetaboAnalystR 4.0+, ReactomePA 1.46+

## Dependencies

**Required**: numpy, pandas
**Optional**: MetaboAnalystR (R), pathview (R), KEGGREST (R), igraph (R), ReactomePA (R)

## Citations

- [MetaboAnalyst](https://doi.org/10.1093/nar/gkab382) — Pang et al., Nucleic Acids Research 2021
- [pathview](https://doi.org/10.1093/bioinformatics/btt285) — Luo & Brouwer, Bioinformatics 2013
- [mummichog](https://doi.org/10.1371/journal.pcbi.1003123) — Li et al., PLoS Computational Biology 2013
- [FELLA](https://doi.org/10.1371/journal.pcbi.1006726) — Picart-Armada et al., PLoS Computational Biology 2018

## Related Skills

- `met-annotate` — Identify metabolites first
- `met-diff` — Get significant metabolites for enrichment
- `xcms-preprocess` — Feature extraction upstream
