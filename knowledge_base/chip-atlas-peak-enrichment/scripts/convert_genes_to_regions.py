"""
Convert gene symbols to promoter regions using Ensembl REST API.

Supports batch lookup (POST /lookup/symbol) for all genes in one request,
with sequential fallback for robustness.

Includes rate limiting and error handling for robust API queries.
"""

import requests
import time


# Common gene symbol renames (retired → current HGNC symbol)
# Source: HGNC (genenames.org) approved symbol changes
GENE_ALIASES = {
    # Interleukins/chemokines
    'IL8': 'CXCL8',
    'IL8A': 'CXCL8',
    'GRO1': 'CXCL1',
    'GRO2': 'CXCL2',
    'GRO3': 'CXCL3',
    'SDF1': 'CXCL12',
    'MIG': 'CXCL9',
    'IP10': 'CXCL10',
    'MCP1': 'CCL2',
    'MIP1A': 'CCL3',
    'MIP1B': 'CCL4',
    'RANTES': 'CCL5',
    # Apoptosis/signaling
    'TNFSF6': 'FASLG',
    'APO1': 'FAS',
    'TRAIL': 'TNFSF10',
    # Epigenetic regulators
    'MLL': 'KMT2A',
    'MLL2': 'KMT2D',
    'MLL3': 'KMT2C',
    # Other common renames
    'P53': 'TP53',
    'ERK1': 'MAPK3',
    'ERK2': 'MAPK1',
    'P38': 'MAPK14',
}


def convert_genes_to_regions(gene_list, genome="hg38", upstream=2000, downstream=500):
    """
    Convert gene symbols to promoter regions via Ensembl API.

    Parameters:
    -----------
    gene_list : list of str
        Gene symbols (e.g., ['TP53', 'MYC'])
    genome : str
        Genome assembly ('hg38', 'hg19', 'mm10', 'mm9')
    upstream : int
        Bases upstream of TSS
    downstream : int
        Bases downstream of TSS

    Returns:
    --------
    tuple: (successful_regions, failed_genes)
        successful_regions: list of tuples (chr, start, end, gene, strand)
        failed_genes: list of str (genes that couldn't be mapped)

    Notes:
    ------
    - Rate limited to 0.5s between requests
    - Retries on timeout (max 3 attempts)
    - Skips genes not found in Ensembl
    """

    # Map genome assembly prefix to Ensembl species name
    _GENOME_TO_SPECIES = {
        'hg': 'human', 'mm': 'mouse', 'rn': 'rat',
        'dm': 'drosophila_melanogaster', 'ce': 'caenorhabditis_elegans',
        'sacCer': 'saccharomyces_cerevisiae',
    }
    prefix = next((k for k in _GENOME_TO_SPECIES if genome.startswith(k)), None)
    species = _GENOME_TO_SPECIES.get(prefix, 'human')

    # Try batch lookup first (single POST request for all genes)
    successful_regions, failed_genes = _batch_lookup(
        gene_list, species, upstream, downstream
    )

    # Fall back to sequential lookup for any failed genes, with alias retry
    if failed_genes:
        retry_genes = list(failed_genes)
        failed_genes = []
        for gene in retry_genes:
            region = _sequential_lookup(gene, species, upstream, downstream)
            if region is not None:
                successful_regions.append(region)
            elif gene.upper() in GENE_ALIASES:
                alias = GENE_ALIASES[gene.upper()]
                print(f"   Retrying {gene} as {alias} (known rename)...")
                region = _sequential_lookup(alias, species, upstream, downstream)
                if region is not None:
                    # Store with original gene name for traceability
                    region = (region[0], region[1], region[2], gene, region[4])
                    successful_regions.append(region)
                    print(f"   ✓ Mapped {gene} → {alias} successfully")
                else:
                    failed_genes.append(gene)
            else:
                failed_genes.append(gene)
            time.sleep(0.5)

    return successful_regions, failed_genes


def _batch_lookup(gene_list, species, upstream, downstream):
    """
    Batch lookup of gene coordinates via Ensembl POST endpoint.

    Uses POST /lookup/symbol/{species} with {"symbols": [...]} to
    retrieve all genes in a single request.
    """

    base_url = "https://rest.ensembl.org"
    url = f"{base_url}/lookup/symbol/{species}"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    payload = {"symbols": gene_list}

    successful_regions = []
    failed_genes = []

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        for gene in gene_list:
            if gene not in data or data[gene] is None:
                failed_genes.append(gene)
                continue

            gene_data = data[gene]
            region = _parse_gene_data(gene_data, gene, upstream, downstream)
            if region is not None:
                successful_regions.append(region)
            else:
                failed_genes.append(gene)

    except Exception as e:
        print(f"   Batch lookup failed ({e}), falling back to sequential...")
        failed_genes = list(gene_list)

    return successful_regions, failed_genes


def _sequential_lookup(gene, species, upstream, downstream):
    """Look up a single gene via Ensembl GET endpoint."""

    base_url = "https://rest.ensembl.org"
    url = f"{base_url}/lookup/symbol/{species}/{gene}"
    params = {'expand': '0'}

    try:
        response = _fetch_with_retry(url, params, max_retries=3)
        if response is None:
            return None
        data = response.json()
        return _parse_gene_data(data, gene, upstream, downstream)
    except Exception as e:
        print(f"   Warning: Failed to map {gene}: {e}")
        return None


def _parse_gene_data(data, gene, upstream, downstream):
    """Parse Ensembl gene data into promoter region tuple."""

    try:
        chrom = data['seq_region_name']
        gene_start = data['start']
        gene_end = data['end']
        strand = data['strand']

        if strand == 1:
            tss = gene_start
            promoter_start = max(1, tss - upstream)
            promoter_end = tss + downstream
        else:
            tss = gene_end
            promoter_start = max(1, tss - downstream)
            promoter_end = tss + upstream

        if not chrom.startswith('chr'):
            chrom = 'chr' + chrom

        strand_symbol = '+' if strand == 1 else '-'
        return (chrom, promoter_start, promoter_end, gene, strand_symbol)

    except (KeyError, TypeError):
        return None


def _fetch_with_retry(url, params=None, max_retries=3):
    """
    Fetch URL with exponential backoff retry.

    Parameters:
    -----------
    url : str
        URL to fetch
    params : dict or None
        Query parameters
    max_retries : int
        Maximum number of retry attempts

    Returns:
    --------
    requests.Response or None
    """

    # Ensembl API requires Content-Type header
    headers = {'Content-Type': 'application/json'}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                print(f"   Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"   Failed after {max_retries} attempts")
                return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Gene not found in Ensembl
                return None
            elif e.response.status_code == 429:
                # Rate limited
                wait_time = 60
                print(f"   Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                return None

        except Exception as e:
            print(f"   Error: {e}")
            return None

    return None


if __name__ == "__main__":
    # Test with TP53 targets
    test_genes = ["TP53", "MYC", "CDKN1A", "BAX", "INVALID_GENE"]

    print("Testing convert_genes_to_regions...")
    regions, failed = convert_genes_to_regions(test_genes, genome="hg38")

    print(f"\nSuccessful mappings: {len(regions)}")
    for region in regions:
        print(f"  {region[3]}: {region[0]}:{region[1]}-{region[2]} ({region[4]} strand)")

    print(f"\nFailed mappings: {len(failed)}")
    for gene in failed:
        print(f"  {gene}")

