"""
Narrative Synthesis Module

Analyze finding directions, identify agreements/disagreements/gaps,
infer therapeutic direction, and format narrative markdown.
"""

import re
from collections import Counter
from datetime import datetime
from typing import List, Dict


# ---------------------------------------------------------------------------
# Direction keywords for narrative synthesis
# ---------------------------------------------------------------------------

DIRECTION_KEYWORDS = {
    "negative": [
        "inhibited", "reduced", "suppressed", "attenuated", "decreased",
        "impaired", "abolished", "abrogated", "blocked", "downregulated",
        "downregulation", "diminished",
    ],
    "positive": [
        "enhanced", "increased", "promoted", "induced", "elevated",
        "restored", "potentiated", "upregulated", "upregulation",
        "activated", "stimulated",
    ],
    "neutral": [
        "demonstrated", "showed", "revealed", "observed", "identified",
        "detected", "found",
    ],
    "combination": [
        "synergistic", "synergy", "additive", "antagonistic",
        "combination", "co-treatment", "cotargeting",
    ],
}

# Critical model/endpoint types whose absence is noteworthy
CRITICAL_MODELS = {"syngeneic", "pdx"}
CRITICAL_ENDPOINTS = {"survival", "pharmacokinetics", "toxicity"}

# Therapeutic modality keywords — detect whether studies test inhibition vs activation
MODALITY_KEYWORDS = {
    "inhibition": [
        "inhibitor", "inhibition", "inhibited", "inhibit", "inhibits",
        "blocker", "blockade", "blocking", "blocked",
        "antagonist", "antagonism",
        "knockdown", "knockout", "silencing", "depletion", "degrader",
        "suppressor", "suppression",
        "siRNA", "shRNA", "CRISPR",
        "anti-", "antibody",
        "downregulation", "downregulated", "loss-of-function",
    ],
    "activation": [
        "agonist", "activator", "activation", "activating",
        "overexpression", "overexpressed", "overexpress",
        "gain-of-function", "constitutively active",
        "upregulation", "upregulated",
        "stimulation", "stimulator",
        "mimetic", "inducer",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_narrative(
    synthesis: Dict,
    experiments: List[Dict],
    results: List[Dict] = None,
    target: str = "",
) -> Dict:
    """Generate a narrative synthesis summary.

    Returns dict with structured data and formatted markdown covering
    evidence landscape, therapeutic direction, agreements, disagreements,
    and gaps.
    """
    directions = _analyze_finding_directions(experiments)
    gaps = _identify_gaps(synthesis, experiments)
    landscape = _build_landscape_summary(synthesis, experiments)
    n_papers = synthesis["total_papers"]
    agreements = _build_agreements(directions, synthesis, n_papers)
    disagreements = _build_disagreements(directions)
    combo_effects = _build_combination_summary(directions)

    # Infer therapeutic direction if abstracts and target are available
    if results and target:
        therapeutic_direction = _infer_therapeutic_direction(
            results, directions, target
        )
    else:
        therapeutic_direction = []

    narrative_md = _format_narrative_markdown(
        landscape, agreements, disagreements, combo_effects, gaps,
        therapeutic_direction
    )

    return {
        "landscape_summary": landscape,
        "agreements": agreements,
        "disagreements": disagreements,
        "combination_effects": combo_effects,
        "gaps": gaps,
        "finding_directions": directions,
        "therapeutic_direction": therapeutic_direction,
        "narrative_markdown": narrative_md,
    }


# ---------------------------------------------------------------------------
# Direction analysis
# ---------------------------------------------------------------------------

def _classify_sentence_direction(sentence: str) -> str:
    """Classify the effect direction of a finding sentence.

    Returns one of: 'negative', 'positive', 'neutral', 'combination',
    'mixed', or 'unclear'.
    """
    found = set()
    sentence_lower = sentence.lower()
    for direction, keywords in DIRECTION_KEYWORDS.items():
        for kw in keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, sentence_lower):
                found.add(direction)
                break  # one keyword per category is enough

    if not found:
        return "unclear"
    if "combination" in found:
        return "combination"
    if "negative" in found and "positive" in found:
        return "mixed"
    if "negative" in found:
        return "negative"
    if "positive" in found:
        return "positive"
    if "neutral" in found:
        return "neutral"
    return "unclear"


def _analyze_finding_directions(experiments: List[Dict]) -> Dict:
    """Analyze effect directions across all finding sentences.

    Returns dict with direction_counts, by_context breakdowns,
    and categorized sentence lists.
    """
    direction_counts = Counter()
    by_context = {
        "in_vitro": Counter(),
        "in_vivo": Counter(),
        "general": Counter(),
    }
    categorized = {
        "negative": [],
        "positive": [],
        "combination": [],
        "mixed": [],
    }

    for exp in experiments:
        pmid = exp.get("pmid", "unknown")

        for context, field in [
            ("in_vitro", "in_vitro_findings"),
            ("in_vivo", "in_vivo_findings"),
            ("general", "key_findings"),
        ]:
            findings_str = exp.get(field, "")
            if not findings_str:
                continue
            sentences = [s.strip() for s in findings_str.split("|") if s.strip()]
            for sentence in sentences:
                direction = _classify_sentence_direction(sentence)
                direction_counts[direction] += 1
                by_context[context][direction] += 1
                if direction in categorized:
                    categorized[direction].append((pmid, sentence))

    return {
        "direction_counts": dict(direction_counts),
        "by_context": {k: dict(v) for k, v in by_context.items()},
        "negative_sentences": categorized["negative"],
        "positive_sentences": categorized["positive"],
        "combination_sentences": categorized["combination"],
        "mixed_sentences": categorized["mixed"],
    }


# ---------------------------------------------------------------------------
# Gap identification
# ---------------------------------------------------------------------------

def _identify_gaps(synthesis: Dict, experiments: List[Dict]) -> List[str]:
    """Identify gaps in the preclinical evidence landscape."""
    gaps = []
    n_papers = synthesis["total_papers"]
    type_bd = synthesis["experiment_type_breakdown"]

    # Experiment type gaps
    has_in_vivo = type_bd.get("in_vivo", 0) > 0 or type_bd.get("both", 0) > 0
    has_in_vitro = type_bd.get("in_vitro", 0) > 0 or type_bd.get("both", 0) > 0

    if not has_in_vivo:
        gaps.append(
            "No in vivo studies found. All evidence is limited to in vitro "
            "experiments, which cannot assess pharmacokinetics, toxicity, or "
            "efficacy in a physiological context."
        )
    elif not has_in_vitro:
        gaps.append(
            "No in vitro studies found. Mechanistic understanding at the "
            "cellular level may be limited."
        )

    if type_bd.get("both", 0) == 0 and n_papers > 3:
        gaps.append(
            "No papers report both in vitro and in vivo experiments in the "
            "same study. Translation from cell-based to animal models is not "
            "directly demonstrated within individual studies."
        )

    # Critical model gaps
    observed_models = set(synthesis.get("animal_model_frequency", {}).keys())
    if has_in_vivo:
        model_labels = {
            "syngeneic": "syngeneic (immunocompetent) models",
            "pdx": "patient-derived xenograft (PDX) models",
        }
        model_explanations = {
            "syngeneic": (
                "Syngeneic models use immunocompetent hosts and are critical "
                "for evaluating immune-mediated mechanisms and immunotherapy "
                "combinations."
            ),
            "pdx": (
                "PDX models preserve patient tumor heterogeneity and are "
                "considered more clinically predictive than established cell "
                "line xenografts."
            ),
        }
        for model in CRITICAL_MODELS:
            if model not in observed_models:
                gaps.append(
                    f"No {model_labels[model]} reported. "
                    f"{model_explanations[model]}"
                )

    # Critical endpoint gaps
    observed_endpoints = set(synthesis.get("endpoint_frequency", {}).keys())
    if has_in_vivo:
        endpoint_labels = {
            "survival": "survival endpoints",
            "pharmacokinetics": "pharmacokinetic (PK) data",
            "toxicity": "toxicity/safety endpoints",
        }
        for ep in CRITICAL_ENDPOINTS:
            if ep not in observed_endpoints:
                gaps.append(
                    f"No {endpoint_labels[ep]} reported across in vivo studies."
                )

    # High unclassified fraction
    unclassified_pct = type_bd.get("unclassified", 0) / max(n_papers, 1) * 100
    if unclassified_pct > 40:
        gaps.append(
            f"{type_bd.get('unclassified', 0)} papers ({unclassified_pct:.0f}%) "
            "could not be classified as in vitro or in vivo. These may be "
            "reviews, computational studies, or clinical papers that passed "
            "search filters."
        )

    # Temporal recency gap
    year_dist = synthesis.get("year_distribution", {})
    if year_dist:
        years_int = sorted(int(y) for y in year_dist if y.isdigit())
        if years_int:
            max_year = max(years_int)
            current_year = datetime.now().year
            if max_year < current_year - 1:
                gaps.append(
                    f"Most recent paper is from {max_year}. No publications "
                    f"found in {current_year - 1}\u2013{current_year}, "
                    "suggesting research activity may have declined."
                )

    return gaps


# ---------------------------------------------------------------------------
# Agreement / disagreement / combination builders
# ---------------------------------------------------------------------------

def _build_landscape_summary(synthesis: Dict, experiments: List[Dict]) -> str:
    """Build a 1-2 sentence overview of the evidence landscape."""
    n = synthesis["total_papers"]
    type_bd = synthesis["experiment_type_breakdown"]

    # Year range
    years = [e.get("publication_date", "")[:4] for e in experiments]
    years = [y for y in years if y.isdigit()]
    year_range = f"{min(years)}\u2013{max(years)}" if years else "unknown period"

    # Experiment type balance
    in_vitro_total = type_bd.get("in_vitro", 0) + type_bd.get("both", 0)
    in_vivo_total = type_bd.get("in_vivo", 0) + type_bd.get("both", 0)

    if in_vitro_total > in_vivo_total * 2:
        balance = "predominantly in vitro"
    elif in_vivo_total > in_vitro_total * 2:
        balance = "predominantly in vivo"
    elif in_vitro_total > 0 and in_vivo_total > 0:
        balance = "spanning both in vitro and in vivo approaches"
    else:
        balance = "with limited experimental classification"

    n_cell_lines = len(synthesis.get("cell_line_frequency", {}))
    n_models = len(synthesis.get("animal_model_frequency", {}))

    summary = (
        f"Across {n} papers published from {year_range}, the preclinical "
        f"evidence is {balance}."
    )

    if n_cell_lines > 0 or n_models > 0:
        parts = []
        if n_cell_lines > 0:
            parts.append(f"{n_cell_lines} unique cell line(s)")
        if n_models > 0:
            parts.append(f"{n_models} animal model type(s)")
        summary += f" Studies employed {' and '.join(parts)}."

    return summary


def _build_agreements(
    directions: Dict, synthesis: Dict, n_papers: int
) -> List[str]:
    """Identify convergent findings across papers."""
    agreements = []
    dir_counts = directions["direction_counts"]

    total_classified = sum(dir_counts.values())
    if total_classified == 0:
        return [
            "Insufficient finding sentences extracted to identify "
            "convergent themes."
        ]

    neg_count = dir_counts.get("negative", 0)
    pos_count = dir_counts.get("positive", 0)

    # Strong agreement: >70% of directional sentences agree
    directional_total = neg_count + pos_count
    if directional_total > 0:
        neg_pct = neg_count / directional_total * 100
        pos_pct = pos_count / directional_total * 100

        if neg_pct >= 70 and neg_count >= 2:
            agreements.append(
                f"Findings predominantly report inhibitory/suppressive effects "
                f"({neg_count} of {directional_total} directional findings, "
                f"{neg_pct:.0f}%), suggesting convergent evidence for negative "
                f"regulation of the target pathway or disease phenotype."
            )
        elif pos_pct >= 70 and pos_count >= 2:
            agreements.append(
                f"Findings predominantly report enhancing/promoting effects "
                f"({pos_count} of {directional_total} directional findings, "
                f"{pos_pct:.0f}%), suggesting convergent evidence for positive "
                f"regulation or activation."
            )

    # Cross-context agreement (in vitro AND in vivo both same direction)
    iv_context = directions["by_context"]["in_vitro"]
    vv_context = directions["by_context"]["in_vivo"]

    if iv_context.get("negative", 0) >= 1 and vv_context.get("negative", 0) >= 1:
        agreements.append(
            "Inhibitory effects are reported in both in vitro and in vivo "
            "contexts, suggesting the observed suppression translates across "
            "experimental systems."
        )
    elif iv_context.get("positive", 0) >= 1 and vv_context.get("positive", 0) >= 1:
        agreements.append(
            "Enhancing effects are reported in both in vitro and in vivo "
            "contexts, suggesting the observed activation translates across "
            "experimental systems."
        )

    # Assay convergence: a single assay type used in >50% of papers
    assay_freq = synthesis.get("assay_frequency", {})
    if n_papers >= 3:
        for assay, count in assay_freq.items():
            if count >= n_papers * 0.5 and count >= 3:
                agreements.append(
                    f"The '{assay}' assay was used in {count} of "
                    f"{n_papers} papers, indicating a consistent "
                    f"methodological approach across studies."
                )
                break  # report only the top one

    if not agreements:
        agreements.append(
            "No strong convergence pattern detected across the extracted "
            "findings. This may reflect diverse research questions or "
            "insufficient finding sentences."
        )

    return agreements


def _build_disagreements(directions: Dict) -> List[str]:
    """Identify potential disagreements/conflicts in findings."""
    disagreements = []

    # Mixed-direction sentences
    mixed = directions.get("mixed_sentences", [])
    if len(mixed) >= 2:
        disagreements.append(
            f"{len(mixed)} finding sentence(s) contain both positive and "
            "negative effect keywords, suggesting complex or "
            "context-dependent outcomes."
        )

    # Opposing directions between in vitro vs in vivo
    iv_neg = directions["by_context"]["in_vitro"].get("negative", 0)
    iv_pos = directions["by_context"]["in_vitro"].get("positive", 0)
    vv_neg = directions["by_context"]["in_vivo"].get("negative", 0)
    vv_pos = directions["by_context"]["in_vivo"].get("positive", 0)

    if iv_neg > iv_pos and vv_pos > vv_neg and (iv_neg >= 2 or vv_pos >= 2):
        disagreements.append(
            "In vitro findings lean toward inhibitory effects while in vivo "
            "findings lean toward enhancing effects, which may indicate "
            "context-dependent mechanisms or compensatory pathways in "
            "animal models."
        )
    elif iv_pos > iv_neg and vv_neg > vv_pos and (iv_pos >= 2 or vv_neg >= 2):
        disagreements.append(
            "In vitro findings lean toward enhancing effects while in vivo "
            "findings lean toward inhibitory effects, which may reflect "
            "differences in microenvironment complexity between cell culture "
            "and animal models."
        )

    if not disagreements:
        disagreements.append(
            "No clear directional disagreements detected between studies. "
            "Note that keyword-based analysis cannot capture subtle "
            "methodological differences or contradictions in effect magnitude."
        )

    return disagreements


def _build_combination_summary(directions: Dict) -> List[str]:
    """Summarize combination/synergy findings if present."""
    combo = directions.get("combination_sentences", [])
    if not combo:
        return []

    summaries = [
        f"{len(combo)} finding(s) describe combination or synergistic effects:"
    ]
    for pmid, sentence in combo[:3]:
        display = sentence if len(sentence) <= 200 else sentence[:197] + "..."
        summaries.append(f"  - [{pmid}] {display}")

    return summaries


# ---------------------------------------------------------------------------
# Therapeutic direction inference
# ---------------------------------------------------------------------------

def _infer_therapeutic_direction(
    results: List[Dict],
    directions: Dict,
    target: str,
) -> List[str]:
    """Infer which direction the target should be therapeutically perturbed.

    Analyzes:
    1. What modality most papers test (inhibitors vs activators)
    2. Whether the tested modality produces beneficial outcomes
    3. Produces a reasoned statement about therapeutic direction
    """
    statements = []

    # Count modality keywords across all abstracts + titles
    inhibition_count = 0
    activation_count = 0

    for paper in results:
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        for kw in MODALITY_KEYWORDS["inhibition"]:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', text):
                inhibition_count += 1
                break  # one match per paper per modality
        for kw in MODALITY_KEYWORDS["activation"]:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', text):
                activation_count += 1
                break

    total_modality = inhibition_count + activation_count
    if total_modality == 0:
        statements.append(
            f"Insufficient modality information to determine therapeutic "
            f"direction for {target}. Abstracts did not contain clear "
            f"inhibitor/activator terminology."
        )
        return statements

    # Determine dominant modality tested
    dir_counts = directions["direction_counts"]
    neg_count = dir_counts.get("negative", 0)
    pos_count = dir_counts.get("positive", 0)
    directional_total = neg_count + pos_count

    if inhibition_count > activation_count:
        modality_statement = (
            f"{inhibition_count} of {len(results)} papers test inhibition "
            f"or blockade of {target}"
        )

        if directional_total > 0 and neg_count / directional_total >= 0.5:
            statements.append(
                f"**Inhibit {target}.** {modality_statement}, and findings "
                f"predominantly report anti-tumor effects (reduced growth, "
                f"suppressed proliferation, induced apoptosis). This suggests "
                f"{target} inhibition is the therapeutically productive "
                f"direction."
            )
        elif directional_total > 0 and pos_count / directional_total >= 0.5:
            statements.append(
                f"**Inhibit {target}.** {modality_statement}, and findings "
                f"report beneficial activating effects (enhanced immune "
                f"response, increased sensitivity, restored function). "
                f"This suggests {target} blockade produces therapeutically "
                f"desirable activation of anti-tumor mechanisms."
            )
        else:
            statements.append(
                f"**Likely inhibit {target}.** {modality_statement}, though "
                f"finding directions are mixed. The dominant research focus "
                f"on inhibition suggests this is the primary therapeutic "
                f"hypothesis, but results may be context-dependent."
            )

    elif activation_count > inhibition_count:
        modality_statement = (
            f"{activation_count} of {len(results)} papers test activation "
            f"or overexpression of {target}"
        )

        if directional_total > 0 and neg_count / directional_total >= 0.5:
            statements.append(
                f"**Activate {target}.** {modality_statement}, and findings "
                f"predominantly report suppressive effects on disease "
                f"phenotype (reduced growth, inhibited progression). This "
                f"suggests {target} activation is therapeutically productive."
            )
        elif directional_total > 0 and pos_count / directional_total >= 0.5:
            statements.append(
                f"**Activate {target}.** {modality_statement}, and findings "
                f"report enhanced anti-tumor activity or restored function. "
                f"This supports {target} activation as the therapeutic "
                f"direction."
            )
        else:
            statements.append(
                f"**Likely activate {target}.** {modality_statement}, though "
                f"finding directions are mixed. Further investigation is "
                f"needed to confirm therapeutic benefit."
            )

    else:
        # Equal inhibition and activation — ambiguous
        statements.append(
            f"Evidence is split between inhibition ({inhibition_count} papers) "
            f"and activation ({activation_count} papers) of {target}. "
            f"The therapeutic direction may be context-dependent (e.g., "
            f"tumor type, genetic background, combination partners)."
        )

    # Add supporting evidence line
    if activation_count > 0 and inhibition_count > 0:
        statements.append(
            f"Modality breakdown: {inhibition_count} papers test "
            f"inhibition/blockade, {activation_count} test "
            f"activation/overexpression."
        )

    return statements


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def _format_narrative_markdown(
    landscape: str,
    agreements: List[str],
    disagreements: List[str],
    combo_effects: List[str],
    gaps: List[str],
    therapeutic_direction: List[str],
) -> str:
    """Format the narrative synthesis as a markdown section."""
    md = "## Narrative Synthesis\n\n"

    md += "### Evidence Landscape\n\n"
    md += f"{landscape}\n\n"

    if therapeutic_direction:
        md += "### Therapeutic Direction\n\n"
        for item in therapeutic_direction:
            md += f"- {item}\n"
        md += "\n"

    md += "### Convergent Findings\n\n"
    for item in agreements:
        md += f"- {item}\n"
    md += "\n"

    md += "### Divergent Findings\n\n"
    for item in disagreements:
        md += f"- {item}\n"
    md += "\n"

    if combo_effects:
        md += "### Combination Effects\n\n"
        for item in combo_effects:
            md += f"{item}\n"
        md += "\n"

    md += "### Evidence Gaps\n\n"
    if gaps:
        for item in gaps:
            md += f"- {item}\n"
    else:
        md += "- No major evidence gaps identified.\n"
    md += "\n"

    return md

