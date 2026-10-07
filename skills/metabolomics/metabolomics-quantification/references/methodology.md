# Methodology

Min imputation uses half the global positive minimum, median uses each column positive median, and KNN uses neighbouring feature rows with up to five neighbours. TIC scales column sums to their median; median scales column medians; log computes log2(x+1).

`quantify` detects sample/intensity prefixes, then numeric columns excluding feature_id, mz, rt, name and id. Every sample needs a positive observed intensity; completely missing samples raise ValueError for all methods.
