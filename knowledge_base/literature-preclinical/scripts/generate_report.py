"""
Generate a structured PDF analysis report for preclinical literature extraction.

Creates a publication-quality PDF with Title Page, Introduction, Methods,
Results (with embedded figures), and Conclusions sections using reportlab.

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
# Color constants (consistent with project standard)
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
    """Search for a figure in output_dir."""
    path = os.path.join(output_dir, filename)
    return path


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

def generate_report(
    results,
    experiments,
    synthesis,
    target="",
    disease="",
    output_dir=".",
    output_file=None,
):
    """
    Generate a structured PDF analysis report for preclinical literature extraction.

    Parameters
    ----------
    results : list
        Search results (paper dicts).
    experiments : list
        Experiment extraction dicts.
    synthesis : dict
        Synthesis summary from synthesize_preclinical().
    target : str
        Molecular target name.
    disease : str
        Disease context.
    output_dir : str
        Directory containing figures and where PDF will be saved.
    output_file : str, optional
        Full path for output PDF. Defaults to output_dir/preclinical_report.pdf.

    Returns
    -------
    str or None
        Path to generated PDF, or None if reportlab unavailable.
    """
    if not HAS_REPORTLAB:
        print("   reportlab not installed - skipping PDF (markdown report available)")
        return None

    if output_file is None:
        output_file = os.path.join(output_dir, "preclinical_report.pdf")

    styles = _build_styles()
    elements = []

    # Compute summary stats
    n_papers = synthesis.get("total_papers", len(experiments))
    type_bd = synthesis.get("experiment_type_breakdown", {})
    n_vitro = type_bd.get("in_vitro", 0)
    n_vivo = type_bd.get("in_vivo", 0)
    n_both = type_bd.get("both", 0)
    n_unclass = type_bd.get("unclassified", 0)
    n_cell_lines = len(synthesis.get("cell_line_frequency", {}))
    n_models = len(synthesis.get("animal_model_frequency", {}))

    # ===== TITLE PAGE =====
    elements.append(Spacer(1, 0.8 * inch))
    elements.append(Paragraph(
        "Preclinical Literature<br/>Extraction Report",
        styles["ReportTitle"],
    ))
    elements.append(Paragraph(
        f"{target} in {disease}",
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

    # Summary stat boxes — row 1
    stat_data = [
        [Paragraph(f"<b>{n_papers}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_both}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_cell_lines}</b>", styles["StatNumber"])],
        [Paragraph("Papers Analyzed", styles["StatLabel"]),
         Paragraph("Both In Vitro + In Vivo", styles["StatLabel"]),
         Paragraph("Unique Cell Lines", styles["StatLabel"])],
    ]
    stat_table = Table(stat_data, colWidths=[2.2 * inch] * 3)
    stat_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Summary stat boxes — row 2
    stat_data2 = [
        [Paragraph(f"<b>{n_vitro}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_vivo}</b>", styles["StatNumber"]),
         Paragraph(f"<b>{n_models}</b>", styles["StatNumber"])],
        [Paragraph("In Vitro Only", styles["StatLabel"]),
         Paragraph("In Vivo Only", styles["StatLabel"]),
         Paragraph("Unique Animal Models", styles["StatLabel"])],
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
        f"This report summarizes a systematic extraction of preclinical experiment details "
        f"from {n_papers} published studies investigating <b>{target}</b> in the context of "
        f"<b>{disease}</b>. The goal is to compile a structured overview of the preclinical "
        f"evidence landscape, including in vitro assays, in vivo models, and key findings.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "Preclinical studies form the foundation of drug development, providing evidence "
        "of target engagement, efficacy in model systems, and safety signals before clinical "
        "testing. Understanding the breadth and consistency of preclinical evidence helps "
        "inform IND-enabling decisions and identify gaps in the evidence base.",
        styles["ReportBody"],
    ))
    elements.append(Paragraph(
        "Each paper was analyzed to extract structured details about: (1) in vitro experiments "
        "&mdash; cell lines used, assays performed, and key findings; and (2) in vivo experiments "
        "&mdash; animal models, endpoints measured, and outcomes. Results were synthesized across "
        "papers to identify common model systems, assay types, and concordance between in vitro "
        "and in vivo findings.",
        styles["ReportBody"],
    ))

    # ===== 2. METHODS =====
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("2. Methods", styles["SectionHeading"]))

    elements.append(Paragraph("2.1 Literature Search", styles["SubHeading"]))
    elements.append(Paragraph(
        f"Papers were retrieved using the Consensus API (consensus.app), which performs "
        f"semantic search across indexed scientific literature. Multiple query variants "
        f"were used to maximize coverage: \"{target} {disease} preclinical\" and "
        f"\"{target} {disease} in vitro in vivo\". Results were deduplicated by DOI and "
        f"title, then sorted by publication date.",
        styles["ReportBody"],
    ))

    elements.append(Paragraph("2.2 Experiment Extraction", styles["SubHeading"]))
    elements.append(Paragraph(
        "Each abstract was parsed using keyword-based extraction to identify: "
        "(1) <b>In vitro indicators</b> &mdash; cell line names, assay types (viability, "
        "proliferation, apoptosis, migration, western blot, flow cytometry, etc.); "
        "(2) <b>In vivo indicators</b> &mdash; animal model types (xenograft, PDX, syngeneic, "
        "transgenic, orthotopic), endpoints (tumor growth, survival, pharmacokinetics, toxicity, "
        "histology, imaging); and (3) <b>Key findings</b> &mdash; quantitative results extracted "
        "from the abstract text.",
        styles["ReportBody"],
    ))

    elements.append(Paragraph("2.3 Synthesis", styles["SubHeading"]))
    elements.append(Paragraph(
        "Extracted experiments were aggregated across papers to compute frequency distributions "
        "for cell lines, assay types, animal models, and endpoints. Finding directions "
        "(positive, negative, neutral, combination) were classified based on keyword analysis. "
        "Evidence gaps were identified by checking for missing critical model types and endpoints.",
        styles["ReportBody"],
    ))

    # Parameters table
    elements.append(Paragraph("2.4 Search Parameters", styles["SubHeading"]))
    # Get year range from results
    years = [r.get("publication_date", "")[:4] for r in results if r.get("publication_date", "")]
    years = [y for y in years if y.isdigit()]
    year_range = f"{min(years)}&ndash;{max(years)}" if years else "N/A"

    param_rows = [
        ["Target", target],
        ["Disease", disease],
        ["Search Backend", "Consensus API (consensus.app)"],
        ["Papers Retrieved", str(n_papers)],
        ["Publication Date Range", year_range],
    ]
    elements.append(_make_table(
        ["Parameter", "Value"], param_rows,
        col_widths=[2.5 * inch, 4.0 * inch],
    ))
    elements.append(Spacer(1, 0.1 * inch))

    # ===== 3. RESULTS =====
    elements.append(PageBreak())
    elements.append(Paragraph("3. Results", styles["SectionHeading"]))

    # 3.1 Experiment type breakdown
    elements.append(Paragraph("3.1 Experiment Type Breakdown", styles["SubHeading"]))
    elements.append(Paragraph(
        f"Of {n_papers} papers analyzed, <b>{n_both}</b> reported both in vitro and in vivo "
        f"experiments, <b>{n_vitro}</b> reported in vitro only, <b>{n_vivo}</b> reported in vivo "
        f"only, and <b>{n_unclass}</b> could not be classified from abstract text alone.",
        styles["ReportBody"],
    ))
    type_rows = [
        ["In vitro only", str(n_vitro), f"{n_vitro/max(n_papers,1)*100:.1f}%"],
        ["In vivo only", str(n_vivo), f"{n_vivo/max(n_papers,1)*100:.1f}%"],
        ["Both", str(n_both), f"{n_both/max(n_papers,1)*100:.1f}%"],
        ["Unclassified", str(n_unclass), f"{n_unclass/max(n_papers,1)*100:.1f}%"],
    ]
    elements.append(_make_table(
        ["Experiment Type", "Papers", "Percentage"], type_rows,
        col_widths=[2.5 * inch, 1.5 * inch, 1.5 * inch],
    ))
    elements.append(Spacer(1, 0.15 * inch))

    # 3.2 Top cell lines
    cell_lines = synthesis.get("cell_line_frequency", {})
    if cell_lines:
        elements.append(Paragraph("3.2 Most Common Cell Lines", styles["SubHeading"]))
        cl_rows = [[str(i), cl, str(count)]
                    for i, (cl, count) in enumerate(list(cell_lines.items())[:10], 1)]
        elements.append(_make_table(
            ["Rank", "Cell Line", "Papers"], cl_rows,
            col_widths=[0.5 * inch, 3.0 * inch, 1.5 * inch],
        ))
        elements.append(Spacer(1, 0.15 * inch))

    # 3.3 Top assay types
    assays = synthesis.get("assay_frequency", {})
    if assays:
        elements.append(Paragraph("3.3 Most Common Assay Types", styles["SubHeading"]))
        assay_rows = [[str(i), assay, str(count)]
                      for i, (assay, count) in enumerate(list(assays.items())[:10], 1)]
        elements.append(_make_table(
            ["Rank", "Assay Type", "Papers"], assay_rows,
            col_widths=[0.5 * inch, 3.0 * inch, 1.5 * inch],
        ))
        elements.append(Spacer(1, 0.15 * inch))

    # 3.4 Animal models
    models = synthesis.get("animal_model_frequency", {})
    if models:
        elements.append(Paragraph("3.4 Animal Model Types", styles["SubHeading"]))
        model_rows = [[str(i), model, str(count)]
                      for i, (model, count) in enumerate(list(models.items())[:10], 1)]
        elements.append(_make_table(
            ["Rank", "Model Type", "Papers"], model_rows,
            col_widths=[0.5 * inch, 3.0 * inch, 1.5 * inch],
        ))
        elements.append(Spacer(1, 0.15 * inch))

    # 3.5 Endpoints
    endpoints = synthesis.get("endpoint_frequency", {})
    if endpoints:
        elements.append(Paragraph("3.5 Endpoints Measured", styles["SubHeading"]))
        ep_rows = [[str(i), ep, str(count)]
                   for i, (ep, count) in enumerate(list(endpoints.items())[:10], 1)]
        elements.append(_make_table(
            ["Rank", "Endpoint", "Papers"], ep_rows,
            col_widths=[0.5 * inch, 3.0 * inch, 1.5 * inch],
        ))
        elements.append(Spacer(1, 0.15 * inch))

    # 3.6 Visualizations (embedded PNG)
    elements.append(Paragraph("3.6 Visualizations", styles["SubHeading"]))

    plot_path = _find_figure(output_dir, "preclinical_plots.png")
    _embed_figure(elements, plot_path,
                  "<b>Figure 1.</b> Four-panel preclinical experiment visualization: "
                  "(A) Experiment type breakdown, (B) Top assay types, "
                  "(C) Animal model distribution, (D) Publication timeline.",
                  styles)
    elements.append(Spacer(1, 0.15 * inch))

    # 3.7 Narrative synthesis (if available)
    narrative = synthesis.get("narrative", {})
    if narrative:
        elements.append(Paragraph("3.7 Narrative Synthesis", styles["SubHeading"]))

        # Therapeutic direction
        td = narrative.get("therapeutic_direction", [])
        if td:
            elements.append(Paragraph(
                f"<b>Therapeutic direction:</b> {td[0]}",
                styles["ReportBody"],
            ))

        # Agreements
        agreements = narrative.get("agreements", [])
        if agreements:
            elements.append(Paragraph("<b>Key agreements across studies:</b>", styles["ReportBody"]))
            for a in agreements[:5]:
                elements.append(Paragraph(f"&bull; {a}", styles["ReportBody"]))

        # Disagreements
        disagreements = narrative.get("disagreements", [])
        if disagreements:
            elements.append(Paragraph("<b>Disagreements or inconsistencies:</b>", styles["ReportBody"]))
            for d in disagreements[:5]:
                elements.append(Paragraph(f"&bull; {d}", styles["ReportBody"]))

        # Gaps
        gaps = narrative.get("gaps", [])
        if gaps:
            elements.append(Paragraph("<b>Evidence gaps:</b>", styles["ReportBody"]))
            for g in gaps[:5]:
                elements.append(Paragraph(f"&bull; {g}", styles["ReportBody"]))

    # ===== 4. CONCLUSIONS =====
    elements.append(PageBreak())
    elements.append(Paragraph("4. Conclusions", styles["SectionHeading"]))

    elements.append(Paragraph("4.1 Key Findings", styles["SubHeading"]))
    elements.append(Paragraph(
        f"This analysis extracted preclinical experiment details from {n_papers} papers "
        f"studying {target} in {disease}. ",
        styles["ReportBody"],
    ))

    if n_both > 0:
        elements.append(Paragraph(
            f"<b>{n_both} papers</b> reported both in vitro and in vivo experiments, "
            f"providing the strongest translational evidence. ",
            styles["ReportBody"],
        ))

    if cell_lines:
        top_cls = list(cell_lines.keys())[:3]
        elements.append(Paragraph(
            f"The most commonly used cell lines were <b>{', '.join(top_cls)}</b>.",
            styles["ReportBody"],
        ))

    if models:
        top_models = list(models.keys())[:3]
        elements.append(Paragraph(
            f"The most common animal model types were <b>{', '.join(top_models)}</b>.",
            styles["ReportBody"],
        ))

    elements.append(Paragraph("4.2 Caveats", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; Experiment extraction is based on abstract text only and may miss details "
        "available only in full-text methods sections.<br/>"
        "&bull; Keyword-based classification has inherent limitations &mdash; novel assay names "
        "or unconventional terminology may be missed.<br/>"
        "&bull; Publication bias may skew results toward positive findings.<br/>"
        "&bull; The search is limited to papers indexed by Consensus and may not cover "
        "all published preclinical studies.",
        styles["ReportBody"],
    ))

    elements.append(Paragraph("4.3 Suggested Next Steps", styles["SubHeading"]))
    elements.append(Paragraph(
        "&bull; <b>Full-text review</b> of top papers (especially those with both in vitro "
        "and in vivo data) for detailed experimental parameters.<br/>"
        "&bull; <b>Expand search</b> with alternative target names or broader disease terms "
        "to capture additional studies.<br/>"
        "&bull; <b>Functional enrichment analysis</b> of target-related pathways using "
        "complementary bioinformatics skills.<br/>"
        "&bull; <b>Clinical translation</b> &mdash; compare preclinical findings with "
        "clinical trial outcomes using the clinicaltrials-landscape skill.",
        styles["ReportBody"],
    ))

    # Footer
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(HRFlowable(
        width="60%", thickness=0.5, color=COLOR_MEDIUM_GRAY,
        spaceAfter=8, spaceBefore=8,
    ))
    elements.append(Paragraph(
        f"Generated by literature-preclinical Agent Skill | "
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
        title=f"Preclinical Literature Extraction: {target} in {disease}",
        author="literature-preclinical Agent Skill",
    )
    doc.build(elements)
    print(f"   Saved: {output_file}")
    return output_file

