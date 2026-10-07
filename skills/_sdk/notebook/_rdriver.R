options(warn = 1)
grDevices::pdf(NULL)

.omicsclaw_run <- function(directory) {
    clean <- function(value) gsub("[\t\r\n]", " ", value)
    on.exit({
        packages <- sort(loadedNamespaces())
        versions <- vapply(packages, function(name) as.character(utils::packageVersion(name)), "")
        writeLines(c(paste("R", R.version.string, sep = "\t"),
                     paste(packages, versions, sep = "\t")),
                   file.path(directory, "session.tsv"))
    })
    for (cell in sort(list.files(directory, pattern = "^cell_[0-9]+\\.R$", full.names = TRUE))) {
        number <- as.integer(sub("^cell_([0-9]+)\\.R$", "\\1", basename(cell)))
        cat(sprintf("##omicsclaw-cell %d##\n", number))
        failure <- tryCatch({
            source(cell, local = globalenv(), print.eval = TRUE, echo = FALSE)
            NULL
        }, error = identity)
        if (inherits(failure, "error")) {
            writeLines(paste(number, class(failure)[1], clean(conditionMessage(failure)), sep = "\t"),
                       file.path(directory, "error.tsv"))
            return(1L)
        }
    }
    0L
}
quit(status = .omicsclaw_run(commandArgs(trailingOnly = TRUE)[1]), save = "no")
