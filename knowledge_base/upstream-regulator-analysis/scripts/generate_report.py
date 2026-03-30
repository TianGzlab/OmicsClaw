"""
Generate a structured PDF analysis report for upstream regulator analysis.

Creates a publication-quality PDF with Introduction, Methods, Results
(with embedded figures), and Conclusions sections using reportlab.

Requires: reportlab (pip install reportlab)
Falls back gracefully if reportlab is not installed.
"""

import os
from datetime import datetime

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, HRFlowable,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ---------------------------------------------------------------------------
# Color constants
# ---------------------------------------------------------------------------
if HAS_REPORTLAB:
    COLOR_PRIMARY = colors.HexColor("#1B4F72")
    COLOR_ACCENT = colors.HexColor("#E74C3C")
    COLOR_DARK = colors.HexColor("#2C3E50")
    COLOR_LIGHT_GRAY = colors.HexColor("#F2F3F4")
    COLOR_MEDIUM_GRAY = colors.HexColor("#BDC3C7")


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _build_styles():
    """Create custom paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=24, textColor=COLOR_PRIMARY, spaceAfter=6,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=12, textColor=COLOR_DARK, spaceAfter=20,
        alignment=TA_CENTER, fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        "SectionHeading", parent=styles["Heading1"],
        fontSize=16, textColor=COLOR_PRIMARY, spaceBefore=18,
        spaceAfter=8, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "SubHeading", parent=styles["Heading2"],
        fontSize=13, textColor=COLOR_DARK, spaceBefore=12,
        spaceAfter=6, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "ReportBody", parent=styles["Normal"],
        fontSize=10, textColor=COLOR_DARK, spaceAfter=6,
        leading=14, fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        "StatNumber", parent=styles["Normal"],
        fontSize=28, textColor=COLOR_ACCENT, alignment=TA_CENTER,
        spaceAfter=2, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "StatLabel", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_DARK, alignment=TA_CENTER,
        spaceAfter=6, fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        "FigureCaption", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_DARK, spaceAfter=12,
        leading=12, fontName="Helvetica-Oblique", alignment=TA_CENTER,
    ))

    return styles


def _embed_figure(elements, image_path, caption, styles, max_width=6.0):
    """Embed a PNG figure with caption."""
    if not os.path.exists(image_path):
        return
    img = Image(image_path)
    aspect = img.imageHeight / img.imageWidth
    img_width = min(max_width * inch, 6.5 * inch)
    img.drawWidth = img_width
    img.drawHeight = img_width * aspect
    elements.append(img)
    elements.append(Paragraph(caption, styles["FigureCaption"]))
    elements.append(Spacer(1, 8))


def _make_table(data, col_widths=None):
    """Create a styled table."""
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MEDIUM_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def generate_report(results, output_dir="regulator_results"):
    """
    Generate a PDF report for upstream regulator analysis.

    Parameters
    ----------
    results : dict
        Results from run_integration_workflow().
    output_dir : str
        Directory containing plots and where PDF will be saved.

    Returns
    -------
    str or None
        Path to generated PDF, or None if reportlab unavailable.
    """
    if not HAS_REPORTLAB:
        print("   reportlab not installed — skipping PDF report")
        return None

    output_path = os.path.join(output_dir, "analysis_report.pdf")
    styles = _build_styles()
    elements = []

    regulon_scores = results["regulon_scores"]
    parameters = results["parameters"]
    metadata = results["metadata"]

    # ---- Title Page ----
    elements.append(Spacer(1, 60))
    elements.append(Paragraph("Upstream Regulator Analysis", styles["ReportTitle"]))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["ReportSubtitle"],
    ))
    elements.append(HRFlowable(
        width="80%", thickness=2, color=COLOR_PRIMARY,
        spaceAfter=20, spaceBefore=10,
    ))

    # Summary stats
    stat_data = [
        [str(metadata["n_background"]), str(metadata["n_de_total"]),
         str(metadata["n_tfs_enriched"]), str(len(regulon_scores))],
        ["Total Genes", "DE Genes", "TFs Enriched", "TFs Scored"],
    ]
    stat_table = Table(stat_data, colWidths=[1.5 * inch] * 4)
    stat_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 22),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_ACCENT),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 9),
        ("TEXTCOLOR", (0, 1), (-1, 1), COLOR_DARK),
    ]))
    elements.append(stat_table)
    elements.append(Spacer(1, 30))

    # ---- Introduction ----
    elements.append(Paragraph("1. Introduction", styles["SectionHeading"]))
    elements.append(Paragraph(
        "This report identifies transcription factors (TFs) driving observed "
        "differential gene expression by integrating ChIP-Atlas TF binding data "
        "(epigenomics) with RNA-seq DE results (transcriptomics). TFs are ranked "
        "by a combined regulatory score incorporating binding enrichment, "
        "target-DE overlap (Fisher's exact test), and directional concordance "
        "(activator vs repressor).",
        styles["ReportBody"],
    ))
    elements.append(Spacer(1, 6))

    # ---- Methods ----
    elements.append(Paragraph("2. Methods", styles["SectionHeading"]))

    elements.append(Paragraph("2.1 Parameters", styles["SubHeading"]))
    param_data = [
        ["Parameter", "Value"],
        ["Genome", parameters["genome"]],
        ["Antigen class", parameters["antigen_class"]],
        ["Cell class", parameters["cell_class"]],
        ["Peak threshold", str(parameters["threshold"])],
        ["Target gene distance", f"\u00b1{parameters['distance_kb']}kb"],
        ["DE padj threshold", str(parameters["padj_threshold"])],
        ["DE log2FC threshold", str(parameters["log2fc_threshold"])],
        ["Max TFs investigated", str(parameters["max_tfs"])],
        ["Min target overlap", str(parameters["min_targets_overlap"])],
    ]
    elements.append(_make_table(param_data, col_widths=[2.5 * inch, 2.5 * inch]))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("2.2 Pipeline", styles["SubHeading"]))
    elements.append(Paragraph(
        "<b>Step 1:</b> DE gene lists (up/down) submitted to ChIP-Atlas Peak "
        "Enrichment API (433,000+ ChIP-seq experiments).",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 2:</b> Top enriched TFs identified; target gene lists downloaded "
        "from ChIP-Atlas.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 3:</b> Fisher's exact test for each TF (TF-bound vs not \u00d7 "
        "DE vs not-DE). Directional concordance computed.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 4:</b> Combined regulatory score = "
        "-log10(Fisher P) \u00d7 Concordance \u00d7 -log10(ChIP Q).",
        styles["ReportBody"],
    ))
    elements.append(Spacer(1, 6))

    # ---- Results ----
    elements.append(Paragraph("3. Results", styles["SectionHeading"]))

    elements.append(Paragraph("3.1 Input Summary", styles["SubHeading"]))
    elements.append(Paragraph(
        f"A total of <b>{metadata['n_background']}</b> genes were measured, of which "
        f"<b>{metadata['n_de_total']}</b> were differentially expressed "
        f"({metadata['n_de_up']} upregulated, {metadata['n_de_down']} downregulated). "
        f"ChIP-Atlas enrichment identified <b>{metadata['n_tfs_enriched']}</b> TFs, "
        f"of which <b>{metadata['n_tfs_with_targets']}</b> had target gene data and "
        f"<b>{len(regulon_scores)}</b> passed the scoring threshold.",
        styles["ReportBody"],
    ))

    # Top regulators table
    if len(regulon_scores) > 0:
        elements.append(Paragraph("3.2 Top Upstream Regulators", styles["SubHeading"]))

        table_data = [["Rank", "TF", "Dir.", "Score", "Fisher P", "Conc.", "Targets DE"]]
        for i, (_, row) in enumerate(regulon_scores.head(10).iterrows()):
            table_data.append([
                str(i + 1),
                row["tf"],
                row["direction"][:3],
                f"{row['regulatory_score']:.1f}",
                f"{row['fisher_pvalue']:.1e}",
                f"{row['concordance']:.0%}",
                f"{row['n_targets_de_total']} ({row['n_targets_de_up']}\u2191{row['n_targets_de_down']}\u2193)",
            ])

        elements.append(_make_table(
            table_data,
            col_widths=[0.5 * inch, 0.9 * inch, 0.5 * inch, 0.7 * inch,
                        0.9 * inch, 0.6 * inch, 1.2 * inch],
        ))
        elements.append(Spacer(1, 6))

        n_act = (regulon_scores["direction"] == "activator").sum()
        n_rep = (regulon_scores["direction"] == "repressor").sum()
        n_mix = (regulon_scores["direction"] == "mixed").sum()
        elements.append(Paragraph(
            f"<b>Direction summary:</b> {n_act} activators, {n_rep} repressors, {n_mix} mixed.",
            styles["ReportBody"],
        ))

    # Embed figures
    elements.append(Paragraph("3.3 Visualizations", styles["SubHeading"]))
    prefix = os.path.join(output_dir, "upstream_regulators")
    _embed_figure(elements, prefix + "_top_regulators.png",
                  "Figure 1. Top upstream regulators ranked by regulatory score.",
                  styles)
    _embed_figure(elements, prefix + "_target_overlap.png",
                  "Figure 2. TF target gene overlap with DE genes.",
                  styles)
    _embed_figure(elements, prefix + "_evidence_scatter.png",
                  "Figure 3. Evidence integration: ChIP enrichment vs Fisher significance.",
                  styles)
    _embed_figure(elements, prefix + "_heatmap.png",
                  "Figure 4. Regulatory evidence heatmap (z-scored metrics).",
                  styles)

    # ---- Conclusions ----
    elements.append(Paragraph("4. Conclusions", styles["SectionHeading"]))

    if len(regulon_scores) > 0:
        top = regulon_scores.iloc[0]
        elements.append(Paragraph(
            f"The top-ranked upstream regulator is <b>{top['tf']}</b> "
            f"(regulatory score: {top['regulatory_score']:.1f}, "
            f"classified as {top['direction']}). "
            f"A total of {len(regulon_scores)} TFs were scored as potential "
            f"upstream regulators.",
            styles["ReportBody"],
        ))
    else:
        elements.append(Paragraph(
            "No TFs passed the scoring thresholds.",
            styles["ReportBody"],
        ))

    elements.append(Paragraph("4.1 Key Caveats", styles["SubHeading"]))
    caveats = [
        "Results are biased toward well-studied TFs and cell types in ChIP-Atlas.",
        "Binding enrichment does not prove regulatory causation — validate with perturbation experiments.",
        "Activator/repressor labels assume simple regulation; context-dependent effects are not captured.",
        "The combined regulatory score is a heuristic ranking, not a formal multi-test correction.",
        "Fisher's exact test assumes gene independence, which may be violated for pathway-co-regulated targets.",
    ]
    for caveat in caveats:
        elements.append(Paragraph(f"\u2022 {caveat}", styles["ReportBody"]))

    elements.append(Paragraph("4.2 Suggested Next Steps", styles["SubHeading"]))
    next_steps = [
        "Validate binding: Examine cell-type-specific binding patterns for top TFs.",
        "Functional enrichment: Run pathway analysis on TF-target gene subsets.",
        "Literature review: Validate TF-disease associations in published literature.",
        "Perturbation: Confirm key findings with TF knockdown/overexpression experiments.",
    ]
    for step in next_steps:
        elements.append(Paragraph(f"\u2022 {step}", styles["ReportBody"]))

    # ---- References ----
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("References", styles["SectionHeading"]))
    refs = [
        "Zou Z, et al. (2024) ChIP-Atlas 3.0. Nucleic Acids Res. 52(W1):W159-W166.",
        "Oki S, et al. (2018) ChIP-Atlas. EMBO Rep. 19(12):e46255.",
        "Fisher RA (1922) On the interpretation of chi-squared. J R Stat Soc. 85(1):87-94.",
    ]
    for ref in refs:
        elements.append(Paragraph(f"\u2022 {ref}", styles["ReportBody"]))

    # ---- Build PDF ----
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    doc.build(elements)
    print(f"   8. {output_path}")

    return output_path

