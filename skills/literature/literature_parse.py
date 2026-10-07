#!/usr/bin/env python3
"""Literature parsing CLI - extract GEO data from scientific papers."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.notebook import load_skill
from skills.literature._lib.input_kind import detect_input_type
from skills.literature._lib.extractor import DOMAIN_ENTRY, infer_domain
from skills.literature.core.downloader import download_geo_dataset

SKILL_NAME = "literature"
SKILL_VERSION = "0.5.0"


DEMO_TEXT = (
    "We profiled human brain spatial transcriptomics with Visium and deposited "
    "the processed data in GEO under accession GSE123456."
)


def main():
    parser = argparse.ArgumentParser(description='Parse literature and extract GEO datasets')
    parser.add_argument('--input', help='URL, DOI, PubMed ID, PDF path, or text')
    parser.add_argument('--input-type', default='auto',
                       choices=['auto', 'url', 'doi', 'pubmed', 'file', 'text'],
                       help='Input type (default: auto-detect)')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--demo', action='store_true', help='Run with built-in local demo text')
    parser.add_argument('--no-download', action='store_true',
                       help='Extract metadata only, skip download')
    parser.add_argument('--data-dir', help='Data directory for downloads (default: data/)')

    args = parser.parse_args()
    if not args.demo and not args.input:
        parser.error('the following arguments are required: --input (unless --demo is used)')

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # Keep default writes inside this Run.  An explicit --data-dir remains
        # an intentionally broader user-selected write surface.
        data_dir = output_dir / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    input_value = DEMO_TEXT if args.demo else args.input
    input_type = 'text' if args.demo else args.input_type
    no_download = bool(args.no_download or args.demo)

    print(f"Parsing input: {input_value}")

    # Parse input
    library = load_skill(SKILL_NAME)
    detected_type = detect_input_type(input_value) if input_type == 'auto' else input_type
    if detected_type == 'file':
        text = library.read_document(input_value)
    elif detected_type in ('url', 'doi', 'pubmed'):
        text = library.fetch_text(input_value, input_type=detected_type)
    else:
        text = input_value
    print(f"Detected input type: {detected_type}")

    if not text or text.startswith('Error'):
        print(f"Failed to parse input: {text}")
        sys.exit(1)

    # Extract metadata
    print("Extracting metadata...")
    accessions = library.extract(text)
    metadata = library.run_info(accessions, keep=False)

    geo_acc = metadata['geo_accessions']
    gse_ids = geo_acc.get('gse', [])

    print(f"Found {len(gse_ids)} GEO datasets: {', '.join(gse_ids)}")
    print(f"Organism: {metadata['organism']}")
    print(f"Tissue: {metadata['tissue']}")
    print(f"Technology: {metadata['technology']}")

    # Save metadata
    metadata_file = output_dir / 'extracted_metadata.json'
    metadata_file.write_text(json.dumps(metadata, indent=2))

    # Persist the parsed source text so EVERY input type (file/url/doi/pubmed/text)
    # leaves one server-controlled, KG-routable artifact the backend can ingest into
    # the knowledge graph (D-1: literature → knowledge → idea grounding).
    source_text_path = output_dir / 'source.txt'
    try:
        source_text_path.write_text(text, encoding='utf-8')
    except OSError:
        source_text_path = None

    # Download datasets
    download_results = []
    if not no_download and gse_ids:
        print(f"\nDownloading datasets to {data_dir}...")
        for gse_id in gse_ids:
            print(f"\nProcessing {gse_id}...")
            result = download_geo_dataset(gse_id, data_dir)
            download_results.append(result)

            if result['status'] == 'success':
                print(f"✓ {gse_id}: Downloaded {len(result['files'])} files")
            elif result['status'] == 'partial':
                print(f"⚠ {gse_id}: Partial download ({len(result['files'])} files)")
            else:
                print(f"✗ {gse_id}: Failed - {', '.join(result['errors'])}")

    # Generate report
    generate_report(output_dir, metadata, download_results, no_download)
    write_result_json(
        output_dir=output_dir,
        metadata=metadata,
        download_results=download_results,
        no_download=no_download,
        detected_type=detected_type,
        demo=args.demo,
        input_value=input_value,
        source_text_path=source_text_path,
    )

    print(f"\n✓ Results saved to {output_dir}")
    print(f"  - Report: {output_dir / 'report.md'}")
    print(f"  - Metadata: {metadata_file}")

    if download_results:
        print(f"  - Downloaded data: {data_dir}")


def write_result_json(
    output_dir: Path,
    *,
    metadata: dict,
    download_results: list,
    no_download: bool,
    detected_type: str,
    demo: bool,
    input_value: str = "",
    source_text_path: Path | None = None,
):
    """Write a minimal OmicsClaw result envelope for downstream output tooling.

    ``source_text_path`` + ``source`` let the backend ingest the parsed source
    into the KG (D-1) so the paper grounds ideation.
    """
    payload = {
        "skill": "literature",
        "version": SKILL_VERSION,
        "success": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "input_checksum": "",
        "summary": {
            "method": "metadata-extraction",
            "gse_count": len(metadata["geo_accessions"].get("gse", [])),
            "organism": metadata.get("organism", "unknown"),
            "technology": metadata.get("technology", "unknown"),
        },
        "data": {
            "metadata": metadata,
            "download_results": download_results,
            "source_text_path": str(source_text_path) if source_text_path else None,
            "source": {"value": input_value, "type": detected_type},
            "params": {
                "input_type": detected_type,
                "no_download": no_download,
                "demo": demo,
            },
        },
    }
    (output_dir / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_report(output_dir: Path, metadata: dict, download_results: list, no_download: bool):
    """Generate markdown report."""
    report_lines = [
        "# Literature Parsing Report",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n## Extracted Metadata",
        f"\n- **Organism**: {metadata['organism']}",
        f"- **Tissue**: {metadata['tissue']}",
        f"- **Technology**: {metadata['technology']}",
    ]

    geo_acc = metadata['geo_accessions']
    if geo_acc['gse']:
        report_lines.append(f"\n## GEO Datasets\n")
        for gse_id in geo_acc['gse']:
            report_lines.append(f"- **{gse_id}**")

    if download_results:
        report_lines.append("\n## Download Results\n")
        for result in download_results:
            gse_id = result['gse_id']
            status = result['status']
            files = result['files']

            if status == 'success':
                report_lines.append(f"### {gse_id} ✓")
                report_lines.append(f"\nDownloaded {len(files)} files:")
                for f in files[:5]:  # Show first 5
                    report_lines.append(f"- `{Path(f).name}`")
                if len(files) > 5:
                    report_lines.append(f"- ... and {len(files) - 5} more")
            else:
                report_lines.append(f"### {gse_id} ✗")
                report_lines.append(f"\nStatus: {status}")
                if result['errors']:
                    report_lines.append(f"\nErrors: {', '.join(result['errors'])}")

    report_lines.append("\n## Next Steps")
    report_lines.append("\nYou can now analyze the downloaded data using OmicsClaw skills:")
    # E-(1): route on the detected technology's omics domain (all 6 domains), not
    # just spatial/single-cell. Unknown technology → list the common starting points.
    domain = infer_domain(metadata.get("technology", ""))
    if domain and domain in DOMAIN_ENTRY:
        entry_skill, label = DOMAIN_ENTRY[domain]
        report_lines.append(f"- Detected **{label}** data → start with `{entry_skill}`")
    else:
        report_lines.append("- For spatial data: `spatial-preprocess`")
        report_lines.append("- For single-cell data: `sc-preprocessing`")
        report_lines.append("- For bulk RNA-seq: `bulkrna-qc` · genomics: `genomics-alignment` · "
                            "proteomics: `proteomics-identification` · metabolomics: `metabolomics-peak-detection`")

    report_file = output_dir / 'report.md'
    report_file.write_text('\n'.join(report_lines))


if __name__ == '__main__':
    main()
