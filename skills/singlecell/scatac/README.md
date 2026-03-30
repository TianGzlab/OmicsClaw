# scATAC Subdomain

`skills/singlecell/scatac/` is the single-cell chromatin accessibility
subdomain container.

Current implemented skill:

- `scatac-preprocessing`:
  Signac-style TF-IDF + LSI preprocessing followed by Scanpy neighbor graph
  construction, UMAP, and Leiden clustering.

Planned follow-on skills for this subdomain include peak annotation, motif
enrichment, gene activity, differential accessibility, and multi-sample
integration.
