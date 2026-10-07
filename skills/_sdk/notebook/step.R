.omicsclaw_step <- local({
    noticed <- FALSE
    context <- function() {
        step <- Sys.getenv("OMICSCLAW_STEP_FILE")
        if (!nzchar(step)) {
            args <- grep("^--file=", commandArgs(), value = TRUE)
            if (length(args)) step <- sub("^--file=", "", args[1])
        }
        step <- normalizePath(step, winslash = "/", mustWork = TRUE)
        module <- dirname(step)
        if (basename(dirname(module)) != "analysis" ||
            !grepl("^[0-9]{2}_[a-z0-9][a-z0-9_]*$", basename(module)))
            stop("run this step from analysis/<NN_slug>/", call. = FALSE)
        root <- dirname(dirname(module))
        list(root = root, results = file.path(root, "results", basename(module)))
    }
    journal <- function(kind, path, via) {
        if (grepl("[\t\r\n]", path)) stop("IO paths cannot contain tabs or newlines", call. = FALSE)
        target <- Sys.getenv("OMICSCLAW_STEP_IO")
        if (nzchar(target)) {
            cat(paste(kind, path, via, sep = "\t"), "\n", file = target, append = TRUE, sep = "")
        } else if (!noticed) {
            message("note: not running under the step runner; reads and writes are not recorded")
            noticed <<- TRUE
        }
    }
    read <- function(path) {
        suffix <- tolower(tools::file_ext(path))
        if (dir.exists(path)) return(path)
        switch(suffix,
            csv = utils::read.csv(path, check.names = FALSE),
            tsv = utils::read.delim(path, check.names = FALSE),
            rds = readRDS(path),
            mtx = { if (!requireNamespace("Matrix", quietly = TRUE)) stop("reading .mtx needs Matrix")
                    Matrix::readMM(path) },
            txt = paste(readLines(path, warn = FALSE), collapse = "\n"),
            md = paste(readLines(path, warn = FALSE), collapse = "\n"),
            h5ad = stop("write Matrix Market plus CSV in a Python step, or supply reader =", call. = FALSE),
            path)
    }
    write <- function(obj, target, suffix) {
        if (suffix %in% c("csv", "tsv") && (is.data.frame(obj) || is.matrix(obj))) {
            utils::write.table(obj, target, sep = if (suffix == "csv") "," else "\t",
                               row.names = FALSE, col.names = TRUE)
        } else if (suffix == "rds") {
            saveRDS(obj, target)
        } else if (suffix == "mtx" && inherits(obj, "sparseMatrix")) {
            if (!requireNamespace("Matrix", quietly = TRUE)) stop("writing .mtx needs Matrix")
            Matrix::writeMM(obj, target)
        } else if (suffix %in% c("txt", "md") && is.character(obj)) {
            writeLines(obj, target)
        } else if (suffix %in% c("png", "pdf", "svg") && inherits(obj, "ggplot")) {
            if (!requireNamespace("ggplot2", quietly = TRUE)) stop("writing ggplot needs ggplot2")
            ggplot2::ggsave(target, obj, device = suffix, dpi = 150)
        } else if (suffix %in% c("png", "pdf", "svg") && is.function(obj)) {
            switch(suffix, png = grDevices::png(target, width = 1200, height = 900, res = 150),
                   pdf = grDevices::pdf(target), svg = grDevices::svg(target))
            device <- grDevices::dev.cur()
            on.exit(grDevices::dev.off(device), add = TRUE)
            obj()
        } else {
            stop("no default writer for this object and suffix; supply writer =", call. = FALSE)
        }
    }
    list(context = context, journal = journal, read = read, write = write)
})

#' read_input(path, reader = NULL)
#' Read relative to the project root and record the input path. Defaults: CSV/TSV
#' tables, RDS objects, Matrix Market matrices, TXT/MD text; otherwise return the
#' path. For H5AD, export Matrix Market plus CSV in Python or supply reader =.
read_input <- function(path, reader = NULL) {
    ctx <- .omicsclaw_step$context()
    target <- if (grepl("^(/|[A-Za-z]:[/\\\\])", path)) path else file.path(ctx$root, path)
    if (!file.exists(target)) stop(paste("no such input:", path), call. = FALSE)
    .omicsclaw_step$journal("input", target, "read_input")
    if (is.null(reader)) .omicsclaw_step$read(target) else reader(target)
}

#' write_output(obj, path, writer = NULL)
#' Write atomically beneath this module's figures/, tables/, intermediate/ or
#' logs/. Absolute paths and .. are rejected; accepted modules are frozen.
#' Defaults: CSV/TSV tables, RDS objects, sparse MTX, TXT/MD, and ggplot or a
#' no-argument plotting function as PNG/PDF/SVG. Return the written path.
write_output <- function(obj, path, writer = NULL) {
    ctx <- .omicsclaw_step$context()
    parts <- strsplit(path, "/", fixed = TRUE)[[1]]
    if (grepl("^(/|[A-Za-z]:[/\\\\])|[\t\r\n]", path) || ".." %in% parts ||
        length(parts) < 2 || !parts[1] %in% c("figures", "tables", "intermediate", "logs"))
        stop("write_output needs a path inside figures/, tables/, intermediate/ or logs/ without ..", call. = FALSE)
    manifest <- file.path(ctx$results, "provenance", "manifest.json")
    if (file.exists(manifest) && grepl('"frozen"\\s*:\\s*true',
        paste(readLines(manifest, warn = FALSE), collapse = "\n"), perl = TRUE))
        stop("module is accepted and frozen; revise it before writing", call. = FALSE)
    target <- file.path(ctx$results, path)
    dir.create(dirname(target), recursive = TRUE, showWarnings = FALSE)
    temporary <- tempfile(".tmp-", tmpdir = dirname(target), fileext = paste0(".", tools::file_ext(path)))
    on.exit(unlink(temporary), add = TRUE)
    if (is.null(writer)) .omicsclaw_step$write(obj, temporary, tolower(tools::file_ext(path)))
    else writer(obj, temporary)
    if (!file.rename(temporary, target)) stop(paste("cannot replace output:", path), call. = FALSE)
    .omicsclaw_step$journal("output", path, parts[1])
    target
}
