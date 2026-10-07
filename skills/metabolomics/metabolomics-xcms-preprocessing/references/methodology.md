# Synthetic peak table

The CLI uses numpy default_rng(42) to simulate m/z, retention times and five
sample intensity columns. Peak counts respond to ppm and peak-width settings.
No real XCMS algorithm or raw-data reader is implemented. Real inputs fail.
