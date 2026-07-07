#!/usr/bin/env python3
"""Download public GEO datasets (SOFT family + series matrix + RAW supplementary).

sc-geo-download fetches publicly available Gene Expression Omnibus (GEO) series
over HTTPS from NCBI and writes them into a layout that the sibling
``sc-geo-import`` skill consumes for AnnData reconstruction.

Typical chain:

    oc run sc-geo-download --accession GSE109564 --output /data
    oc run sc-geo-import   --input /data/geo/GSE109564 --output /data/imported

The skill is Python-only (uses ``requests``); it does NOT fetch raw FASTQ from
SRA. For metadata-only resolution (PubMed -> linked GEO series) it uses the
NCBI Entrez E-utilities.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import logging
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional

import pandas as pd
import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-geo-download"
SKILL_VERSION = "0.1.0"
DOMAIN = "singlecell"
SUMMARY = (
    "Download public GEO series (GSE accessions) from NCBI into the layout that "
    "sc-geo-import consumes."
)

GEO_BASE = "https://ftp.ncbi.nlm.nih.gov/geo/series"
ENTREZ_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ACCESSION_RE = re.compile(r"^GSE\d+$")

USER_AGENT = (
    f"OmicsClaw/{SKILL_NAME}-{SKILL_VERSION} "
    "(https://github.com/TianGzlab/OmicsClaw)"
)


# ---------------------------------------------------------------------------
# URL + network helpers
# ---------------------------------------------------------------------------


def _build_geo_dir_url(accession: str) -> str:
    """Return the GEO series HTTPS directory for ``accession``.

    NCBI groups GSE accessions into buckets where the last three digits are
    replaced with ``nnn``:

        GSE109564  -> GSE109nnn/GSE109564/
        GSE12345   -> GSE12nnn/GSE12345/
        GSE123     -> GSEnnn/GSE123/
    """
    digits = accession[3:]
    if len(digits) <= 3:
        bucket = "GSEnnn"
    else:
        bucket = f"GSE{digits[:-3]}nnn"
    return f"{GEO_BASE}/{bucket}/{accession}"


def _download_stream(
    session: requests.Session,
    url: str,
    dest: Path,
    *,
    timeout: float,
    chunk: int = 1 << 20,
) -> dict[str, Any]:
    """Stream-download ``url`` into ``dest`` atomically. Returns a record dict."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with session.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        n_bytes = 0
        with tmp.open("wb") as fp:
            for buf in resp.iter_content(chunk_size=chunk):
                if buf:
                    fp.write(buf)
                    n_bytes += len(buf)
    tmp.rename(dest)
    return {
        "url": url,
        "path": str(dest),
        "bytes": n_bytes,
        "sha256": sha256_file(dest),
        "status": "downloaded",
    }


_HREF_RE = re.compile(r'href="([^"]+)"')


def _list_directory_files(
    session: requests.Session, url: str, *, timeout: float
) -> list[str]:
    """List filenames in an NCBI Apache autoindex directory by parsing HTML.

    Returns an empty list on 404 or on any failure to parse — callers should
    treat that as "directory absent or empty" and continue.
    """
    if not url.endswith("/"):
        url = url + "/"
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except requests.RequestException:
        return []
    files: list[str] = []
    for href in _HREF_RE.findall(resp.text):
        # Skip parent-dir, anchors, absolute URLs (NCBI footer links), and
        # subdirectory entries (trailing slash).
        if href.startswith(("/", "?", "http", "#")):
            continue
        if href.endswith("/"):
            continue
        files.append(href)
    return files


def _maybe_skip_existing(dest: Path, url: str) -> Optional[dict[str, Any]]:
    """Idempotent skip: when ``dest`` already exists and is non-empty,
    return a 'cached' record without re-fetching."""
    if dest.exists() and dest.stat().st_size > 0:
        return {
            "url": url,
            "path": str(dest),
            "bytes": dest.stat().st_size,
            "sha256": sha256_file(dest),
            "status": "cached",
        }
    return None


