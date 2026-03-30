"""
Generate a structured PDF analysis report for disease progression trajectory analysis.

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

def generate_report(data, metadata, results, output_dir=".", output_file=None):
    """
    Generate a structured PDF analysis report for trajectory results.

    Parameters
    ----------
    data : pd.DataFrame
        Preprocessed data matrix (features x samples).
    metadata : pd.DataFrame
        Sample metadata.
    results : dict
        Output from run_trajectory_analysis().
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
        output_file = os.path.join(output_dir, "analysis_report.pdf")

    styles = _build_styles()
    elements = []

    # Compute summary stats
    n_samples = data.shape[1]
    n_features = data.shape[0]
    n_patients = metadata['patient_id'].nunique() if 'patient_id' in metadata.columns else 0
    pseudotime = results.get('pseudotime')
    trajectory_features = results.get('trajectory_features')
    n_traj_features = len(trajectory_features) if trajectory_features is not None else 0
    monotonicity = results.get('monotonicity_score')
    robustness = results.get('robustness_score')
    method = results.get('method', 'timeax')

    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 0.8 * inch))
    elements.append(Paragraph(
        "Disease Progression<br/>Trajectory Analysis Report",
        styles["ReportTitle"],
    ))
    elements.append(Paragraph(
        f"TimeAx Multiple Trajectory Alignment",
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
    mono_str = f"{monotonicity:.2f}" if monotonicity is not None else "N/A"
    stat_data = [
        [Paragraph(f"<b>{n_patients}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_samples}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_traj_features}</b>", styles["StatNumber"])],
        [Paragraph("Patients", styles["StatLabel"]),
         Paragraph("Samples", styles["StatLabel"]),
         Paragraph("Trajectory Features", styles["StatLabel"])],
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
        [Paragraph(f"<b>{n_features:,}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{mono_str}</b>", styles["StatNumber"])],
        [Paragraph("Genes Analyzed", styles["StatLabel"]),
         Paragraph("Monotonicity Score", styles["StatLabel"])],
    ]
    stat_table2 = Table(stat_data2, colWidths=[3.3 * inch] * 2)
    stat_table2.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table2)

    # ===== 1. INTRODUCTION =====
    elements.append(PageBreak())
    elements.append(Paragraph("1. Introduction", styles["SectionHeading"]))
    elements.append(Paragraph(
        "Disease progression analysis reconstructs the molecular timeline of disease "
        "from longitudinal patient omics data. By aligning multiple patient trajectories "
        "into a consensus disease pseudotime, this approach reveals the sequence of "
        "molecular changes driving disease evolution and enables patient stratification "
        "by progression rate.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "This analysis uses <b>TimeAx</b> (Frishberg et al., <i>Nat Commun</i> 2023), "
        "a multiple trajectory alignment algorithm that handles irregular sampling "
        "patterns across patients. TimeAx identifies conserved seed features with "
        "coordinated dynamics, then iteratively aligns patient trajectories to build "
        "a consensus disease progression model.",
        styles["ReportBody"],
    ))

    # ===== 2. METHODS =====
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("2. Methods", styles["SectionHeading"]))

    elements.append(Paragraph("2.1 Pipeline Overview", styles["SubHeading"]))
    elements.append(Paragraph(
        "<b>Step 1 &mdash; Data Loading:</b> Expression data and sample metadata "
        "are loaded, validated, and filtered. Features with low variance are removed "
        "and data quality is assessed.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 2 &mdash; TimeAx Trajectory Alignment:</b> The algorithm selects "
        "seed features with coordinated temporal dynamics, then iteratively aligns "
        "patient trajectories to build a consensus model. Each sample receives a "
        "disease pseudotime value and uncertainty score.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 3 &mdash; Feature Identification:</b> Polynomial regression "
        "(linear, quadratic, cubic) identifies features with significant expression "
        "changes along pseudotime, with FDR correction for multiple testing.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "<b>Step 4 &mdash; Export:</b> All results, model objects, and visualizations "
        "are exported for downstream analysis and reporting.",
        styles["ReportBody"],
    ))

    # Parameters table
    elements.append(Paragraph("2.2 Parameters", styles["SubHeading"]))
    seed_features = results.get('seed_features', [])
    param_rows = [
        ["Method", method.upper()],
        ["Patients", str(n_patients)],
        ["Samples", str(n_samples)],
        ["Features analyzed", f"{n_features:,}"],
        ["Seed features", str(len(seed_features)) if seed_features else "N/A"],
        ["Monotonicity score", mono_str],
        ["LOO robustness", f"{robustness:.3f}" if robustness is not None else "N/A"],
    ]
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
        elements.append(Paragraph(
            f"TimeAx successfully computed disease pseudotime for <b>{n_samples}</b> "
            f"samples from <b>{n_patients}</b> patients, with values ranging from "
            f"<b>{pseudotime.min():.3f}</b> to <b>{pseudotime.max():.3f}</b>. "
            f"The within-patient monotonicity score of <b>{mono_str}</b> indicates "
            f"{'good' if monotonicity and monotonicity > 0.5 else 'moderate'} agreement "
            f"between pseudotime ordering and actual clinical timepoints.",
            styles["ReportBody"],
        ))
    elements.append(Paragraph(
        f"A total of <b>{n_traj_features}</b> genes showed significant expression "
        f"changes along the disease trajectory.",
        styles["ReportBody"],
    ))

    # Embed figures
    elements.append(Paragraph("3.2 Trajectory Visualizations", styles["SubHeading"]))

    _embed_figure(elements,
                  os.path.join(output_dir, "patient_trajectories_pca.png"),
                  "<b>Figure 1.</b> PCA projection of gene expression space, colored "
                  "by disease pseudotime. Gray lines connect samples from the same "
                  "patient over time.",
                  styles)
    elements.append(Spacer(1, 0.15 * inch))

    _embed_figure(elements,
                  os.path.join(output_dir, "pseudotime_vs_stage.png"),
                  "<b>Figure 2.</b> Pseudotime distribution across clinical tumor "
                  "stages. Higher pseudotime corresponds to more advanced disease.",
                  styles)

    elements.append(PageBreak())

    _embed_figure(elements,
                  os.path.join(output_dir, "patient_progression.png"),
                  "<b>Figure 3.</b> Per-patient pseudotime progression over actual "
                  "clinical timepoints. Each colored line represents one patient.",
                  styles)
    elements.append(Spacer(1, 0.15 * inch))

    _embed_figure(elements,
                  os.path.join(output_dir, "timeax_progression_rates.png"),
                  "<b>Figure 4.</b> Patient progression rates ranked from fastest "
                  "(red) to slowest (blue), showing heterogeneity in disease dynamics.",
                  styles)

    elements.append(PageBreak())
    elements.append(Paragraph("3.3 Molecular Dynamics", styles["SubHeading"]))

    _embed_figure(elements,
                  os.path.join(output_dir, "seed_feature_heatmap.png"),
                  "<b>Figure 5.</b> Heatmap of TimeAx seed feature expression "
                  "dynamics. Samples ordered by pseudotime (left to right), "
                  "color = Z-score.",
                  styles)
    elements.append(Spacer(1, 0.15 * inch))

    _embed_figure(elements,
                  os.path.join(output_dir, "timeax_seed_dynamics.png"),
                  "<b>Figure 6.</b> LOESS-smoothed expression trends for seed "
                  "features along disease pseudotime.",
                  styles)

    # Top trajectory features table
    if trajectory_features is not None and len(trajectory_features) > 0:
        elements.append(PageBreak())
        elements.append(Paragraph("3.4 Top Trajectory Features", styles["SubHeading"]))
        header = ["Rank", "Gene", "R\u00b2", "Best Fit", "Direction"]
        rows = []
        deg_labels = {1: "Linear", 2: "Quadratic", 3: "Cubic"}
        for i, (_, row) in enumerate(trajectory_features.head(15).iterrows(), 1):
            rows.append([
                str(i), str(row["feature"]),
                f"{row['r_squared']:.3f}",
                deg_labels.get(int(row.get('best_degree', 1)), "Unknown"),
                str(row.get("direction", "N/A")),
            ])
        elements.append(_make_table(
            header, rows,
            col_widths=[0.5*inch, 1.8*inch, 0.8*inch, 1.0*inch, 0.8*inch],
        ))

    # ===== 4. CONCLUSIONS =====
    elements.append(PageBreak())
    elements.append(Paragraph("4. Conclusions", styles["SectionHeading"]))

    elements.append(Paragraph(
        f"TimeAx trajectory analysis of {n_patients} patients ({n_samples} samples) "
        f"successfully reconstructed a consensus disease progression timeline. "
        f"The analysis identified {n_traj_features} genes with significant expression "
        f"dynamics along the trajectory, providing molecular insight into disease "
        f"progression mechanisms.",
        styles["ReportBody"],
    ))

    if monotonicity is not None and monotonicity > 0.5:
        elements.append(Paragraph(
            f"The monotonicity score of <b>{monotonicity:.3f}</b> indicates good "
            f"agreement between the computed pseudotime and actual clinical timepoints, "
            f"supporting the biological validity of the reconstructed trajectory.",
            styles["ReportBody"],
        ))

    elements.append(Paragraph("4.1 Caveats", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; Disease pseudotime is a relative ordering and does not correspond "
        "to absolute calendar time.<br/>"
        "&bull; TimeAx assumes a single dominant disease trajectory; patients with "
        "divergent disease courses may not be well captured.<br/>"
        "&bull; Trajectory features reflect associations with pseudotime, not "
        "necessarily causal relationships with disease progression.<br/>"
        "&bull; The LOO robustness metric from TimeAx v0.1.1 can produce misleading "
        "negative values; within-patient monotonicity is a more reliable quality metric.",
        styles["ReportBody"],
    ))

    elements.append(Paragraph("4.2 Suggested Next Steps", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; <b>Functional enrichment</b> of trajectory features to identify "
        "pathways driving disease progression.<br/>"
        "&bull; <b>Transcription factor activity</b> analysis along pseudotime "
        "to find master regulators.<br/>"
        "&bull; <b>Patient stratification</b> by progression rate for clinical "
        "decision support.<br/>"
        "&bull; <b>Survival analysis</b> using pseudotime-based risk groups.",
        styles["ReportBody"],
    ))

    # Footer
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(HRFlowable(
        width="60%", thickness=0.5, color=COLOR_MEDIUM_GRAY,
        spaceAfter=8, spaceBefore=8,
    ))
    elements.append(Paragraph(
        f"Generated by Disease Progression Trajectory Agent Skill | "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
        title="Disease Progression Trajectory Analysis Report",
        author="Disease Progression Agent Skill",
    )
    doc.build(elements)
    print(f"  ✓ PDF report: {output_file}")
    return output_file

