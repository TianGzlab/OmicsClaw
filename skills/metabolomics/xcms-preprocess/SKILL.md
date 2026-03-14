---
name: xcms-preprocess
description: >-
  XCMS3 workflow for LC-MS/GC-MS metabolomics preprocessing. Peak detection
  (CentWave/MatchedFilter), RT alignment (Obiwarp), correspondence, gap filling,
  and CAMERA adduct/isotope annotation.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [metabolomics, xcms, preprocessing, LC-MS, peak-detection, alignment]
metadata:
  omicsclaw:
    domain: metabolomics
    emoji: "🧪"
    trigger_keywords: [xcms, metabolomics preprocessing, LC-MS, peak detection, RT alignment]
---

# 🧪 XCMS Metabolomics Preprocessing

XCMS3 workflow for untargeted LC-MS/GC-MS metabolomics. Requires Bioconductor 3.18+ with xcms 4.0+ and MSnbase 2.28+.

## Core Capabilities

1. **Peak detection**: CentWave (centroided) or MatchedFilter (profile data)
2. **RT alignment**: Obiwarp dynamic time warping for retention time correction
3. **Peak correspondence**: Density-based grouping across samples
4. **Gap filling**: Recover missing values by region integration
5. **CAMERA annotation**: Isotope pattern and adduct group identification

## CLI Reference

```bash
python omicsclaw.py run xcms-preprocess --demo
python omicsclaw.py run xcms-preprocess --input <raw_data/> --output <dir>
```

## Algorithm / Methodology

### Load Raw Data

```r
library(xcms)
library(MSnbase)

raw_files <- list.files('raw_data', pattern = '\\.(mzML|mzXML)$', full.names = TRUE)
raw_data <- readMSData(raw_files, mode = 'onDisk')
```

### Define Sample Groups

```r
sample_info <- data.frame(
    sample_name = basename(raw_files),
    sample_group = c(rep('Control', 5), rep('Treatment', 5), rep('QC', 3)),
    injection_order = 1:length(raw_files)
)
pData(raw_data) <- sample_info
```

### Peak Detection (CentWave — Centroided Data)

```r
cwp <- CentWaveParam(
    peakwidth = c(5, 30),       # Peak width range in seconds
    ppm = 15,                    # m/z tolerance
    snthresh = 10,               # Signal-to-noise threshold
    prefilter = c(3, 1000),      # Min peaks and intensity
    mzdiff = 0.01,               # Minimum m/z difference
    noise = 1000,                # Noise level
    integrate = 1                # Integration method
)

xdata <- findChromPeaks(raw_data, param = cwp)
cat('Peaks found:', nrow(chromPeaks(xdata)), '\n')
```

### Peak Detection (MatchedFilter — Profile Data)

```r
mfp <- MatchedFilterParam(
    binSize = 0.1, fwhm = 30, snthresh = 10, step = 0.1, mzdiff = 0.8
)
xdata_profile <- findChromPeaks(raw_data, param = mfp)
```

### Retention Time Alignment (Obiwarp)

```r
obp <- ObiwarpParam(
    binSize = 0.5, response = 1, distFun = 'cor_opt',
    gapInit = 0.3, gapExtend = 2.4
)
xdata <- adjustRtime(xdata, param = obp)
plotAdjustedRtime(xdata)
```

### Peak Correspondence (Grouping)

```r
pdp <- PeakDensityParam(
    sampleGroups = pData(xdata)$sample_group,
    bw = 5,                      # RT bandwidth
    minFraction = 0.5,           # Min fraction of samples
    minSamples = 1,              # Min samples per group
    binSize = 0.025              # m/z bin size
)
xdata <- groupChromPeaks(xdata, param = pdp)
cat('Features:', nrow(featureDefinitions(xdata)), '\n')
```

### Gap Filling

```r
fpp <- ChromPeakAreaParam()
xdata <- fillChromPeaks(xdata, param = fpp)
```

### Extract Feature Table