def _resolve_pubmed_to_gse(pmid: str, *, session: requests.Session, timeout: float = 30.0) -> list[str]:
    """Resolve a PubMed ID to linked GEO Series accessions via Entrez ELink + ESummary."""
    elink = session.get(
        f"{ENTREZ_BASE}/elink.fcgi",
        params={"dbfrom": "pubmed", "db": "gds", "id": str(pmid), "retmode": "xml"},
        timeout=timeout,
    )
    elink.raise_for_status()
    uids = re.findall(r"<Link>\s*<Id>(\d+)</Id>\s*</Link>", elink.text)
    if not uids:
        return []
    esummary = session.get(
        f"{ENTREZ_BASE}/esummary.fcgi",
        params={"db": "gds", "id": ",".join(uids), "retmode": "json"},
        timeout=timeout,
    )
    esummary.raise_for_status()
    data = esummary.json().get("result", {})
    accessions: list[str] = []
    for uid in uids:
        doc = data.get(uid, {})
        acc = doc.get("accession")
        if isinstance(acc, str) and ACCESSION_RE.match(acc):
            accessions.append(acc)
    return sorted(set(accessions))


def _entrez_metadata(accession: str, *, session: requests.Session, timeout: float = 30.0) -> dict[str, Any]:
    """Return lightweight metadata about a GSE via Entrez ESummary."""
    esearch = session.get(
        f"{ENTREZ_BASE}/esearch.fcgi",
        params={"db": "gds", "term": f"{accession}[Accession]", "retmode": "json"},
        timeout=timeout,
    )
    esearch.raise_for_status()
    ids = esearch.json().get("esearchresult", {}).get("idlist", []) or []
    if not ids:
        return {}
    esummary = session.get(
        f"{ENTREZ_BASE}/esummary.fcgi",
        params={"db": "gds", "id": ids[0], "retmode": "json"},
        timeout=timeout,
    )
    esummary.raise_for_status()
    doc = esummary.json().get("result", {}).get(ids[0], {})
    return {
        "title": doc.get("title", ""),
        "organism": doc.get("taxon", ""),
        "platform": doc.get("gpl", ""),
        "num_samples": int(doc.get("n_samples", 0) or 0),
        "pubmed_ids": [str(p) for p in (doc.get("pubmedids") or [])],
        "summary": doc.get("summary", ""),
        "publication_date": doc.get("pdat", ""),
    }


def _extract_raw_tar(tar_path: Path, *, into: Path) -> list[Path]:
    """Extract a ``_RAW.tar`` archive into per-sample subdirectories keyed by GSM prefix."""
    extracted: list[Path] = []
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = Path(member.name).name
            m = re.match(r"^(GSM\d+)[_.]", name)
            sample_dir = into / (m.group(1) if m else "_misc")
            sample_dir.mkdir(parents=True, exist_ok=True)
            dest = sample_dir / name
            src = tar.extractfile(member)
            if src is None:
                continue
            with src, dest.open("wb") as out:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    out.write(buf)
            extracted.append(dest)
    return extracted


# ---------------------------------------------------------------------------
# Per-accession download
# ---------------------------------------------------------------------------


