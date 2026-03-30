"""
Generate a structured PDF analysis report for pySCENIC GRN inference.

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
# Color constants (consistent with clinicaltrials-landscape)
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
    # Cap height to avoid overflow
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
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MEDIUM_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    # Alternating row shading
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_commands.append(
                ("BACKGROUND", (0, i), (-1, i), COLOR_LIGHT_GRAY)
            )

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(style_commands))
    return tbl


def _find_figure(output_dir, filename):
    """Search for a figure in output_dir and output_dir/plots."""
    candidates = [
        os.path.join(output_dir, filename),
        os.path.join(output_dir, "plots", filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]  # Return first candidate (will show "not available")


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

def generate_report(
    regulons,
    auc_matrix,
    auc_summary,
    adjacencies=None,
    output_dir=".",
    output_file=None,
    parameters=None,
):
    """
    Generate a structured PDF analysis report for pySCENIC results.

    Parameters
    ----------
    regulons : list
        List of Regulon objects from pySCENIC.
    auc_matrix : pd.DataFrame
        AUCell activity matrix (cells x regulons).
    auc_summary : pd.DataFrame
        Summary statistics per regulon.
    adjacencies : pd.DataFrame, optional
        Raw TF-target adjacencies from GRNBoost2.
    output_dir : str
        Directory containing figures and where PDF will be saved.
    output_file : str, optional
        Full path for output PDF. Defaults to output_dir/scenic_analysis_report.pdf.
    parameters : dict, optional
        Analysis parameters to document in Methods section.

    Returns
    -------
    str or None
        Path to generated PDF, or None if reportlab unavailable.
    """
    if not HAS_REPORTLAB:
        print("   reportlab not installed - skipping PDF (markdown report available)")
        return None

    if output_file is None:
        output_file = os.path.join(output_dir, "scenic_analysis_report.pdf")

    styles = _build_styles()
    elements = []

    # Compute summary stats
    n_regulons = len(regulons)
    n_cells = auc_matrix.shape[0] if auc_matrix is not None else 0
    n_pairs = sum(len(r.genes) for r in regulons) if n_regulons > 0 else 0
    n_adjacencies = len(adjacencies) if adjacencies is not None else 0

    if n_regulons > 0:
        sizes = [len(r.genes) for r in regulons]
        mean_targets = sum(sizes) / len(sizes)
        sorted_sizes = sorted(sizes)
        median_targets = sorted_sizes[len(sorted_sizes) // 2]
    else:
        mean_targets = 0
        median_targets = 0

    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 0.8 * inch))
    elements.append(Paragraph(
        "Gene Regulatory Network<br/>Analysis Report",
        styles["ReportTitle"],
    ))
    elements.append(Paragraph(
        "pySCENIC GRN Inference Results",
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

    # Summary stat boxes
    stat_data = [
        [Paragraph(f"<b>{n_regulons}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_cells:,}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_pairs:,}</b>", styles["StatNumber"])],
        [Paragraph("Regulons", styles["StatLabel"]),
         Paragraph("Cells Analyzed", styles["StatLabel"]),
         Paragraph("TF-Target Pairs", styles["StatLabel"])],
    ]
    stat_table = Table(stat_data, colWidths=[2.2 * inch] * 3)
    stat_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Second row of stats
    stat_data2 = [
        [Paragraph(f"<b>{mean_targets:.1f}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{median_targets}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_adjacencies:,}</b>", styles["StatNumber"])],
        [Paragraph("Mean Targets/Regulon", styles["StatLabel"]),
         Paragraph("Median Targets/Regulon", styles["StatLabel"]),
         Paragraph("GRNBoost2 Edges", styles["StatLabel"])],
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
        "Gene regulatory network (GRN) inference reveals the transcription factor (TF) "
        "regulatory programs that control gene expression in individual cells. Understanding "
        "these programs is essential for identifying cell-type-specific regulators, master "
        "regulators of cell state transitions, and potential therapeutic targets.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "This analysis uses pySCENIC (Single-Cell rEgulatory Network Inference and Clustering) "
        "to infer GRNs de novo from single-cell RNA-seq expression data. Unlike approaches that "
        "rely solely on curated databases, pySCENIC discovers TF-target relationships directly "
        "from co-expression patterns and validates them using cis-regulatory motif enrichment.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "A <b>regulon</b> is a transcription factor together with its set of validated target "
        "genes &mdash; targets that are both co-expressed with the TF and contain its binding "
        "motif in their cis-regulatory regions. Each cell receives an activity score for each "
        "regulon, enabling discovery of cell-type-specific regulatory programs.",
        styles["ReportBody"],
    ))

    # ===== 2. METHODS =====
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("2. Methods", styles["SectionHeading"]))

    elements.append(Paragraph("2.1 Pipeline Overview", styles["SubHeading"]))
    elements.append(Paragraph(
        "The pySCENIC pipeline consists of three sequential steps:",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 1 &mdash; GRN Inference (GRNBoost2):</b> A gradient boosting algorithm identifies "
        "co-expression relationships between transcription factors and candidate target genes. "
        "For each TF, a regression model predicts target gene expression, yielding a ranked list "
        "of TF-target associations with importance scores.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 2 &mdash; Regulon Prediction (cisTarget):</b> Candidate TF-target associations "
        "are pruned by testing for enrichment of TF binding motifs in the cis-regulatory regions "
        "(promoters and enhancers) of target genes. Only targets with statistically significant "
        "motif enrichment are retained, producing validated regulons.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 3 &mdash; Activity Scoring (AUCell):</b> Each cell is scored for the activity "
        "of each regulon using the Area Under the recovery Curve (AUC) method. This produces a "
        "cell-by-regulon activity matrix that can be used for clustering, visualization, and "
        "differential activity analysis.",
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

    elements.append(Paragraph("3.1 Summary", styles["SubHeading"]))

    if n_regulons == 0:
        elements.append(Paragraph(
            "<b>No regulons were identified in this analysis.</b> This may indicate insufficient "
            "cell count, mismatched gene nomenclature, or database compatibility issues. "
            "See the Conclusions section for troubleshooting guidance.",
            styles["ReportBody"],
        ))
    else:
        elements.append(Paragraph(
            f"The analysis identified <b>{n_regulons} regulons</b> from "
            f"<b>{n_cells:,} cells</b>, representing {len(set(r.transcription_factor for r in regulons))} "
            f"unique transcription factors. GRNBoost2 initially detected "
            f"{n_adjacencies:,} TF-target co-expression edges, which cisTarget motif pruning "
            f"refined to {n_pairs:,} validated TF-target pairs across all regulons.",
            styles["ReportBody"],
        ))
        elements.append(Paragraph(
            f"Regulon sizes ranged from {min(sizes)} to {max(sizes)} target genes "
            f"(mean: {mean_targets:.1f}, median: {median_targets}).",
            styles["ReportBody"],
        ))

        # Top regulons by target count
        elements.append(Paragraph("3.2 Top Regulons by Target Count", styles["SubHeading"]))
        regulon_by_size = sorted(regulons, key=lambda r: len(r.genes), reverse=True)[:10]
        header = ["Rank", "Regulon", "TF", "Targets", "Mean Activity", "Std Activity"]
        rows = []
        for i, r in enumerate(regulon_by_size, 1):
            mean_act = f"{auc_matrix[r.name].mean():.4f}" if r.name in auc_matrix.columns else "N/A"
            std_act = f"{auc_matrix[r.name].std():.4f}" if r.name in auc_matrix.columns else "N/A"
            rows.append([str(i), r.name, r.transcription_factor,
                         str(len(r.genes)), mean_act, std_act])
        elements.append(_make_table(header, rows,
                                    col_widths=[0.4*inch, 1.3*inch, 1.0*inch,
                                                0.7*inch, 1.0*inch, 1.0*inch]))
        elements.append(Spacer(1, 0.15 * inch))

        # Top regulons by variance
        elements.append(Paragraph("3.3 Top Regulons by Activity Variance", styles["SubHeading"]))
        elements.append(Paragraph(
            "High-variance regulons are often the most biologically informative, as they "
            "distinguish cell types or states within the dataset.",
            styles["ReportBody"],
        ))
        regulon_vars = {r.name: auc_matrix[r.name].var()
                        for r in regulons if r.name in auc_matrix.columns}
        top_var = sorted(regulon_vars.items(), key=lambda x: x[1], reverse=True)[:10]
        rows_var = []
        for i, (name, var) in enumerate(top_var, 1):
            reg = next((r for r in regulons if r.name == name), None)
            if reg:
                rows_var.append([str(i), name, reg.transcription_factor,
                                 str(len(reg.genes)), f"{var:.5f}"])
        if rows_var:
            elements.append(_make_table(
                ["Rank", "Regulon", "TF", "Targets", "Variance"],
                rows_var,
                col_widths=[0.4*inch, 1.3*inch, 1.0*inch, 0.7*inch, 1.0*inch],
            ))
        elements.append(Spacer(1, 0.15 * inch))

        # Figures
        elements.append(Paragraph("3.4 Visualizations", styles["SubHeading"]))

        heatmap_path = _find_figure(output_dir, "regulon_heatmap.png")
        _embed_figure(elements, heatmap_path,
                      "<b>Figure 1.</b> Top regulon activities across cells (clustered heatmap). "
                      "Rows represent regulons, columns represent cells or cell types. "
                      "Color intensity reflects AUCell activity score.",
                      styles)

        elements.append(Spacer(1, 0.15 * inch))

        network_path = _find_figure(output_dir, "regulon_network.png")
        _embed_figure(elements, network_path,
                      "<b>Figure 2.</b> Gene regulatory network showing top transcription factors "
                      "(red nodes) and their target genes (blue nodes). Edge connections represent "
                      "validated TF-target regulatory relationships.",
                      styles)

    # ===== 4. CONCLUSIONS =====
    elements.append(PageBreak())
    elements.append(Paragraph("4. Conclusions", styles["SectionHeading"]))

    if n_regulons == 0:
        elements.append(Paragraph(
            "No regulons were identified. Consider the following troubleshooting steps:",
            styles["ReportBody"],
        ))
        elements.append(Paragraph(
            "&bull; Verify gene symbol nomenclature matches the TF list (HGNC for human, MGI for mouse)<br/>"
            "&bull; Ensure the dataset has 500+ cells with 2,000+ expressed genes<br/>"
            "&bull; Check that the correct species-specific cisTarget databases are used<br/>"
            "&bull; Try relaxing filtering thresholds",
            styles["ReportBody"],
        ))
    else:
        # Key findings
        top3 = sorted(regulons, key=lambda r: len(r.genes), reverse=True)[:3]
        top3_str = ", ".join(f"<b>{r.transcription_factor}</b> ({len(r.genes)} targets)"
                             for r in top3)
        elements.append(Paragraph(
            f"This analysis identified {n_regulons} regulons from {n_cells:,} cells. "
            f"The largest regulons were driven by {top3_str}.",
            styles["ReportBody"],
        ))

        # Caveats
        elements.append(Paragraph("4.1 Caveats", styles["SubHeading"]))
        elements.append(Paragraph(
            "&bull; Regulon size and composition depend on the cisTarget database coverage "
            "for the species and genome build used.<br/>"
            "&bull; Co-expression-based inference may miss regulatory relationships that do not "
            "manifest as correlated expression (e.g., repressive interactions).<br/>"
            "&bull; AUCell scores are relative within the dataset and should not be compared "
            "directly across independent analyses.<br/>"
            "&bull; Regulon identification is influenced by cell type composition and sequencing "
            "depth of the input dataset.",
            styles["ReportBody"],
        ))

        # Next steps
        elements.append(Paragraph("4.2 Suggested Next Steps", styles["SubHeading"]))
        elements.append(Paragraph(
            "&bull; <b>Validate key regulons</b> with orthogonal data (ChIP-seq, ATAC-seq, "
            "perturbation experiments).<br/>"
            "&bull; <b>Differential regulon activity</b> between conditions or cell types to "
            "identify condition-specific regulatory programs.<br/>"
            "&bull; <b>Trajectory analysis</b> with regulon dynamics to identify TFs driving "
            "cell state transitions or differentiation.<br/>"
            "&bull; <b>Functional enrichment</b> of regulon target genes to characterize "
            "biological pathways under TF control.",
            styles["ReportBody"],
        ))

    # Footer
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(HRFlowable(
        width="60%", thickness=0.5, color=COLOR_MEDIUM_GRAY,
        spaceAfter=8, spaceBefore=8,
    ))
    elements.append(Paragraph(
        f"Generated by pySCENIC Agent Skill | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
        title="pySCENIC GRN Analysis Report",
        author="pySCENIC Agent Skill",
    )
    doc.build(elements)
    print(f"✓ PDF report generated: {output_file}")
    return output_file