```r
feature_values <- featureValues(xdata, method = 'maxint', value = 'into')
feature_defs <- as.data.frame(featureDefinitions(xdata))
feature_defs$feature_id <- rownames(feature_defs)

feature_table <- cbind(feature_defs[, c('feature_id', 'mzmed', 'rtmed')], feature_values)
write.csv(feature_table, 'feature_table.csv', row.names = FALSE)
```

### CAMERA Annotation (Isotopes/Adducts)

```r
library(CAMERA)

xsa <- xsAnnotate(as(xdata, 'xcmsSet'))
xsa <- groupFWHM(xsa, perfwhm = 0.6)
xsa <- findIsotopes(xsa, mzabs = 0.01, ppm = 10)
xsa <- findAdducts(xsa, polarity = 'positive')
camera_results <- getPeaklist(xsa)
```

### Quality Control

```r
# TIC for each sample
tic <- chromatogram(raw_data, aggregationFun = 'sum')
plot(tic)

# Peak count per sample
peak_counts <- table(chromPeaks(xdata)[, 'sample'])
barplot(peak_counts, main = 'Peaks per sample')

# PCA of features
library(pcaMethods)
log_values <- log2(feature_values + 1)
log_values[is.na(log_values)] <- 0
pca <- pca(t(log_values), nPcs = 3, method = 'ppca')
plotPcs(pca, col = as.factor(pData(xdata)$sample_group))
```

### Export for MetaboAnalyst

```r
export_data <- t(feature_values)
colnames(export_data) <- paste0('M', round(feature_defs$mzmed, 4), 'T', round(feature_defs$rtmed, 1))
export_df <- data.frame(Sample = rownames(export_data), Group = pData(xdata)$sample_group, export_data)
write.csv(export_df, 'metaboanalyst_input.csv', row.names = FALSE)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--peak-method` | `centwave` | centwave or matchedfilter |
| `--ppm` | `15` | m/z tolerance (ppm) |
| `--peakwidth` | `5,30` | Peak width range (seconds) |
| `--sn-thresh` | `10` | Signal-to-noise threshold |
| `--align-method` | `obiwarp` | RT alignment method |

## Why This Exists

- **Without it**: Raw mzML/mzXML profiles are just unaligned 3D data clouds of m/z, intensity, and time
- **With it**: Sophisticated algorithms detect true chemical peaks, correct temporal drift (Obiwarp), and map features across runs
- **Why OmicsClaw**: Avoids verbose R scripts with a hyper-optimized parameter wrapper for XCMS3

## Workflow

1. **Calculate**: Fit moving mathematical wavelets to detect peaks (CentWave).
2. **Execute**: Align retention times dynamically across all mass spec runs.
3. **Assess**: Group congruent features and integrate signal caps for missing zones.
4. **Generate**: Output structural correspondence matrices (feature tables).
5. **Report**: Synthesize Total Ion Chromatogram (TIC) and aligned retention deviation plots.

## Example Queries

- "Preprocess these mzML files using XCMS"
- "Detect peaks and align retention times"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── feature_table.csv
├── figures/
│   ├── tic_overlay.png
│   └── retention_deviation.png
├── tables/
│   └── grouped_features.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `met-normalize` — Downstream data scaling
- `met-annotate` — Downstream explicit matching to spectra

## Version Compatibility

Reference examples tested with: xcms 4.0+, MSnbase 2.28+

## Dependencies

**Required**: xcms, MSnbase (R/Bioconductor)
**Optional**: CAMERA, pcaMethods

## Citations

- [XCMS](https://doi.org/10.1021/ac051437y) — Smith et al., Analytical Chemistry 2006
- [CentWave](https://doi.org/10.1186/1471-2105-9-504) — Tautenhahn et al., BMC Bioinformatics 2008
- [CAMERA](https://doi.org/10.1021/ac202450g) — Kuhl et al., Analytical Chemistry 2012

## Related Skills

- `met-annotate` — Identify metabolites
- `met-normalize` — Normalize feature table
- `met-diff` — Differential analysis