def _download_accession(
    accession: str,
    *,
    geo_root: Path,
    session: requests.Session,
    include_supp: bool,
    extract_tar: bool,
    fetch_metadata: bool,
    timeout: float,
) -> dict[str, Any]:
    """Download the SOFT family file, series matrix, and (optionally) the RAW
    supplementary archive for a single GSE accession."""
    if not ACCESSION_RE.match(accession):
        raise ValueError(
            f"Invalid GEO accession: {accession!r} (expected GSE<digits>, e.g. GSE109564)"
        )
    base_url = _build_geo_dir_url(accession)
    acc_dir = geo_root / accession
    acc_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []

    def _try_optional(url: str, dest: Path, *, kind: str) -> Optional[dict[str, Any]]:
        """Download an optional file, returning ``None`` on 404 instead of raising."""
        rec = _maybe_skip_existing(dest, url)
        if rec is None:
            try:
                rec = _download_stream(session, url, dest, timeout=timeout)
            except requests.HTTPError as exc:
                if getattr(exc.response, "status_code", None) == 404:
                    return None
                raise
        rec.update({"accession": accession, "kind": kind})
        return rec

    # 1. SOFT family file — the canonical metadata. If this 404s the rest is
    # almost certainly noise, but record `absent` and continue rather than
    # crashing mid-batch when one of many accessions is malformed.
    soft_rec = _try_optional(
        f"{base_url}/soft/{accession}_family.soft.gz",
        acc_dir / f"{accession}_family.soft.gz",
        kind="soft",
    )
    if soft_rec is None:
        logger.warning("No SOFT family file at %s/soft/ (HTTP 404)", base_url)
        soft_rec = {
            "url": f"{base_url}/soft/{accession}_family.soft.gz",
            "path": "", "bytes": 0, "sha256": "", "status": "absent",
            "accession": accession, "kind": "soft",
        }
    records.append(soft_rec)

    # 2. Series matrix. Try the canonical single-platform name first. On 404,
    # fall back to listing matrix/ — multi-platform studies (e.g. GSE109564)
    # split into per-GPL files like `<acc>-GPL<id>_series_matrix.txt.gz`.
    matrix_url_root = f"{base_url}/matrix/"
    canonical_matrix = f"{accession}_series_matrix.txt.gz"
    matrix_rec = _try_optional(
        f"{matrix_url_root}{canonical_matrix}",
        acc_dir / canonical_matrix,
        kind="series_matrix",
    )
    if matrix_rec is not None:
        records.append(matrix_rec)
    else:
        per_gpl = [
            name for name in _list_directory_files(session, matrix_url_root, timeout=timeout)
            if name.startswith(f"{accession}-") and name.endswith("_series_matrix.txt.gz")
        ]
        if per_gpl:
            logger.info("Found %d per-platform series matrices for %s", len(per_gpl), accession)
            for name in per_gpl:
                rec = _try_optional(f"{matrix_url_root}{name}", acc_dir / name, kind="series_matrix")
                if rec is not None:
                    records.append(rec)
        else:
            records.append({
                "url": f"{matrix_url_root}{canonical_matrix}",
                "path": "", "bytes": 0, "sha256": "", "status": "absent",
                "accession": accession, "kind": "series_matrix",
            })

    # 3. Supplementary files. Try the canonical `_RAW.tar` first; if it 404s,
    # list suppl/ and pull every accession-prefixed file (often a single DGE
    # `.txt.gz` or per-sample `.h5` rather than a tarball).
    if include_supp:
        suppl_url_root = f"{base_url}/suppl/"
        raw_dest = acc_dir / f"{accession}_RAW.tar"
        raw_url = f"{suppl_url_root}{accession}_RAW.tar"
        raw_rec = _try_optional(raw_url, raw_dest, kind="raw_tar")
        if raw_rec is not None:
            records.append(raw_rec)
            if extract_tar and raw_rec.get("status") in {"downloaded", "cached"} and raw_dest.exists():
                extracted = _extract_raw_tar(raw_dest, into=acc_dir / "samples")
                logger.info("Extracted %d files from %s -> samples/", len(extracted), raw_dest.name)
        else:
            other_supp = [
                name for name in _list_directory_files(session, suppl_url_root, timeout=timeout)
                if name.startswith(f"{accession}_") and name != f"{accession}_RAW.tar"
            ]
            if other_supp:
                logger.info("Found %d non-tar supplementary files for %s", len(other_supp), accession)
                for name in other_supp:
                    rec = _try_optional(
                        f"{suppl_url_root}{name}", acc_dir / name, kind="supp_file",
                    )
                    if rec is not None:
                        records.append(rec)
            else:
                records.append({
                    "url": raw_url,
                    "path": "", "bytes": 0, "sha256": "", "status": "absent",
                    "accession": accession, "kind": "raw_tar",
                })

    metadata = _entrez_metadata(accession, session=session, timeout=timeout) if fetch_metadata else {}
    return {"accession": accession, "records": records, "metadata": metadata}


