# Output contract

`extracted_metadata.json`, `source.txt`, `report.md` and `result.json` at the output root. The CLI creates data/ and optionally downloads into per-GSE directories; --data-dir chooses another destination. The original source.txt write remains best-effort. The function library writes no files.

Public functions return tables, text or Figures; the CLI owns durable writes.
