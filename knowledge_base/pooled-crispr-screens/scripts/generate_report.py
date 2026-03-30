"""
Generate a structured PDF analysis report for pooled CRISPR screen analysis.

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
        Image, PageBreak, HRFlowable,
    )
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


# ---------------------------------------------------------------------------
# Color constants (project standard)
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
        spaceAfter=8, fontName="Helvetica",
    ))
    styles.add(ParagraphStyle(
        "FigureCaption", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_DARK, alignment=TA_CENTER,
        spaceAfter=12, fontName="Helvetica-Oblique",
    ))
    styles.add(ParagraphStyle(
        "FooterText", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_MEDIUM_GRAY, alignment=TA_CENTER,
        fontName="Helvetica",
    ))
    return styles


# ---------------------------------------------------------------------------
# Component helpers
# ---------------------------------------------------------------------------

def _embed_figure(elements, image_path, caption, styles, max_width=6.0):
    """Embed a PNG figure if it exists, with caption."""
    if not os.path.exists(image_path):
        elements.append(Paragraph(
            f"<i>[Figure not available: {os.path.basename(image_path)}]</i>",
            styles["ReportBody"],
        ))
        return

    img = Image(image_path)
    aspect = img.imageHeight / img.imageWidth
    img_width = min(max_width * inch, 6.5 * inch)
    img_height = img_width * aspect
    max_height = 5.0 * inch
    if img_height > max_height:
        img_height = max_height
        img_width = img_height / aspect
    img.drawWidth = img_width
    img.drawHeight = img_height
    elements.append(img)
    elements.append(Paragraph(caption, styles["FigureCaption"]))


def _make_table(header, rows, col_widths=None):
    """Create a styled table with header row and alternating shading."""
    data = [header] + rows
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MEDIUM_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_commands.append(
                ("BACKGROUND", (0, i), (-1, i), COLOR_LIGHT_GRAY)
            )

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(style_commands))
    return tbl


def _find_figure(output_dir, filename):
    """Search for a figure in output_dir, output_dir/figures, and output_dir/plots."""
    candidates = [
        os.path.join(output_dir, filename),
        os.path.join(output_dir, "figures", filename),
        os.path.join(output_dir, "plots", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

def generate_report(
    adata=None,
    perturbation_summary=None,
    de_results=None,
    validation_df=None,
    output_dir="results",
    output_file=None,
    parameters=None,
):
    """
    Generate a structured PDF analysis report for pooled CRISPR screen results.

    Parameters
    ----------
    adata : AnnData, optional
        Processed AnnData object (for cell/gene counts).
    perturbation_summary : DataFrame, optional
        Per-perturbation summary with hit calling results.
    de_results : dict, optional
        Dictionary mapping perturbation -> DE results DataFrame.
    validation_df : DataFrame, optional
        Target validation results.
    output_dir : str
        Directory containing figures and where PDF will be saved.
    output_file : str, optional
        Full path for output PDF. Defaults to output_dir/crispr_screen_report.pdf.
    parameters : dict, optional
        Analysis parameters to document in Methods section.

    Returns
    -------
    str or None
        Path to generated PDF, or None if reportlab unavailable.
    """
    if not HAS_REPORTLAB:
        print("   reportlab not installed - skipping PDF (text report available)")
        return None

    if output_file is None:
        output_file = os.path.join(output_dir, "crispr_screen_report.pdf")

    styles = _build_styles()
    elements = []

    # Compute summary stats
    n_cells = adata.n_obs if adata is not None else 0
    n_genes = adata.n_vars if adata is not None else 0
    n_perturbations = 0
    n_hits = 0
    hit_rate = 0.0

    if perturbation_summary is not None and len(perturbation_summary) > 0:
        n_perturbations = len(perturbation_summary)
        if 'is_hit' in perturbation_summary.columns:
            n_hits = int(perturbation_summary['is_hit'].sum())
            hit_rate = n_hits / n_perturbations * 100

    n_de_perturbations = len(de_results) if de_results else 0
    mean_de_genes = 0.0
    if de_results and perturbation_summary is not None and 'n_de_genes' in perturbation_summary.columns:
        mean_de_genes = perturbation_summary['n_de_genes'].mean()

    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 0.8 * inch))
    elements.append(Paragraph(
        "Pooled CRISPR Screen<br/>Analysis Report",
        styles["ReportTitle"],
    ))
    elements.append(Paragraph(
        "Perturb-seq / CROP-seq Tiered Workflow Results",
        styles["ReportSubtitle"],
    ))
    elements.append(Paragraph(
        datetime.now().strftime("%B %d, %Y"),
        styles["ReportSubtitle"],
    ))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(HRFlowable(
        width="80%", thickness=1, color=COLOR_PRIMARY,
        spaceAfter=20, spaceBefore=10,
    ))

    # Summary stat boxes - row 1
    stat_data = [
        [Paragraph(f"<b>{n_cells:,}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_perturbations}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_hits}</b>", styles["StatNumber"])],
        [Paragraph("Cells Analyzed", styles["StatLabel"]),
         Paragraph("Perturbations Tested", styles["StatLabel"]),
         Paragraph("Validated Hits", styles["StatLabel"])],
    ]
    stat_table = Table(stat_data, colWidths=[2.2 * inch] * 3)
    stat_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Summary stat boxes - row 2
    stat_data2 = [
        [Paragraph(f"<b>{hit_rate:.1f}%</b>", styles["StatNumber"]),
         Paragraph(f"<b>{mean_de_genes:.0f}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_genes:,}</b>", styles["StatNumber"])],
        [Paragraph("Hit Rate", styles["StatLabel"]),
         Paragraph("Mean DE Genes/Hit", styles["StatLabel"]),
         Paragraph("Genes Measured", styles["StatLabel"])],
    ]
    stat_table2 = Table(stat_data2, colWidths=[2.2 * inch] * 3)
    stat_table2.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table2)

    # ===== 1. INTRODUCTION =====
    elements.append(PageBreak())
    elements.append(Paragraph("1. Introduction", styles["SectionHeading"]))
    elements.append(Paragraph(
        "Pooled CRISPR screens with single-cell RNA-seq readout (Perturb-seq, CROP-seq) "
        "enable systematic interrogation of gene function at scale. By introducing unique "
        "sgRNA perturbations across a pool of cells and profiling their transcriptomes, "
        "these screens identify genes whose loss or gain of function produces measurable "
        "transcriptional phenotypes.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "This analysis uses a tiered workflow to efficiently process screen data: "
        "(1) fast t-test screening to identify preliminary hits, "
        "(2) target gene validation to confirm on-target effects, and "
        "(3) rigorous batch-corrected differential expression (glmGamPoi) for top hits. "
        "This approach balances computational efficiency with statistical rigor.",
        styles["ReportBody"],
    ))

    # ===== 2. METHODS =====
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("2. Methods", styles["SectionHeading"]))

    elements.append(Paragraph("2.1 Pipeline Overview", styles["SubHeading"]))
    elements.append(Paragraph(
        "The analysis follows a three-tier approach:",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Tier 1 &mdash; Fast Screening (t-test):</b> For each perturbation, a t-test "
        "compares perturbed cells against non-targeting controls across all genes. "
        "Preliminary hits are called based on the number of differentially expressed genes "
        "exceeding a minimum threshold.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Tier 2 &mdash; Target Validation:</b> Preliminary hits are validated by checking "
        "whether the target gene itself shows the expected expression change (downregulation "
        "for CRISPRi/ko, upregulation for CRISPRa). This filters out perturbations that "
        "produce transcriptional changes without on-target effects.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Tier 3 &mdash; Rigorous DE (glmGamPoi):</b> Validated hits are re-analyzed "
        "using glmGamPoi, a negative binomial model that accounts for batch effects and "
        "donor-level variability. This provides publication-quality DE results for top hits.",
        styles["ReportBody"],
    ))

    if parameters:
        elements.append(Paragraph("2.2 Parameters", styles["SubHeading"]))
        param_header = ["Parameter", "Value"]
        param_rows = [[str(k), str(v)] for k, v in parameters.items()]
        elements.append(_make_table(param_header, param_rows,
                                    col_widths=[2.5 * inch, 4.0 * inch]))
        elements.append(Spacer(1, 0.1 * inch))

    # ===== 3. RESULTS =====
    elements.append(PageBreak())
    elements.append(Paragraph("3. Results", styles["SectionHeading"]))

    elements.append(Paragraph("3.1 Summary Statistics", styles["SubHeading"]))

    if n_perturbations == 0:
        elements.append(Paragraph(
            "<b>No perturbation results available.</b> Check that screening completed "
            "successfully and that perturbation summary data was provided.",
            styles["ReportBody"],
        ))
    else:
        elements.append(Paragraph(
            f"Screening tested <b>{n_perturbations} perturbations</b> across "
            f"<b>{n_cells:,} cells</b>, identifying <b>{n_hits} validated hits</b> "
            f"({hit_rate:.1f}% hit rate).",
            styles["ReportBody"],
        ))

        # Top hits table
        elements.append(Paragraph("3.2 Top Hits", styles["SubHeading"]))
        if 'is_hit' in perturbation_summary.columns:
            hits = perturbation_summary[perturbation_summary['is_hit']].copy()
        else:
            hits = perturbation_summary.copy()

        sort_col = 'outlier_fraction' if 'outlier_fraction' in hits.columns else hits.columns[0]
        top_hits = hits.nlargest(10, sort_col) if len(hits) > 0 else hits.head(10)

        if len(top_hits) > 0:
            header = ["Rank", "Perturbation", "Outlier Frac.", "DE Genes"]
            rows = []
            for i, (_, row) in enumerate(top_hits.iterrows(), 1):
                gene = str(row.get('gene', row.get('perturbation', 'N/A')))
                of = f"{row['outlier_fraction']:.1%}" if 'outlier_fraction' in row.index else "N/A"
                ndeg = str(int(row['n_de_genes'])) if 'n_de_genes' in row.index else "N/A"
                rows.append([str(i), gene, of, ndeg])
            elements.append(_make_table(header, rows,
                                        col_widths=[0.5*inch, 2.5*inch, 1.2*inch, 1.2*inch]))
            elements.append(Spacer(1, 0.15 * inch))

        # Validation summary
        if validation_df is not None and len(validation_df) > 0:
            elements.append(Paragraph("3.3 Target Validation", styles["SubHeading"]))
            n_validated = int(validation_df['target_affected'].sum()) if 'target_affected' in validation_df.columns else 0
            n_tested_val = len(validation_df)
            elements.append(Paragraph(
                f"Target validation confirmed on-target effects for <b>{n_validated}/{n_tested_val}</b> "
                f"perturbations ({n_validated/n_tested_val*100:.1f}% validation rate).",
                styles["ReportBody"],
            ))

        # Figures
        elements.append(Paragraph("3.4 Visualizations", styles["SubHeading"]))

        hit_summary_path = _find_figure(output_dir, "hit_summary.png")
        _embed_figure(elements, hit_summary_path,
                      "<b>Figure 1.</b> Hit summary showing top perturbations by outlier fraction "
                      "(left) and DE genes vs outlier cells (right).",
                      styles)

        elements.append(Spacer(1, 0.15 * inch))

        # Try to embed top volcano plots
        if top_hits is not None and len(top_hits) > 0:
            top_gene = str(top_hits.iloc[0].get('gene', top_hits.iloc[0].get('perturbation', '')))
            if top_gene:
                volcano_path = _find_figure(output_dir, f"volcano_{top_gene}.png")
                _embed_figure(elements, volcano_path,
                              f"<b>Figure 2.</b> Volcano plot for top hit: {top_gene}. "
                              "Red points indicate significantly differentially expressed genes.",
                              styles)

    # ===== 4. CONCLUSIONS =====
    elements.append(PageBreak())
    elements.append(Paragraph("4. Conclusions", styles["SectionHeading"]))

    if n_hits > 0:
        elements.append(Paragraph(
            f"This pooled CRISPR screen identified <b>{n_hits} validated hits</b> from "
            f"{n_perturbations} perturbations ({hit_rate:.1f}% hit rate). These hits "
            "showed both significant transcriptional changes and confirmed on-target effects.",
            styles["ReportBody"],
        ))
    else:
        elements.append(Paragraph(
            "No validated hits were identified. This may indicate weak perturbation effects, "
            "insufficient cell numbers per perturbation, or overly stringent thresholds.",
            styles["ReportBody"],
        ))

    # Caveats
    elements.append(Paragraph("4.1 Caveats", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; sgRNA efficiency varies; some perturbations may have incomplete knockdown "
        "or activation, leading to false negatives.<br/>"
        "&bull; High MOI screens may have cells with multiple perturbations, complicating "
        "interpretation of individual gene effects.<br/>"
        "&bull; Compensatory mechanisms (paralog buffering, feedback loops) can mask "
        "perturbation effects at the transcriptional level.<br/>"
        "&bull; Hit calling thresholds (min DE genes, outlier fraction) affect sensitivity "
        "and specificity of the final hit list.",
        styles["ReportBody"],
    ))

    # Next steps
    elements.append(Paragraph("4.2 Suggested Next Steps", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; <b>Pathway enrichment</b> on hit perturbation DE genes to identify "
        "affected biological processes.<br/>"
        "&bull; <b>Gene regulatory network analysis</b> from perturbed cell populations "
        "to map regulatory relationships.<br/>"
        "&bull; <b>Cluster perturbations</b> by transcriptional signature to identify "
        "functional groups of genes.<br/>"
        "&bull; <b>Validate top hits</b> with orthogonal assays (qPCR, Western blot, "
        "arrayed follow-up screens).",
        styles["ReportBody"],
    ))

    # Footer
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(HRFlowable(
        width="60%", thickness=0.5, color=COLOR_MEDIUM_GRAY,
        spaceAfter=8, spaceBefore=8,
    ))
    elements.append(Paragraph(
        f"Generated by Pooled CRISPR Screen Agent Skill | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["FooterText"],
    ))

    # ===== BUILD PDF =====
    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Pooled CRISPR Screen Analysis Report",
        author="Pooled CRISPR Screen Agent Skill",
    )
    doc.build(elements)
    print(f"  Saved: {os.path.basename(output_file)}")
    return output_file