# ---------------------------------------------------------------------------
# Demo mode — synthesizes a tiny GEO-like bundle without network
# ---------------------------------------------------------------------------


def _build_synthetic_demo_bundle(geo_root: Path) -> str:
    """Create a tiny SOFT family + series matrix + 10x triplet under ``geo_root/<acc>/``.

    Mirrors the on-disk layout sc-geo-import expects (SOFT + canonical 10x
    triplet), so the two skills can be exercised end-to-end without touching
    the network.
    """
    acc = "GSE_DEMO_OC"
    acc_dir = geo_root / acc
    acc_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ SOFT
    n_cells = 6  # 3 per sample
    barcodes = [f"AAAC{i:04d}-1" for i in range(n_cells)]
    sample_assignment = ["GSM_DEMO_01"] * 3 + ["GSM_DEMO_02"] * 3
    genes = [(f"ENSG{i:08d}", f"GENE_{i}") for i in range(5)]

    soft = (
        "^SERIES = GSE_DEMO_OC\n"
        "!Series_title = OmicsClaw demo dataset\n"
        "!Series_summary = Synthetic GEO-like bundle for sc-geo-download demo.\n"
        "!Series_platform_organism = Homo sapiens\n"
        "^SAMPLE = GSM_DEMO_01\n"
        "!Sample_title = Demo sample 1\n"
        "!Sample_characteristics_ch1 = condition: treated\n"
        "^SAMPLE = GSM_DEMO_02\n"
        "!Sample_title = Demo sample 2\n"
        "!Sample_characteristics_ch1 = severity: healthy\n"
    )
    with gzip.open(acc_dir / f"{acc}_family.soft.gz", "wt", encoding="utf-8") as fp:
        fp.write(soft)

    # ------------------------------------------------------------ series matrix
    with gzip.open(acc_dir / f"{acc}_series_matrix.txt.gz", "wt", encoding="utf-8") as fp:
        fp.write('!Series_title\t"OmicsClaw demo dataset"\n')
        fp.write('!Sample_geo_accession\t"GSM_DEMO_01"\t"GSM_DEMO_02"\n')
        fp.write("!series_matrix_table_begin\n")
        fp.write("ID_REF\tGSM_DEMO_01\tGSM_DEMO_02\n")
        for ens, sym in genes:
            fp.write(f"{ens}\t{ord(sym[-1]) % 7 + 1}\t{ord(sym[-1]) % 5 + 1}\n")
        fp.write("!series_matrix_table_end\n")

    # ----------------------------------- canonical 10x triplet for sc-geo-import
    # Write per-sample suffixes (-1 / -2) so sc-geo-import's barcode-suffix
    # strategies can associate cells with the right GSM.
    suffixed_barcodes = [bc.split("-")[0] + f"-{1 if s == 'GSM_DEMO_01' else 2}"
                         for bc, s in zip(barcodes, sample_assignment)]
    with gzip.open(acc_dir / "barcodes.tsv.gz", "wt", encoding="utf-8") as fp:
        for bc in suffixed_barcodes:
            fp.write(bc + "\n")

    with gzip.open(acc_dir / "features.tsv.gz", "wt", encoding="utf-8") as fp:
        for ens, sym in genes:
            fp.write(f"{ens}\t{sym}\tGene Expression\n")

    # Build a dense count grid, then emit MatrixMarket coordinate format.
    # Layout: rows = features, cols = cells. 10x convention.
    counts = []
    for ci in range(n_cells):
        for gi in range(len(genes)):
            v = ((ci + 1) * (gi + 1)) % 7  # small, deterministic, non-trivial
            if v:
                counts.append((gi + 1, ci + 1, v))  # 1-indexed
    with gzip.open(acc_dir / "matrix.mtx.gz", "wt", encoding="utf-8") as fp:
        fp.write("%%MatrixMarket matrix coordinate integer general\n")
        fp.write("%\n")
        fp.write(f"{len(genes)} {n_cells} {len(counts)}\n")
        for row, col, val in counts:
            fp.write(f"{row} {col} {val}\n")

    return acc


