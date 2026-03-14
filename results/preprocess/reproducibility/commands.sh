#!/bin/bash
python spatial_preprocess.py --input <input.h5ad> --output /data1/TianLab/zhouwg/project/OmicsClaw/results/preprocess --data-type generic --species human --min-genes 200 --min-cells 3 --max-mt-pct 20.0 --n-top-hvg 2000 --n-pcs 50 --n-neighbors 15 --leiden-resolution 1.0
