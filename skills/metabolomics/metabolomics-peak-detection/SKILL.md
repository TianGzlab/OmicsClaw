---
name: metabolomics-peak-detection
description: >-
  Peak picking, feature detection, alignment and grouping using XCMS, MZmine 3, or
  MS-DIAL.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [metabolomics, peak-detection, XCMS, MZmine, MS-DIAL]
metadata:
  omicsclaw:
    domain: metabolomics
    emoji: "⛰️"
    trigger_keywords: [peak detection, feature detection, XCMS, MZmine, MS-DIAL, peak
        picking]
    allowed_extra_flags: []
    legacy_aliases: [peak-detect]
    saves_h5ad: false
    script: peak_detect.py
    param_hints: {}
    requires_preprocessed: false
---

# ⛰️ Metabolomics Peak Detection

Peak picking, feature detection, chromatographic alignment and grouping. Supports XCMS, MZmine 3, and MS-DIAL outputs.

## CLI Reference

```bash
python omicsclaw.py run peak-detect --demo
python omicsclaw.py run peak-detect --input <data.csv> --output <dir>
```

## Citations

- [XCMS](https://doi.org/10.1021/ac051437y)
- [MZmine 3](https://doi.org/10.1038/s41587-023-01690-2)
- [MS-DIAL](https://doi.org/10.1038/nmeth.3393)
