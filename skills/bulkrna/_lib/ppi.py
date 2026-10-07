"""Local PPI topology analysis and seeded demonstration helpers."""
import numpy as np
import pandas as pd

_DEMO_GENES = [
    "TP53", "BRCA1", "ERBB2", "PTEN", "BRAF", "KRAS", "EGFR", "MYC",
    "CDK4", "RB1", "AKT1", "PIK3CA", "MTOR", "MDM2", "ATM", "CDKN2A",
    "NRAS", "RAF1", "MAP2K1", "MAPK1", "JAK2", "STAT3", "BCL2", "BAX",
    "CASP3", "VEGFA", "FLT1", "KDR", "PDGFRA", "FGFR1",
]

_DEMO_EDGES = [
    ("TP53", "MDM2", 999), ("TP53", "CDKN2A", 950), ("TP53", "ATM", 980),
    ("TP53", "BAX", 970), ("TP53", "BCL2", 910), ("TP53", "CASP3", 850),
    ("BRCA1", "ATM", 990), ("BRCA1", "TP53", 920), ("BRCA1", "RB1", 800),
    ("KRAS", "BRAF", 999), ("KRAS", "RAF1", 990), ("KRAS", "NRAS", 950),
    ("KRAS", "PIK3CA", 910), ("KRAS", "MAP2K1", 900),
    ("EGFR", "ERBB2", 990), ("EGFR", "PIK3CA", 950), ("EGFR", "KRAS", 920),
    ("EGFR", "AKT1", 880), ("EGFR", "STAT3", 830),
    ("AKT1", "MTOR", 990), ("AKT1", "PIK3CA", 980), ("AKT1", "PTEN", 970),
    ("PIK3CA", "PTEN", 999), ("PIK3CA", "MTOR", 960),
    ("MYC", "CDK4", 850), ("MYC", "CDKN2A", 810), ("MYC", "RB1", 780),
    ("CDK4", "RB1", 999), ("CDK4", "CDKN2A", 990),
    ("BRAF", "MAP2K1", 999), ("MAP2K1", "MAPK1", 999), ("BRAF", "RAF1", 950),
    ("JAK2", "STAT3", 999), ("VEGFA", "KDR", 999), ("VEGFA", "FLT1", 990),
    ("BCL2", "BAX", 999), ("BCL2", "CASP3", 960),
    ("PDGFRA", "PIK3CA", 800), ("FGFR1", "MAPK1", 780),
]

def _generate_demo_de() -> pd.DataFrame:
    """Generate demo DE results with gene names."""
    rng = np.random.RandomState(42)
    records = []
    for g in _DEMO_GENES:
        lfc = rng.normal(0, 2)
        pval = 10 ** rng.uniform(-10, -0.5)
        records.append({"gene": g, "log2FoldChange": round(lfc, 4), "padj": round(pval, 8)})
    return pd.DataFrame(records)

def _build_adjacency(edges_df: pd.DataFrame, gene_list: list[str]) -> dict:
    """Build adjacency list from edge DataFrame."""
    adj: dict[str, set[str]] = {g: set() for g in gene_list}
    for _, row in edges_df.iterrows():
        a, b = row["gene_a"], row["gene_b"]
        if a in adj:
            adj[a].add(b)
        if b in adj:
            adj[b].add(a)
    return adj

def _compute_centrality(adj: dict[str, set[str]]) -> pd.DataFrame:
    """Compute degree and betweenness centrality."""
    genes = list(adj.keys())
    n = len(genes)
    gene_idx = {g: i for i, g in enumerate(genes)}

    # Degree centrality
    degree = {g: len(neighbors) for g, neighbors in adj.items()}

    # Betweenness centrality (BFS-based)
    betweenness = {g: 0.0 for g in genes}
    for s in genes:
        # BFS
        visited = {s}
        queue = [s]
        pred: dict[str, list[str]] = {g: [] for g in genes}
        dist: dict[str, int] = {g: -1 for g in genes}
        sigma: dict[str, int] = {g: 0 for g in genes}
        dist[s] = 0
        sigma[s] = 1
        order = []

        while queue:
            v = queue.pop(0)
            order.append(v)
            for w in sorted(adj.get(v, set())):
                if w not in dist:
                    continue
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                    visited.add(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta = {g: 0.0 for g in genes}
        for w in reversed(order[1:]):
            for v in pred[w]:
                delta[v] += (sigma[v] / max(sigma[w], 1)) * (1 + delta[w])
            betweenness[w] += delta[w]

    # Normalize
    norm_factor = max((n - 1) * (n - 2), 1)
    betweenness = {g: v / norm_factor for g, v in betweenness.items()}

    # Closeness centrality
    closeness = {}
    for s in genes:
        # BFS shortest paths
        visited_set = {s}
        queue_bfs = [(s, 0)]
        total_dist = 0
        reachable = 0
        while queue_bfs:
            v, d = queue_bfs.pop(0)
            total_dist += d
            reachable += 1
            for w in sorted(adj.get(v, set())):
                if w not in visited_set:
                    visited_set.add(w)
                    queue_bfs.append((w, d + 1))
        closeness[s] = (reachable - 1) / max(total_dist, 1) if reachable > 1 else 0.0

    records = []
    for g in genes:
        hub_score = 0.5 * (degree[g] / max(max(degree.values()), 1)) + \
                    0.5 * (betweenness[g] / max(max(betweenness.values()), 1e-10))
        records.append({
            "gene": g,
            "degree": degree[g],
            "betweenness": round(betweenness[g], 6),
            "closeness": round(closeness[g], 6),
            "hub_score": round(hub_score, 6),
        })
    return pd.DataFrame(records).sort_values("hub_score", ascending=False).reset_index(drop=True)

def _spring_layout(adj: dict[str, set[str]], genes: list[str],
                   iterations: int = 100, random_state: int = 42) -> dict[str, tuple[float, float]]:
    """Simple Fruchterman-Reingold spring layout."""
    rng = np.random.RandomState(random_state)
    n = len(genes)
    pos = rng.uniform(-1, 1, size=(n, 2))
    gene_idx = {g: i for i, g in enumerate(genes)}

    k = np.sqrt(4.0 / max(n, 1))  # optimal distance
    temperature = 1.0

    for iteration in range(iterations):
        disp = np.zeros((n, 2))
        # Repulsion
        for i in range(n):
            for j in range(i + 1, n):
                delta = pos[i] - pos[j]
                dist = max(np.linalg.norm(delta), 0.01)
                force = k * k / dist
                direction = delta / dist
                disp[i] += direction * force
                disp[j] -= direction * force

        # Attraction
        for g, neighbors in adj.items():
            i = gene_idx.get(g)
            if i is None:
                continue
            for nb in sorted(neighbors):
                j = gene_idx.get(nb)
                if j is None:
                    continue
                delta = pos[i] - pos[j]
                dist = max(np.linalg.norm(delta), 0.01)
                force = dist * dist / k
                direction = delta / dist
                disp[i] -= direction * force
                disp[j] += direction * force

        # Apply displacement with temperature
        for i in range(n):
            norm = max(np.linalg.norm(disp[i]), 0.01)
            pos[i] += disp[i] / norm * min(norm, temperature)

        temperature *= 0.95

    return {g: (pos[gene_idx[g]][0], pos[gene_idx[g]][1]) for g in genes}