def _demo_results(geo_root: Path) -> list[dict[str, Any]]:
    """Build the same record/metadata shape as the live path for demo mode."""
    acc = _build_synthetic_demo_bundle(geo_root)
    acc_dir = geo_root / acc
    records = []
    for kind, name in (
        ("soft", f"{acc}_family.soft.gz"),
        ("series_matrix", f"{acc}_series_matrix.txt.gz"),
        ("barcodes", "barcodes.tsv.gz"),
        ("features", "features.tsv.gz"),
        ("matrix", "matrix.mtx.gz"),
    ):
        path = acc_dir / name
        records.append({
            "accession": acc,
            "kind": kind,
            "path": str(path),
            "url": "demo://local",
            "status": "synthesized",
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return [{
        "accession": acc,
        "records": records,
        "metadata": {
            "title": "OmicsClaw demo dataset",
            "organism": "Homo sapiens",
            "platform": "",
            "num_samples": 2,
            "pubmed_ids": [],
            "summary": "Synthetic GEO-like bundle",
            "publication_date": "",
        },
    }]


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def _write_manifest(results: list[dict[str, Any]], dest: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ar in results:
        for rec in ar["records"]:
            rows.append({
                "accession": rec.get("accession", ar["accession"]),
                "kind": rec.get("kind", ""),
                "status": rec.get("status", ""),
                "bytes": int(rec.get("bytes", 0) or 0),
                "sha256": rec.get("sha256", ""),
                "path": rec.get("path", ""),
                "url": rec.get("url", ""),
            })
    df = pd.DataFrame(rows, columns=["accession", "kind", "status", "bytes", "sha256", "path", "url"])
    df.to_csv(dest, index=False)
    return df


def _write_metadata(results: list[dict[str, Any]], dest: Path) -> dict[str, Any]:
    meta = {ar["accession"]: ar.get("metadata", {}) for ar in results}
    dest.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _manifest_markdown(df: pd.DataFrame, *, max_rows: int = 50) -> str:
    """Render a tabulate-free markdown table (tabulate is not a project dep)."""
    if df.empty:
        return "_(no files)_"
    columns = list(df.columns)
    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    rows = []
    for _, row in df.head(max_rows).iterrows():
        cells = []
        for col in columns:
            val = row[col]
            if isinstance(val, float) and val.is_integer():
                val = int(val)
            cells.append(str(val).replace("|", "\\|"))
        rows.append("| " + " | ".join(cells) + " |")
    out = "\n".join([head, sep] + rows)
    if len(df) > max_rows:
        out += f"\n\n_…and {len(df) - max_rows} more rows; see `manifest.csv`._"
    return out


def _write_report(
    *,
    output_dir: Path,
    results: list[dict[str, Any]],
    manifest_df: pd.DataFrame,
    metadata: dict[str, Any],
    demo: bool,
) -> None:
    header = generate_report_header(
        title="GEO Dataset Download",
        skill_name=SKILL_NAME,
        extra_metadata={
            "Mode": "demo (synthetic)" if demo else "live (NCBI HTTPS)",
            "Accessions": ", ".join(sorted(metadata.keys())) or "(none)",
            "Files written": str(len(manifest_df)),
            "Total bytes": f"{int(manifest_df['bytes'].sum()):,}",
        },
    )
    lines: list[str] = ["## Per-accession metadata", ""]
    for acc, meta in metadata.items():
        lines.append(f"### {acc}")
        if not meta:
            lines.append("_(no metadata fetched)_")
        else:
            lines.append(f"- **Title**: {meta.get('title') or '_(missing)_'}")
            lines.append(f"- **Organism**: {meta.get('organism') or '_(missing)_'}")
            lines.append(f"- **Platform**: {meta.get('platform') or '_(missing)_'}")
            lines.append(f"- **Samples**: {meta.get('num_samples', 0)}")
            pmids = meta.get("pubmed_ids") or []
            if pmids:
                lines.append(f"- **PubMed**: {', '.join(map(str, pmids))}")
            pdat = meta.get("publication_date")
            if pdat:
                lines.append(f"- **Published**: {pdat}")
        lines.append("")
    lines.append("## Downloaded files")
    lines.append("")
    lines.append(_manifest_markdown(manifest_df))
    lines.append("")
    lines.append("## Next step")
    lines.append("")
    lines.append(
        "For each downloaded accession, run `sc-geo-import` against the per-accession "
        "directory to assemble an OmicsClaw-compatible AnnData:\n"
    )
    for acc in sorted(metadata.keys()):
        lines.append(
            f"```bash\noc run sc-geo-import --input "
            f"{output_dir / 'geo' / acc} --output <import_dir>\n```"
        )
    lines.append("")
    body = "\n".join(lines)
    (output_dir / "report.md").write_text(header + body + "\n" + generate_report_footer(), encoding="utf-8")


def _write_reproducibility(output_dir: Path, args: argparse.Namespace) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = ["oc", "run", SKILL_NAME, "--output", str(output_dir.resolve())]
    if args.demo:
        cmd.append("--demo")
    else:
        for acc in args.accession:
            cmd.extend(["--accession", acc])
        if args.pubmed_id:
            cmd.extend(["--pubmed-id", str(args.pubmed_id)])
        if not args.include_supp:
            cmd.append("--no-include-supp")
        if not args.extract_tar:
            cmd.append("--no-extract-tar")
        if not args.fetch_metadata:
            cmd.append("--no-metadata")
    (repro / "commands.sh").write_text(" ".join(cmd) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=SUMMARY)
    # ``sc-geo-download`` is a fetch-style skill: its input is a GEO accession,
    # not a file. The shared OmicsClaw runner, however, always injects either
    # ``--demo`` or ``--input <path>`` into the argv based on the caller's
    # ``mode`` parameter. To stay compatible with the standard agent/orchestrator
    # invocation path (``mode='path'`` with a placeholder file_path), the skill
    # accepts ``--input`` but ignores it — the real fetch target comes from
    # ``--accession`` and/or ``--pubmed-id``. Hidden from ``--help`` so users
    # don't think this is a file-input skill.
    parser.add_argument(
        "--input", dest="ignored_input_path", default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--accession", action="append", default=[], metavar="GSE",
        help="GEO accession to download (e.g. GSE109564). Repeatable for batch download.",
    )
    parser.add_argument(
        "--pubmed-id", dest="pubmed_id", default=None,
        help="Optional PubMed ID. Linked GEO Series are resolved via Entrez and added "
             "to the download set.",
    )
    parser.add_argument(
        "--output", dest="output_dir", required=True,
        help="Output directory.",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Synthesize a tiny GEO-like bundle locally (no network).",
    )
    parser.add_argument(
        "--include-supp", dest="include_supp", action="store_true", default=True,
        help="Download the `_RAW.tar` supplementary archive (default: True).",
    )
    parser.add_argument(
        "--no-include-supp", dest="include_supp", action="store_false",
        help="Skip the supplementary `_RAW.tar` download.",
    )
    parser.add_argument(
        "--extract-tar", dest="extract_tar", action="store_true", default=True,
        help="Extract `_RAW.tar` into per-sample subdirectories under `samples/` "
             "(default: True).",
    )
    parser.add_argument(
        "--no-extract-tar", dest="extract_tar", action="store_false",
        help="Leave `_RAW.tar` archived; sc-geo-import can still process it.",
    )
    parser.add_argument(
        "--no-metadata", dest="fetch_metadata", action="store_false", default=True,
        help="Skip the Entrez metadata lookup (avoids one extra round-trip per accession).",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0,
        help="Per-HTTP-request timeout in seconds (default: 60).",
    )
    return parser.parse_args(argv)


def _build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    if args.ignored_input_path:
        logger.warning(
            "sc-geo-download is a fetch-style skill — `--input %r` is ignored. "
            "The fetch target comes from --accession / --pubmed-id / --demo.",
            args.ignored_input_path,
        )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    geo_root = output_dir / "geo"
    geo_root.mkdir(parents=True, exist_ok=True)

    if args.demo:
        logger.info("Running in --demo mode (synthetic bundle, no network)")
        results = _demo_results(geo_root)
    else:
        session = _build_session()
        accessions: list[str] = list(args.accession)
        if args.pubmed_id:
            logger.info("Resolving PubMed ID %s -> GEO accessions via Entrez…", args.pubmed_id)
            try:
                resolved = _resolve_pubmed_to_gse(args.pubmed_id, session=session, timeout=args.timeout)
            except requests.RequestException as exc:
                raise SystemExit(f"Entrez PubMed lookup failed: {exc}") from exc
            if not resolved:
                raise SystemExit(f"No GEO Series linked to PubMed ID {args.pubmed_id}.")
            logger.info("PMID %s -> %s", args.pubmed_id, resolved)
            accessions.extend(resolved)
        accessions = sorted(set(accessions))
        if not accessions:
            raise SystemExit(
                "Provide at least one --accession GSE<id>, --pubmed-id, or use --demo."
            )
        results = []
        for acc in accessions:
            logger.info("Downloading %s…", acc)
            try:
                results.append(_download_accession(
                    acc,
                    geo_root=geo_root,
                    session=session,
                    include_supp=args.include_supp,
                    extract_tar=args.extract_tar,
                    fetch_metadata=args.fetch_metadata,
                    timeout=args.timeout,
                ))
            except requests.HTTPError as exc:
                code = getattr(exc.response, "status_code", "?")
                raise SystemExit(
                    f"HTTP error fetching {acc} ({code}): {exc.request.url if exc.request else ''}"
                ) from exc
            except requests.RequestException as exc:
                raise SystemExit(f"Network error fetching {acc}: {exc}") from exc

    manifest_df = _write_manifest(results, output_dir / "manifest.csv")
    metadata = _write_metadata(results, output_dir / "metadata.json")
    _write_report(
        output_dir=output_dir,
        results=results,
        manifest_df=manifest_df,
        metadata=metadata,
        demo=bool(args.demo),
    )
    _write_reproducibility(output_dir, args)

    accessions_listed = sorted(metadata.keys())
    summary = {
        "method": "geo_https",
        "demo": bool(args.demo),
        "accessions": accessions_listed,
        "n_files": int(len(manifest_df)),
        "total_bytes": int(manifest_df["bytes"].sum()),
        "include_supp": bool(args.include_supp),
        "extract_tar": bool(args.extract_tar),
        "fetch_metadata": bool(args.fetch_metadata),
    }
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        {
            "manifest_path": str(output_dir / "manifest.csv"),
            "metadata_path": str(output_dir / "metadata.json"),
            "metadata": metadata,
            "geo_root": str(geo_root),
            "per_accession_paths": {
                acc: str(geo_root / acc) for acc in accessions_listed
            },
        },
    )

    logger.info("Done. Wrote %d files for %d accession(s) -> %s",
                len(manifest_df), len(accessions_listed), output_dir)


if __name__ == "__main__":
    main()
