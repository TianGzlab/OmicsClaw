# Methodology

Median and total scale each column to the median column median or sum. Quantile maps ranks to averaged sorted values. PQN uses a TIC-normalized reference to estimate quotients, then divides the original intensities. Log computes log2(x+1).

`normalize` preserves NaNs according to the method and performs no imputation. Zero divisors become NaN. The input index is retained in `tables/normalized.csv`.
