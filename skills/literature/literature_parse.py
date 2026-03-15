#!/usr/bin/env python3
"""Literature parsing CLI - extract GEO data from scientific papers."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skills.literature.core.parser import parse_input
from skills.literature.core.extractor import extract_metadata
from skills.literature.core.downloader import download_geo_dataset


def main():
    parser = argparse.ArgumentParser(description='Parse literature and extract GEO datasets')
    parser.add_argument('--input', required=True, help='URL, DOI, PubMed ID, PDF path, or text')
    parser.add_argument('--input-type', default='auto',
                       choices=['auto', 'url', 'doi', 'pubmed', 'file', 'text'],
                       help='Input type (default: auto-detect)')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--no-download', action='store_true',
                       help='Extract metadata only, skip download')
    parser.add_argument('--data-dir', help='Data directory for downloads (default: data/)')

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # Use project root data/ directory
        project_root = Path(__file__).parent.parent.parent
        data_dir = project_root / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Parsing input: {args.input}")

    # Parse input
    text, detected_type = parse_input(args.input, args.input_type)
    print(f"Detected input type: {detected_type}")

    if not text or text.startswith('Error'):
        print(f"Failed to parse input: {text}")
        sys.exit(1)

    # Extract metadata
    print("Extracting metadata...")
    metadata = extract_metadata(text)

    geo_acc = metadata['geo_accessions']
    gse_ids = geo_acc.get('gse', [])

    print(f"Found {len(gse_ids)} GEO datasets: {', '.join(gse_ids)}")
    print(f"Organism: {metadata['organism']}")
    print(f"Tissue: {metadata['tissue']}")
    print(f"Technology: {metadata['technology']}")

    # Save metadata
    metadata_file = output_dir / 'extracted_metadata.json'
    metadata_file.write_text(json.dumps(metadata, indent=2))

    # Download datasets
    download_results = []
    if not args.no_download and gse_ids:
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
    generate_report(output_dir, metadata, download_results, args.no_download)

    print(f"\n✓ Results saved to {output_dir}")
    print(f"  - Report: {output_dir / 'report.md'}")
    print(f"  - Metadata: {metadata_file}")

    if download_results:
        print(f"  - Downloaded data: {data_dir}")


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
    report_lines.append("- For spatial data: `spatial-preprocessing`")
    report_lines.append("- For single-cell data: `sc-preprocessing`")

    report_file = output_dir / 'report.md'
    report_file.write_text('\n'.join(report_lines))


if __name__ == '__main__':
    main()
