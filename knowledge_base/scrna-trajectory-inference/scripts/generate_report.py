"""
Generate a structured PDF analysis report for trajectory inference.

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


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

def generate_report(adata, results, output_dir=".", output_file=None):
    """
    Generate a structured PDF analysis report for trajectory results.

    Parameters
    ----------
    adata : AnnData
        AnnData with trajectory analysis results.
    results : dict
        Output from run_trajectory().
    output_dir : str
        Directory containing figures and where PDF will be saved.
    output_file : str, optional
        Full path for output PDF.

    Returns
    -------
    str or None
        Path to generated PDF, or None if reportlab unavailable.
    """
    if not HAS_REPORTLAB:
        print("   reportlab not installed — skipping PDF (markdown report available)")
        return None

    if output_file is None:
        output_file = os.path.join(output_dir, "trajectory_analysis_report.pdf")

    styles = _build_styles()
    elements = []

    # Compute summary stats
    n_cells = adata.n_obs
    n_genes = adata.n_vars
    pseudotime = results.get("pseudotime")
    traj_genes = results.get("trajectory_genes")
    n_traj_genes = len(traj_genes) if traj_genes is not None else 0
    params = results.get("parameters", {})
    has_velocity = results.get("velocity_results") is not None
    has_cellrank = results.get("cellrank_results") is not None

    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 0.8 * inch))
    elements.append(Paragraph(
        "Single-Cell Trajectory<br/>Analysis Report",
        styles["ReportTitle"],
    ))
    elements.append(Paragraph(
        "PAGA + Diffusion Pseudotime"
        + (" + RNA Velocity" if has_velocity else "")
        + (" + CellRank" if has_cellrank else ""),
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
        [Paragraph(f"<b>{n_cells:,}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_traj_genes}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{'Yes' if has_velocity else 'No'}</b>", styles["StatNumber"])],
        [Paragraph("Cells Analyzed", styles["StatLabel"]),
         Paragraph("Trajectory Genes", styles["StatLabel"]),
         Paragraph("RNA Velocity", styles["StatLabel"])],
    ]
    stat_table = Table(stat_data, colWidths=[2.2 * inch] * 3)
    stat_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table)

    # ===== 1. INTRODUCTION =====
    elements.append(PageBreak())
    elements.append(Paragraph("1. Introduction", styles["SectionHeading"]))
    elements.append(Paragraph(
        "Trajectory inference reconstructs the dynamic processes underlying single-cell "
        "RNA-seq data, such as cellular differentiation, disease progression, or immune "
        "response. By ordering cells along a pseudotemporal axis, trajectory analysis "
        "reveals the sequence of transcriptional changes that drive cell state transitions.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "This analysis uses partition-based graph abstraction (PAGA) to identify the global "
        "topology of cell state transitions, combined with diffusion pseudotime (DPT) to "
        "order cells along the inferred trajectory. PAGA provides a coarse-grained map of "
        "cluster connectivity, while DPT assigns continuous pseudotime values based on "
        "diffusion distances from a user-specified root cell.",
        styles["ReportBody"],
    ))
    if has_velocity:
        elements.append(Paragraph(
            "RNA velocity analysis (scVelo) provides an independent estimate of cell "
            "state transitions by modeling the ratio of unspliced to spliced mRNA, "
            "predicting the future transcriptional state of each cell.",
            styles["ReportBody"],
        ))
    if has_cellrank:
        elements.append(Paragraph(
            "CellRank extends trajectory analysis by computing cell fate probabilities, "
            "identifying terminal states, and discovering driver genes that govern "
            "lineage commitment decisions.",
            styles["ReportBody"],
        ))

    # ===== 2. METHODS =====
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("2. Methods", styles["SectionHeading"]))

    elements.append(Paragraph("2.1 Pipeline Overview", styles["SubHeading"]))
    elements.append(Paragraph(
        "<b>Step 1 &mdash; PAGA:</b> Partition-based graph abstraction identifies "
        "statistically significant connections between cell clusters, providing a "
        "topology of cell state transitions.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 2 &mdash; Diffusion Pseudotime:</b> Cells are ordered along a "
        "continuous pseudotime axis using diffusion distances from the root cell. "
        "The root cell type for this analysis was set to "
        f"<b>{params.get('root_cell_type', 'auto')}</b>.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 3 &mdash; Gene Dynamics:</b> Spearman rank correlation identifies "
        "genes whose expression significantly changes along pseudotime (FDR &lt; 0.05).",
        styles["ReportBody"],
    ))

    # Parameters table
    elements.append(Paragraph("2.2 Parameters", styles["SubHeading"]))
    param_rows = [[str(k), str(v)] for k, v in params.items()]
    elements.append(_make_table(
        ["Parameter", "Value"], param_rows,
        col_widths=[2.5 * inch, 4.0 * inch],
    ))

    # ===== 3. RESULTS =====
    elements.append(PageBreak())
    elements.append(Paragraph("3. Results", styles["SectionHeading"]))

    elements.append(Paragraph("3.1 Trajectory Overview", styles["SubHeading"]))
    if pseudotime is not None:
        import numpy as np
        valid_pt = pseudotime[~np.isinf(pseudotime)]
        elements.append(Paragraph(
            f"Diffusion pseudotime was computed for <b>{n_cells:,}</b> cells, "
            f"with values ranging from <b>{valid_pt.min():.3f}</b> to "
            f"<b>{valid_pt.max():.3f}</b>. "
            f"A total of <b>{n_traj_genes}</b> genes showed significant correlation "
            f"with pseudotime (FDR &lt; 0.05).",
            styles["ReportBody"],
        ))

    # Embed figures
    elements.append(Paragraph("3.2 Visualizations", styles["SubHeading"]))

    _embed_figure(elements,
                  os.path.join(output_dir, "pseudotime_umap.png"),
                  "<b>Figure 1.</b> UMAP colored by diffusion pseudotime (left) "
                  "and cell type annotations (right).",
                  styles)
    elements.append(Spacer(1, 0.15 * inch))

    _embed_figure(elements,
                  os.path.join(output_dir, "paga_graph.png"),
                  "<b>Figure 2.</b> PAGA cluster connectivity graph (left) "
                  "and PAGA-initialized UMAP (right).",
                  styles)
    elements.append(Spacer(1, 0.15 * inch))

    _embed_figure(elements,
                  os.path.join(output_dir, "gene_heatmap.png"),
                  "<b>Figure 3.</b> Heatmap of top trajectory-associated genes. "
                  "Cells ordered by pseudotime (columns), genes clustered by "
                  "expression pattern (rows). Color = Z-score.",
                  styles)

    if has_velocity:
        elements.append(PageBreak())
        elements.append(Paragraph("3.3 RNA Velocity", styles["SubHeading"]))

        vel = results["velocity_results"]
        elements.append(Paragraph(
            f"RNA velocity was computed using the <b>{vel.get('model', 'stochastic')}</b> "
            f"model. Velocity streamlines show the predicted direction of cell state "
            f"transitions on the UMAP embedding.",
            styles["ReportBody"],
        ))

        _embed_figure(elements,
                      os.path.join(output_dir, "velocity_stream.png"),
                      "<b>Figure 4.</b> RNA velocity stream plot. Arrows indicate "
                      "predicted direction of cell state transitions.",
                      styles)

    if has_cellrank:
        elements.append(PageBreak())
        elements.append(Paragraph("3.4 Cell Fate Mapping", styles["SubHeading"]))

        cr = results["cellrank_results"]
        states = cr.get("terminal_states", [])
        elements.append(Paragraph(
            f"CellRank identified <b>{len(states)}</b> terminal states: "
            f"<b>{', '.join(states)}</b>. Fate probabilities were computed for "
            f"each cell, quantifying commitment towards each terminal fate.",
            styles["ReportBody"],
        ))

        _embed_figure(elements,
                      os.path.join(output_dir, "fate_probabilities.png"),
                      "<b>Figure 5.</b> Cell fate probabilities on UMAP. "
                      "Each panel shows probability of commitment to a terminal state.",
                      styles)

    # Top trajectory genes table
    if traj_genes is not None and len(traj_genes) > 0:
        elements.append(Paragraph("3.5 Top Trajectory Genes", styles["SubHeading"]))
        header = ["Rank", "Gene", "Correlation", "FDR", "Direction"]
        rows = []
        for i, (_, row) in enumerate(traj_genes.head(15).iterrows(), 1):
            rows.append([
                str(i), str(row["gene"]),
                f"{row['correlation']:.3f}", f"{row['fdr']:.2e}",
                str(row["direction"]),
            ])
        elements.append(_make_table(
            header, rows,
            col_widths=[0.4*inch, 1.5*inch, 1.0*inch, 1.0*inch, 0.8*inch],
        ))

    # ===== 4. CONCLUSIONS =====
    elements.append(PageBreak())
    elements.append(Paragraph("4. Conclusions", styles["SectionHeading"]))

    elements.append(Paragraph(
        f"Trajectory analysis of {n_cells:,} cells identified {n_traj_genes} genes "
        f"with significant expression dynamics along pseudotime. "
        f"The PAGA-based trajectory reveals the differentiation landscape connecting "
        f"the identified cell populations.",
        styles["ReportBody"],
    ))

    elements.append(Paragraph("4.1 Caveats", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; Pseudotime ordering depends on the choice of root cell and may not "
        "reflect actual chronological time.<br/>"
        "&bull; Trajectory inference assumes continuous state transitions; discrete "
        "state changes may not be well captured.<br/>"
        "&bull; Gene-pseudotime correlations may reflect composition effects rather "
        "than true temporal dynamics.",
        styles["ReportBody"],
    ))

    elements.append(Paragraph("4.2 Suggested Next Steps", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; <b>Functional enrichment</b> of trajectory genes to identify pathways "
        "driving differentiation.<br/>"
        "&bull; <b>Transcription factor activity</b> analysis along pseudotime.<br/>"
        "&bull; <b>Gene regulatory network</b> inference with pySCENIC using trajectory "
        "gene sets.<br/>"
        "&bull; <b>Differential dynamics</b> between conditions or patients.",
        styles["ReportBody"],
    ))

    # Footer
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(HRFlowable(
        width="60%", thickness=0.5, color=COLOR_MEDIUM_GRAY,
        spaceAfter=8, spaceBefore=8,
    ))
    elements.append(Paragraph(
        f"Generated by Trajectory Inference Agent Skill | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
        title="Single-Cell Trajectory Analysis Report",
        author="Trajectory Inference Agent Skill",
    )
    doc.build(elements)
    print(f"✓ PDF report generated: {output_file}")
    return output_file

