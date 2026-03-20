"""Shared R bridge helpers for single-cell skills.

These helpers adapt the reference Seurat and CellChat scripts into the
OmicsClaw single-cell runtime while keeping Python-first skills intact.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse

from .dependency_manager import validate_r_environment

logger = logging.getLogger(__name__)


def _to_dataframe(obj: Any, pandas2ri, localconverter, default_converter) -> pd.DataFrame:
    with localconverter(default_converter + pandas2ri.converter):
        df = pandas2ri.rpy2py(obj)
    if isinstance(df, pd.Series):
        df = df.to_frame()
    return df


def _to_array(obj: Any, numpy2ri, localconverter, default_converter) -> np.ndarray:
    with localconverter(default_converter + numpy2ri.converter):
        arr = numpy2ri.rpy2py(obj)
    return np.asarray(arr)


def _align_matrix(matrix: np.ndarray, n_obs: int, n_vars: int) -> sparse.csr_matrix:
    arr = np.asarray(matrix)
    if arr.shape == (n_obs, n_vars):
        return sparse.csr_matrix(arr)
    if arr.shape == (n_vars, n_obs):
        return sparse.csr_matrix(arr.T)
    raise ValueError(
        f"Unexpected matrix shape {arr.shape}; expected {(n_obs, n_vars)} or {(n_vars, n_obs)}"
    )


def _subset_adata(adata, cells: list[str], genes: list[str]):
    cells = pd.Index([str(x) for x in cells])
    genes = pd.Index([str(x) for x in genes])
    common_cells = [c for c in cells if c in adata.obs_names]
    common_genes = [g for g in genes if g in adata.var_names]
    if not common_genes:
        reverse_gene_map = {str(g).replace("_", "-"): str(g) for g in adata.var_names}
        mapped = [reverse_gene_map[g] for g in genes if g in reverse_gene_map]
        common_genes = mapped
    if not common_cells:
        raise ValueError("R bridge returned no cells matching the AnnData input")
    if not common_genes:
        raise ValueError("R bridge returned no genes matching the AnnData input")
    return adata[common_cells, common_genes].copy()


def _sync_obs(adata, obs_df: pd.DataFrame) -> None:
    obs_df = obs_df.copy()
    obs_df.index = obs_df.index.astype(str)
    obs_df = obs_df.reindex(adata.obs_names)
    for col in obs_df.columns:
        adata.obs[col] = obs_df[col].values


def _sync_embedding(adata, key: str, values: np.ndarray, expected_rows: int) -> None:
    arr = np.asarray(values)
    if arr.ndim != 2:
        raise ValueError(f"Embedding '{key}' must be 2D, got {arr.shape}")
    if arr.shape[0] != expected_rows and arr.shape[1] == expected_rows:
        arr = arr.T
    if arr.shape[0] != expected_rows:
        raise ValueError(f"Embedding '{key}' rows {arr.shape[0]} do not match {expected_rows}")
    adata.obsm[key] = arr


def _get_r_callable(code: str):
    robjects, pandas2ri, numpy2ri, importr, localconverter, default_converter, openrlib, anndata2ri = (
        validate_r_environment()
    )
    with openrlib.rlock:
        func = robjects.r(code)
    return func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri


def _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib):
    from rpy2.robjects import conversion

    with openrlib.rlock:
        with localconverter(default_converter + anndata2ri.converter):
            return conversion.get_conversion().py2rpy(adata)


def run_seurat_preprocessing(
    adata,
    *,
    workflow: str = "seurat",
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
):
    """Run Seurat-based preprocessing and return an updated AnnData object."""
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, workflow, min_genes, min_cells, max_mt_pct, n_top_hvg, n_pcs, n_neighbors, resolution) {
            suppressPackageStartupMessages({
                library(Seurat)
                library(SingleCellExperiment)
            })
            if (workflow == "sctransform" && !requireNamespace("sctransform", quietly = TRUE)) {
                stop("SCTransform workflow requires the R package 'sctransform'")
            }
            sce <- adata
            counts <- SummarizedExperiment::assay(sce, "X")
            meta <- as.data.frame(SummarizedExperiment::colData(sce))
            seurat_obj <- CreateSeuratObject(
                counts = counts,
                meta.data = meta,
                min.cells = as.integer(min_cells),
                min.features = as.integer(min_genes)
            )
            mt_pattern <- if (sum(grepl("^MT-", rownames(seurat_obj))) > 0) "^MT-" else "^mt-"
            seurat_obj[["percent.mt"]] <- PercentageFeatureSet(seurat_obj, pattern = mt_pattern)
            seurat_obj <- subset(
                seurat_obj,
                subset = nFeature_RNA >= min_genes & percent.mt <= max_mt_pct
            )
            if (workflow == "sctransform") {
                seurat_obj <- SCTransform(
                    seurat_obj,
                    vars.to.regress = if ("percent.mt" %in% colnames(seurat_obj@meta.data)) "percent.mt" else NULL,
                    variable.features.n = as.integer(n_top_hvg),
                    verbose = FALSE
                )
            } else {
                seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
                seurat_obj <- FindVariableFeatures(
                    seurat_obj,
                    selection.method = "vst",
                    nfeatures = as.integer(n_top_hvg),
                    verbose = FALSE
                )
                seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)
            }
            seurat_obj <- RunPCA(seurat_obj, npcs = as.integer(n_pcs), verbose = FALSE)
            seurat_obj <- FindNeighbors(
                seurat_obj,
                dims = seq_len(min(as.integer(n_pcs), ncol(Embeddings(seurat_obj, "pca")))),
                k.param = as.integer(n_neighbors),
                verbose = FALSE
            )
            seurat_obj <- FindClusters(seurat_obj, resolution = resolution, verbose = FALSE)
            seurat_obj <- RunUMAP(
                seurat_obj,
                dims = seq_len(min(as.integer(n_pcs), ncol(Embeddings(seurat_obj, "pca")))),
                verbose = FALSE
            )
            meta_out <- seurat_obj@meta.data
            meta_out$seurat_clusters <- as.character(Idents(seurat_obj))
            assay_name <- DefaultAssay(seurat_obj)
            norm_mat <- as.matrix(GetAssayData(seurat_obj, assay = assay_name, slot = "data"))
            list(
                cells = colnames(seurat_obj),
                genes = rownames(seurat_obj),
                X = norm_mat,
                obs = meta_out,
                hvg = VariableFeatures(seurat_obj),
                pca = Embeddings(seurat_obj, "pca"),
                umap = Embeddings(seurat_obj, "umap"),
                assay = assay_name
            )
        }
        '''
    )
    validate_r_environment(["Seurat", "SingleCellExperiment"])
    r_adata = _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(
            r_adata,
            workflow,
            int(min_genes),
            int(min_cells),
            float(max_mt_pct),
            int(n_top_hvg),
            int(n_pcs),
            int(n_neighbors),
            float(leiden_resolution),
        )

    cells = [str(x) for x in list(result.rx2("cells"))]
    genes = [str(x) for x in list(result.rx2("genes"))]
    updated = _subset_adata(adata, cells, genes)
    updated.layers["counts"] = updated.X.copy()
    updated.X = _align_matrix(
        _to_array(result.rx2("X"), numpy2ri, localconverter, default_converter),
        updated.n_obs,
        updated.n_vars,
    )
    _sync_obs(updated, _to_dataframe(result.rx2("obs"), pandas2ri, localconverter, default_converter))
    if "nFeature_RNA" in updated.obs and "n_genes_by_counts" not in updated.obs:
        updated.obs["n_genes_by_counts"] = updated.obs["nFeature_RNA"].values
    if "nCount_RNA" in updated.obs and "total_counts" not in updated.obs:
        updated.obs["total_counts"] = updated.obs["nCount_RNA"].values
    if "percent.mt" in updated.obs and "pct_counts_mt" not in updated.obs:
        updated.obs["pct_counts_mt"] = updated.obs["percent.mt"].values
    updated.var["highly_variable"] = updated.var_names.isin([str(x) for x in list(result.rx2("hvg"))])
    _sync_embedding(updated, "X_pca", _to_array(result.rx2("pca"), numpy2ri, localconverter, default_converter), updated.n_obs)
    _sync_embedding(updated, "X_umap", _to_array(result.rx2("umap"), numpy2ri, localconverter, default_converter), updated.n_obs)
    updated.obs["leiden"] = updated.obs["seurat_clusters"].astype(str)
    updated.uns["preprocessing"] = {
        "method": workflow,
        "default_assay": str(result.rx2("assay")[0]),
    }
    return updated


def run_singler_annotation(adata, *, reference: str = "HPCA") -> pd.DataFrame:
    """Run SingleR annotation on an AnnData object."""
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, reference_name) {
            suppressPackageStartupMessages({
                library(SingleR)
                library(celldex)
                library(SingleCellExperiment)
            })
            sce <- adata
            ref_data <- switch(
                reference_name,
                HPCA = celldex::HumanPrimaryCellAtlasData(),
                Blueprint_Encode = celldex::BlueprintEncodeData(),
                Monaco = celldex::MonacoImmuneData(),
                Mouse = celldex::MouseRNAseqData(),
                stop(sprintf("Unsupported SingleR reference: %s", reference_name))
            )
            pred <- SingleR(
                test = SummarizedExperiment::assay(sce, "X"),
                ref = ref_data,
                labels = ref_data$label.main
            )
            score <- apply(pred$scores, 1, max)
            out <- data.frame(
                cell = colnames(sce),
                cell_type = pred$labels,
                pruned_label = ifelse(is.na(pred$pruned.labels), pred$labels, pred$pruned.labels),
                score = score,
                stringsAsFactors = FALSE,
                row.names = colnames(sce)
            )
            out
        }
        '''
    )
    validate_r_environment(["SingleR", "celldex", "SingleCellExperiment"])
    r_adata = _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(r_adata, reference)
    return _to_dataframe(result, pandas2ri, localconverter, default_converter)


def run_doubletfinder(adata, *, expected_doublet_rate: float = 0.06) -> pd.DataFrame:
    """Run DoubletFinder on AnnData-derived Seurat object."""
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, expected_rate) {
            suppressPackageStartupMessages({
                library(Seurat)
                library(DoubletFinder)
                library(SingleCellExperiment)
            })
            sce <- adata
            counts <- SummarizedExperiment::assay(sce, "X")
            meta <- as.data.frame(SummarizedExperiment::colData(sce))
            seurat_obj <- CreateSeuratObject(counts = counts, meta.data = meta)
            seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
            seurat_obj <- FindVariableFeatures(seurat_obj, verbose = FALSE)
            seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)
            seurat_obj <- RunPCA(seurat_obj, npcs = 30, verbose = FALSE)
            seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30, verbose = FALSE)
            seurat_obj <- FindClusters(seurat_obj, resolution = 0.5, verbose = FALSE)
            pK_optimal <- 0.15
            annotations <- as.character(Idents(seurat_obj))
            homotypic_prop <- modelHomotypic(annotations)
            nExp_poi <- round(expected_rate * ncol(seurat_obj))
            nExp_poi_adj <- max(1, round(nExp_poi * (1 - homotypic_prop)))
            seurat_obj <- doubletFinder(
                seurat_obj,
                PCs = 1:30,
                pN = 0.25,
                pK = pK_optimal,
                nExp = nExp_poi_adj,
                reuse.pANN = FALSE,
                sct = FALSE
            )
            df_cols <- grep("^DF.classifications", colnames(seurat_obj@meta.data), value = TRUE)
            pann_cols <- grep("^pANN", colnames(seurat_obj@meta.data), value = TRUE)
            out <- data.frame(
                cell = colnames(seurat_obj),
                classification = as.character(seurat_obj@meta.data[[df_cols[1]]]),
                doublet_score = as.numeric(seurat_obj@meta.data[[pann_cols[1]]]),
                predicted_doublet = as.character(seurat_obj@meta.data[[df_cols[1]]]) == "Doublet",
                stringsAsFactors = FALSE,
                row.names = colnames(seurat_obj)
            )
            out
        }
        '''
    )
    validate_r_environment(["Seurat", "DoubletFinder", "SingleCellExperiment"])
    r_adata = _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(r_adata, float(expected_doublet_rate))
    return _to_dataframe(result, pandas2ri, localconverter, default_converter)


def run_scdblfinder(adata, *, expected_doublet_rate: float = 0.06) -> pd.DataFrame:
    """Run scDblFinder on AnnData-derived SingleCellExperiment."""
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, expected_rate) {
            suppressPackageStartupMessages({
                library(scDblFinder)
                library(SingleCellExperiment)
            })
            sce <- adata
            SummarizedExperiment::assay(sce, "counts") <- round(SummarizedExperiment::assay(sce, "X"))
            set.seed(42)
            sce <- scDblFinder::scDblFinder(sce, dbr = expected_rate, verbose = FALSE)
            out <- data.frame(
                cell = colnames(sce),
                classification = as.character(colData(sce)$scDblFinder.class),
                doublet_score = as.numeric(colData(sce)$scDblFinder.score),
                predicted_doublet = as.character(colData(sce)$scDblFinder.class) == "doublet",
                stringsAsFactors = FALSE,
                row.names = colnames(sce)
            )
            out
        }
        '''
    )
    validate_r_environment(["scDblFinder", "SingleCellExperiment"])
    r_adata = _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(r_adata, float(expected_doublet_rate))
    return _to_dataframe(result, pandas2ri, localconverter, default_converter)


def run_seurat_integration(
    adata,
    *,
    method: str,
    batch_key: str,
    n_features: int = 2000,
    n_pcs: int = 30,
):
    """Run an R-backed integration workflow and return embeddings."""
    if method not in {"seurat_cca", "seurat_rpca", "fastmnn"}:
        raise ValueError(f"Unsupported R integration method: {method}")

    if method == "fastmnn":
        required = ["batchelor", "SingleCellExperiment"]
    else:
        required = ["Seurat", "SingleCellExperiment"]
    validate_r_environment(required)

    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, method_name, batch_key, n_features, n_pcs) {
            suppressPackageStartupMessages({
                library(SingleCellExperiment)
            })
            sce <- adata
            meta <- as.data.frame(SummarizedExperiment::colData(sce))
            if (!batch_key %in% colnames(meta)) {
                stop(sprintf("Batch key '%s' not found in metadata", batch_key))
            }
            if (method_name == "fastmnn") {
                suppressPackageStartupMessages(library(batchelor))
                SummarizedExperiment::assay(sce, "counts") <- SummarizedExperiment::assay(sce, "X")
                SummarizedExperiment::assay(sce, "logcounts") <- log1p(SummarizedExperiment::assay(sce, "X"))
                split_idx <- split(seq_len(ncol(sce)), meta[[batch_key]])
                sce_list <- lapply(split_idx, function(idx) sce[, idx])
                mnn <- do.call(batchelor::fastMNN, c(sce_list, list(d = as.integer(n_pcs))))
                out <- data.frame(row.names = colnames(mnn))
                list(
                    cells = colnames(mnn),
                    embedding = reducedDim(mnn, "corrected"),
                    obs = out
                )
            } else {
                suppressPackageStartupMessages(library(Seurat))
                counts <- SummarizedExperiment::assay(sce, "X")
                seurat_obj <- CreateSeuratObject(counts = counts, meta.data = meta)
                seurat_list <- SplitObject(seurat_obj, split.by = batch_key)
                seurat_list <- lapply(seurat_list, function(x) {
                    x <- NormalizeData(x, verbose = FALSE)
                    x <- FindVariableFeatures(x, nfeatures = as.integer(n_features), verbose = FALSE)
                    x
                })
                features <- SelectIntegrationFeatures(seurat_list, nfeatures = as.integer(n_features))
                reduction_name <- if (method_name == "seurat_rpca") "rpca" else "cca"
                if (method_name == "seurat_rpca") {
                    seurat_list <- lapply(seurat_list, function(x) {
                        x <- ScaleData(x, features = features, verbose = FALSE)
                        x <- RunPCA(x, features = features, npcs = as.integer(n_pcs), verbose = FALSE)
                        x
                    })
                }
                anchors <- FindIntegrationAnchors(
                    object.list = seurat_list,
                    anchor.features = features,
                    reduction = reduction_name,
                    dims = seq_len(as.integer(n_pcs))
                )
                integrated <- IntegrateData(anchorset = anchors, dims = seq_len(as.integer(n_pcs)))
                DefaultAssay(integrated) <- "integrated"
                integrated <- ScaleData(integrated, verbose = FALSE)
                integrated <- RunPCA(integrated, npcs = as.integer(n_pcs), verbose = FALSE)
                integrated <- RunUMAP(integrated, dims = seq_len(as.integer(n_pcs)), verbose = FALSE)
                out <- integrated@meta.data
                list(
                    cells = colnames(integrated),
                    embedding = Embeddings(integrated, "pca"),
                    umap = Embeddings(integrated, "umap"),
                    obs = out
                )
            }
        }
        '''
    )
    r_adata = _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(r_adata, method, batch_key, int(n_features), int(n_pcs))
    cells = [str(x) for x in list(result.rx2("cells"))]
    updated = _subset_adata(adata, cells, list(adata.var_names))
    _sync_embedding(updated, f"X_{method}", _to_array(result.rx2("embedding"), numpy2ri, localconverter, default_converter), updated.n_obs)
    obs_df = _to_dataframe(result.rx2("obs"), pandas2ri, localconverter, default_converter)
    if not obs_df.empty:
        _sync_obs(updated, obs_df)
    if "umap" in list(result.names):
        _sync_embedding(updated, "X_umap", _to_array(result.rx2("umap"), numpy2ri, localconverter, default_converter), updated.n_obs)
    return updated


def run_soupx(
    *,
    raw_matrix_dir: str,
    filtered_matrix_dir: str,
) -> tuple[sparse.csr_matrix, list[str], list[str], float]:
    """Run SoupX on 10x raw/filtered matrices and return corrected counts."""
    validate_r_environment(["Seurat", "SoupX"])
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(raw_dir, filtered_dir) {
            suppressPackageStartupMessages({
                library(Seurat)
                library(SoupX)
            })
            raw_data <- Read10X(raw_dir)
            filtered_data <- Read10X(filtered_dir)
            seurat_temp <- CreateSeuratObject(counts = filtered_data)
            seurat_temp <- NormalizeData(seurat_temp, verbose = FALSE)
            seurat_temp <- FindVariableFeatures(seurat_temp, verbose = FALSE)
            seurat_temp <- ScaleData(seurat_temp, verbose = FALSE)
            seurat_temp <- RunPCA(seurat_temp, npcs = 30, verbose = FALSE)
            seurat_temp <- FindNeighbors(seurat_temp, dims = 1:30, verbose = FALSE)
            seurat_temp <- FindClusters(seurat_temp, resolution = 0.8, verbose = FALSE)
            sc <- SoupChannel(raw_data, filtered_data)
            sc <- setClusters(sc, Idents(seurat_temp))
            sc <- autoEstCont(sc)
            rho <- as.numeric(sc$metaData$rho[1])
            corrected <- adjustCounts(sc)
            list(
                cells = colnames(corrected),
                genes = rownames(corrected),
                X = as.matrix(corrected),
                contamination = rho
            )
        }
        '''
    )
    with openrlib.rlock:
        result = func(str(Path(raw_matrix_dir)), str(Path(filtered_matrix_dir)))
    cells = [str(x) for x in list(result.rx2("cells"))]
    genes = [str(x) for x in list(result.rx2("genes"))]
    matrix = _align_matrix(
        _to_array(result.rx2("X"), numpy2ri, localconverter, default_converter),
        len(cells),
        len(genes),
    )
    contamination = float(result.rx2("contamination")[0])
    return matrix, cells, genes, contamination


def run_pseudobulk_deseq2(
    adata,
    *,
    condition_key: str,
    case_label: str,
    reference_label: str,
    sample_key: str,
    celltype_key: str,
) -> pd.DataFrame:
    """Run DESeq2 pseudobulk differential expression in R."""
    validate_r_environment(["DESeq2", "muscat", "SingleCellExperiment"])
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, condition_key, case_label, reference_label, sample_key, celltype_key) {
            suppressPackageStartupMessages({
                library(DESeq2)
                library(muscat)
                library(SingleCellExperiment)
            })
            sce <- adata
            meta <- as.data.frame(SummarizedExperiment::colData(sce))
            for (key in c(condition_key, sample_key, celltype_key)) {
                if (!key %in% colnames(meta)) {
                    stop(sprintf("Column '%s' not found in metadata", key))
                }
            }
            SummarizedExperiment::assay(sce, "counts") <- round(SummarizedExperiment::assay(sce, "X"))
            colData(sce)$sample_id <- meta[[sample_key]]
            colData(sce)$cluster_id <- meta[[celltype_key]]
            colData(sce)$condition <- meta[[condition_key]]
            pb <- aggregateData(sce, assay = "counts", fun = "sum", by = c("cluster_id", "sample_id"))
            sample_meta <- unique(meta[, c(sample_key, condition_key)])
            rownames(sample_meta) <- sample_meta[[sample_key]]
            out_list <- list()
            for (celltype in assayNames(pb)) {
                counts <- assay(pb, celltype)
                md <- data.frame(sample_id = colnames(counts), row.names = colnames(counts))
                md$condition <- sample_meta[md$sample_id, condition_key]
                keep_samples <- !is.na(md$condition) & md$condition %in% c(case_label, reference_label)
                counts <- counts[, keep_samples, drop = FALSE]
                md <- md[keep_samples, , drop = FALSE]
                if (ncol(counts) < 2 || length(unique(md$condition)) < 2) {
                    next
                }
                dds <- DESeqDataSetFromMatrix(countData = round(counts), colData = md, design = ~ condition)
                keep_genes <- rowSums(counts(dds) >= 10) >= 2
                dds <- dds[keep_genes, ]
                if (nrow(dds) == 0) {
                    next
                }
                dds$condition <- relevel(as.factor(dds$condition), ref = reference_label)
                dds <- DESeq(dds, quiet = TRUE)
                res <- results(dds, contrast = c("condition", case_label, reference_label))
                res_df <- as.data.frame(res)
                res_df$gene <- rownames(res_df)
                res_df$cell_type <- celltype
                out_list[[celltype]] <- res_df
            }
            if (length(out_list) == 0) {
                return(data.frame())
            }
            out <- do.call(rbind, out_list)
            rownames(out) <- NULL
            out
        }
        '''
    )
    r_adata = _convert_anndata(adata, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(r_adata, condition_key, case_label, reference_label, sample_key, celltype_key)
    return _to_dataframe(result, pandas2ri, localconverter, default_converter)


def run_cellchat(
    adata,
    *,
    cell_type_key: str = "cell_type",
    species: str = "human",
) -> pd.DataFrame:
    """Run CellChat and return the inferred ligand-receptor table."""
    validate_r_environment(["CellChat"])
    if getattr(adata, "raw", None) is not None:
        adata_r = adata.raw.to_adata()
        adata_r.obs = adata.obs.copy()
    else:
        adata_r = adata
    func, robjects, pandas2ri, numpy2ri, localconverter, default_converter, openrlib, anndata2ri = _get_r_callable(
        r'''
        function(adata, cell_type_key, species) {
            suppressPackageStartupMessages({
                library(CellChat)
                library(SingleCellExperiment)
            })
            sce <- adata
            counts <- SummarizedExperiment::assay(sce, "X")
            meta <- as.data.frame(SummarizedExperiment::colData(sce))
            if (!cell_type_key %in% colnames(meta)) {
                stop(sprintf("Cell type key '%s' not found in metadata", cell_type_key))
            }
            if (!"samples" %in% colnames(meta)) {
                meta$samples <- "sample1"
            }
            cellchat <- createCellChat(object = counts, meta = meta, group.by = cell_type_key)
            cellchat@DB <- if (tolower(species) == "mouse") CellChatDB.mouse else CellChatDB.human
            cellchat <- subsetData(cellchat)
            cellchat <- identifyOverExpressedGenes(cellchat, do.fast = FALSE)
            cellchat <- identifyOverExpressedInteractions(cellchat)
            cellchat <- computeCommunProb(cellchat, raw.use = TRUE, type = "triMean")
            cellchat <- filterCommunication(cellchat, min.cells = 10)
            cellchat <- computeCommunProbPathway(cellchat)
            cellchat <- aggregateNet(cellchat)
            cellchat <- netAnalysis_computeCentrality(cellchat)
            df <- subsetCommunication(cellchat)
            if (!nrow(df)) {
                return(data.frame())
            }
            out <- data.frame(
                ligand = df$ligand,
                receptor = df$receptor,
                source = df$source,
                target = df$target,
                pathway = df$pathway_name,
                score = df$prob,
                pvalue = df$pval,
                stringsAsFactors = FALSE
            )
            out
        }
        '''
    )
    r_adata = _convert_anndata(adata_r, anndata2ri, localconverter, default_converter, openrlib)
    with openrlib.rlock:
        result = func(r_adata, cell_type_key, species)
    return _to_dataframe(result, pandas2ri, localconverter, default_converter)
