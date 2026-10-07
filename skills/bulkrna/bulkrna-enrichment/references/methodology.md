# Enrichment methods

All real inputs require an explicit JSON pathway mapping (or `gene_sets` for the library). Demo gene sets contain synthetic identifiers and are never inferred for real data.

ORA selects genes using strict adjusted-p and absolute-effect cutoffs and uses the union of supplied pathways as its universe. GSEApy Enrichr performs the primary local calculation; the fallback is a hypergeometric test with Benjamini–Hochberg correction.

GSEApy prerank uses the first available column among `stat`, `scores`, `logfoldchanges`, `log2FoldChange`, with 100 permutations and seed 42. The built-in fallback instead permutes mean ranks of `log2FoldChange * -log10(pvalue)`. It is not GSEA and is labelled `rank_permutation`. Fallbacks emit a warning and preserve requested/executed method and reason in diagnostics.

The `ora_r` and `gsea_r` adapters are unimplemented and reject calls. This avoids labelling a Python computation as an R backend. The CLI sorts output tables by adjusted p, raw p and term. GSEApy's overlapping-gene string order is hash-dependent; the example canonicalizes it before replay comparison.
