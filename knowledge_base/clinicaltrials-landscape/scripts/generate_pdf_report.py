"""
Generate comprehensive PDF landscape report for clinical trials.

Config-driven: all disease-specific content (mechanism briefs, highlight
sections, indication categories, executive highlights) is loaded from
a disease YAML config via disease_config.py.  When no config is provided
the report still works with generic headings.

Uses reportlab to create a publication-quality PDF with:
- Title page with executive summary stats
- 6-panel landscape visualization (embedded PNG)
- Mechanism x Phase distribution table
- Mechanism deep-dives with drug pipeline tables
- Late-stage pipeline (Phase 3) analysis
- Upcoming readouts section
- Config-driven mechanism & sponsor highlight sections
- Sponsor competitive landscape tables
- Company portfolio analysis
- Config-driven indication breakdown
- Enrollment / investment signals

Requires: reportlab (pip install reportlab)
"""

import os
import re
from datetime import datetime, timedelta

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

try:
    from disease_config import (
        get_mechanism_briefs, get_disease_name, get_disease_short,
        get_highlight_mechanisms, get_highlight_sponsors,
        get_executive_highlights, get_indication_categories,
    )
except ImportError:
    from scripts.disease_config import (
        get_mechanism_briefs, get_disease_name, get_disease_short,
        get_highlight_mechanisms, get_highlight_sponsors,
        get_executive_highlights, get_indication_categories,
    )


# Color constants
COLOR_PRIMARY = colors.HexColor("#1B4F72")
COLOR_ACCENT = colors.HexColor("#E74C3C")
COLOR_GREEN = colors.HexColor("#27AE60")
COLOR_ORANGE = colors.HexColor("#E67E22")
COLOR_LIGHT_GRAY = colors.HexColor("#F2F3F4")
COLOR_MEDIUM_GRAY = colors.HexColor("#BDC3C7")
COLOR_DARK = colors.HexColor("#2C3E50")
COLOR_HIGHLIGHT_ROW = colors.HexColor("#FADBD8")
COLOR_GREEN_ROW = colors.HexColor("#D5F5E3")
COLOR_BLUE_ROW = colors.HexColor("#D6EAF8")
COLOR_ORANGE_ROW = colors.HexColor("#FDEBD0")


def _build_styles():
    """Create custom paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=26, textColor=COLOR_PRIMARY, spaceAfter=6, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=13, textColor=COLOR_DARK, spaceAfter=20, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "SectionHeading", parent=styles["Heading1"],
        fontSize=16, textColor=COLOR_PRIMARY, spaceBefore=18, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        "SubHeading", parent=styles["Heading2"],
        fontSize=13, textColor=COLOR_DARK, spaceBefore=12, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "SubSubHeading", parent=styles["Heading3"],
        fontSize=11, textColor=COLOR_PRIMARY, spaceBefore=8, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "ReportBody", parent=styles["Normal"],
        fontSize=10, textColor=COLOR_DARK, spaceAfter=6, leading=14,
    ))
    styles.add(ParagraphStyle(
        "BodySmall", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_DARK, spaceAfter=4, leading=12,
    ))
    styles.add(ParagraphStyle(
        "MechDescription", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=6,
        leading=12, leftIndent=8, rightIndent=8,
    ))
    styles.add(ParagraphStyle(
        "StatNumber", parent=styles["Normal"],
        fontSize=28, textColor=COLOR_ACCENT, alignment=TA_CENTER, spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        "StatLabel", parent=styles["Normal"],
        fontSize=9, textColor=COLOR_DARK, alignment=TA_CENTER, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        "BulletItem", parent=styles["Normal"],
        fontSize=10, textColor=COLOR_DARK, leftIndent=20, spaceAfter=3, leading=13,
    ))
    styles.add(ParagraphStyle(
        "TrialEntry", parent=styles["Normal"],
        fontSize=8.5, textColor=COLOR_DARK, leftIndent=12, spaceAfter=2, leading=11,
    ))
    styles.add(ParagraphStyle(
        "FooterText", parent=styles["Normal"],
        fontSize=8, textColor=COLOR_MEDIUM_GRAY, alignment=TA_CENTER,
    ))

    # ---- Table cell styles (enable text wrapping) ----
    styles.add(ParagraphStyle(
        "CellLeft", parent=styles["Normal"],
        fontSize=7.5, textColor=COLOR_DARK, leading=9,
        alignment=TA_LEFT, wordWrap="CJK",
        spaceAfter=0, spaceBefore=0,
    ))
    styles.add(ParagraphStyle(
        "CellCenter", parent=styles["Normal"],
        fontSize=7.5, textColor=COLOR_DARK, leading=9,
        alignment=TA_CENTER, wordWrap="CJK",
        spaceAfter=0, spaceBefore=0,
    ))
    styles.add(ParagraphStyle(
        "CellHeaderLeft", parent=styles["Normal"],
        fontSize=7.5, textColor=colors.white, leading=9,
        fontName="Helvetica-Bold", alignment=TA_LEFT,
        spaceAfter=0, spaceBefore=0,
    ))
    styles.add(ParagraphStyle(
        "CellHeaderCenter", parent=styles["Normal"],
        fontSize=7.5, textColor=colors.white, leading=9,
        fontName="Helvetica-Bold", alignment=TA_CENTER,
        spaceAfter=0, spaceBefore=0,
    ))

    return styles


def _make_table_style(header_color=COLOR_PRIMARY):
    """Standard table style for landscape tables with Paragraph cells."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_MEDIUM_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_GRAY]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])


def _make_wrapped_table(data_rows, col_widths, text_cols, header_color=COLOR_PRIMARY, styles=None):
    """
    Create a table with Paragraph-wrapped cells for proper text wrapping.

    Parameters
    ----------
    data_rows : list of list
        First row is header. Remaining rows are data (strings/ints/floats).
    col_widths : list of float
        Column widths.
    text_cols : set of int
        Column indices that contain long text and should be LEFT-aligned.
        Other columns will be CENTER-aligned.
    header_color : Color
        Header row background color.
    styles : StyleSheet
        Paragraph styles (must contain CellLeft, CellCenter, CellHeaderLeft, CellHeaderCenter).
    """
    if styles is None:
        styles = _build_styles()

    cell_left = styles["CellLeft"]
    cell_center = styles["CellCenter"]
    hdr_left = styles["CellHeaderLeft"]
    hdr_center = styles["CellHeaderCenter"]

    wrapped = []
    for row_idx, row in enumerate(data_rows):
        wrapped_row = []
        for col_idx, cell in enumerate(row):
            text = str(cell) if cell is not None else "\u2014"
            is_text_col = col_idx in text_cols

            if row_idx == 0:
                # Header row
                style = hdr_left if is_text_col else hdr_center
                wrapped_row.append(Paragraph(f"<b>{text}</b>", style))
            else:
                style = cell_left if is_text_col else cell_center
                wrapped_row.append(Paragraph(text, style))
        wrapped.append(wrapped_row)

    table = Table(wrapped, colWidths=col_widths, repeatRows=1)
    table.setStyle(_make_table_style(header_color))
    return table


def generate_pdf_report(
    trials_df,
    parameters=None,
    output_file="landscape_report.pdf",
    plot_image_path=None,
    config=None,
):
    """
    Generate comprehensive PDF landscape report.

    Parameters
    ----------
    trials_df : pd.DataFrame
        Compiled trials from compile_trials().
    parameters : dict, optional
        Query parameters and metadata.
    output_file : str
        Output PDF file path.
    plot_image_path : str or None
        Path to the 6-panel landscape PNG to embed.
    config : dict or None
        Disease config loaded via load_disease_config().
        When None, generic headings are used.

    Returns
    -------
    str
        Path to the generated PDF.
    """
    if parameters is None:
        parameters = {}

    # ---- Config-driven disease data ----
    disease_name = get_disease_name(config, default="Clinical Trial")
    disease_short = get_disease_short(config, default="")
    mechanism_briefs = get_mechanism_briefs(config)
    highlight_mechanisms = get_highlight_mechanisms(config)
    highlight_sponsors = get_highlight_sponsors(config)
    exec_highlights = get_executive_highlights(config)
    indication_cats = get_indication_categories(config)

    styles = _build_styles()
    elements = []
    now = datetime.now()

    n_total = len(trials_df)
    n_mechanisms = trials_df["mechanism"].nunique()
    n_sponsors = trials_df["sponsor_normalized"].nunique()
    n_industry = int(trials_df["is_industry"].sum())
    highlight_mech = parameters.get("highlight_mechanism", "")
    highlight_sponsor = parameters.get("highlight_sponsor")

    non_pharma = ["Non-pharmacological", "Unclassified", "Other Biologic", "Small Molecule (Other)"]
    pharma_df = trials_df[~trials_df["mechanism"].isin(non_pharma)]
    top_mech = trials_df["mechanism"].value_counts()
    pharma_mechs = top_mech[~top_mech.index.isin(non_pharma)]

    # ==========================================
    # PAGE 1: Title + Executive Summary
    # ==========================================

    elements.append(Spacer(1, 0.4 * inch))
    elements.append(Paragraph(f"{disease_name} Clinical Trial Landscape", styles["ReportTitle"]))
    elements.append(Paragraph("Competitive Intelligence Report", styles["ReportSubtitle"]))

    if highlight_mech:
        elements.append(Paragraph(
            f"Focus: <b>{highlight_mech}</b>", styles["ReportSubtitle"],
        ))

    elements.append(Paragraph(
        f"Generated: {now.strftime('%B %d, %Y')}  |  Source: ClinicalTrials.gov API v2",
        styles["FooterText"],
    ))
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(HRFlowable(width="100%", color=COLOR_PRIMARY, thickness=2))
    elements.append(Spacer(1, 0.2 * inch))

    # Key stats boxes (2 rows of 4)
    phase3_count = len(trials_df[trials_df["phase_normalized"] == "Phase 3"])
    n_recruiting = len(trials_df[trials_df["overall_status"] == "RECRUITING"])

    stat_data = [
        [
            Paragraph(f"<b>{n_total}</b>", styles["StatNumber"]),
            Paragraph(f"<b>{n_mechanisms}</b>", styles["StatNumber"]),
            Paragraph(f"<b>{n_sponsors}</b>", styles["StatNumber"]),
            Paragraph(f"<b>{n_industry}</b>", styles["StatNumber"]),
        ],
        [
            Paragraph("Clinical Trials", styles["StatLabel"]),
            Paragraph("Mechanism Classes", styles["StatLabel"]),
            Paragraph("Unique Sponsors", styles["StatLabel"]),
            Paragraph("Industry-Sponsored", styles["StatLabel"]),
        ],
        [
            Paragraph(f"<b>{phase3_count}</b>", styles["StatNumber"]),
            Paragraph(f"<b>{n_recruiting}</b>", styles["StatNumber"]),
            Paragraph(f"<b>{pharma_df['mechanism'].nunique()}</b>", styles["StatNumber"]),
            Paragraph(f"<b>{int(trials_df['enrollment'].sum()):,}</b>", ParagraphStyle(
                "StatEnroll", parent=styles["StatNumber"], fontSize=20)),
        ],
        [
            Paragraph("Phase 3 Trials", styles["StatLabel"]),
            Paragraph("Recruiting Now", styles["StatLabel"]),
            Paragraph("Pharma Mechanisms", styles["StatLabel"]),
            Paragraph("Total Enrollment", styles["StatLabel"]),
        ],
    ]
    stat_table = Table(stat_data, colWidths=[1.6 * inch] * 4)
    stat_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_LIGHT_GRAY),
        ("BOX", (0, 0), (0, 1), 1, colors.white),
        ("BOX", (1, 0), (1, 1), 1, colors.white),
        ("BOX", (2, 0), (2, 1), 1, colors.white),
        ("BOX", (3, 0), (3, 1), 1, colors.white),
        ("BOX", (0, 2), (0, 3), 1, colors.white),
        ("BOX", (1, 2), (1, 3), 1, colors.white),
        ("BOX", (2, 2), (2, 3), 1, colors.white),
        ("BOX", (3, 2), (3, 3), 1, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(stat_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Strategic highlights
    elements.append(Paragraph("Strategic Highlights", styles["SectionHeading"]))

    highlights = []
    if len(pharma_mechs) > 0:
        highlights.append(f"Most active mechanism: <b>{pharma_mechs.index[0]}</b> ({pharma_mechs.iloc[0]} trials)")

    top_sponsor = trials_df["sponsor_normalized"].value_counts()
    if len(top_sponsor) > 0:
        highlights.append(f"Most active sponsor: <b>{top_sponsor.index[0]}</b> ({top_sponsor.iloc[0]} trials)")

    # Config-driven mechanism highlights
    exec_mechs = exec_highlights.get("mechanisms", []) if exec_highlights else []
    for mech_name in exec_mechs:
        mech_count = len(trials_df[trials_df["mechanism"] == mech_name])
        if mech_count > 0:
            mech_p3 = len(trials_df[(trials_df["mechanism"] == mech_name) & (trials_df["phase_normalized"] == "Phase 3")])
            highlights.append(f"{mech_name}: <b>{mech_count} trials</b> ({mech_p3} in Phase 3)")

    # Config-driven sponsor highlights
    exec_sponsors = exec_highlights.get("sponsors", []) if exec_highlights else []
    for sponsor_name in exec_sponsors:
        sponsor_count = len(trials_df[trials_df["sponsor_normalized"] == sponsor_name])
        if sponsor_count > 0:
            highlights.append(f"{sponsor_name} portfolio: <b>{sponsor_count} active trials</b>")

    upcoming = _get_upcoming_readouts(trials_df, months=18)
    if len(upcoming) > 0:
        highlights.append(f"Upcoming readouts (18 months): <b>{len(upcoming)} trials</b> expected to report")

    for h in highlights:
        elements.append(Paragraph(f"\u2022  {h}", styles["BulletItem"]))

    # ==========================================
    # PAGE 2: Landscape Visualization
    # ==========================================

    if plot_image_path and os.path.exists(plot_image_path):
        elements.append(PageBreak())
        elements.append(Paragraph("Landscape Visualization", styles["SectionHeading"]))
        elements.append(Spacer(1, 0.1 * inch))

        page_width = letter[0] - 2 * inch
        img = Image(plot_image_path)
        aspect = img.imageHeight / img.imageWidth
        img_width = min(page_width, 6.5 * inch)
        img_height = img_width * aspect
        max_height = 8.5 * inch
        if img_height > max_height:
            img_height = max_height
            img_width = img_height / aspect
        img.drawWidth = img_width
        img.drawHeight = img_height
        elements.append(img)

    # ==========================================
    # PAGE 3: Mechanism x Phase Table
    # ==========================================

    elements.append(PageBreak())
    elements.append(Paragraph("Mechanism \u00d7 Phase Distribution", styles["SectionHeading"]))
    elements.append(Spacer(1, 0.1 * inch))

    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4"]
    ct = pd.crosstab(trials_df["mechanism"], trials_df["phase_normalized"])
    ct = ct.reindex(columns=[p for p in phase_order if p in ct.columns], fill_value=0)
    ct["Total"] = ct.sum(axis=1)
    ct = ct.sort_values("Total", ascending=False)

    cols = list(ct.columns)
    mech_data = [["Mechanism"] + cols]
    for mech, row in ct.iterrows():
        mech_data.append([mech] + [int(row[c]) for c in cols])

    col_widths = [2.2 * inch] + [0.7 * inch] * len(cols)
    mech_table = _make_wrapped_table(mech_data, col_widths, text_cols={0}, styles=styles)

    # Apply highlight for focus mechanism
    if highlight_mech:
        extra_cmds = []
        for i, row_data in enumerate(mech_data):
            if i > 0 and row_data[0] == highlight_mech:
                extra_cmds.append(("BACKGROUND", (0, i), (-1, i), COLOR_HIGHLIGHT_ROW))
        if extra_cmds:
            existing = list(mech_table._argS[0]) if hasattr(mech_table, '_argS') else []
            mech_table.setStyle(TableStyle(extra_cmds))

    elements.append(mech_table)

    # Indication breakdown (config-driven)
    if indication_cats:
        elements.append(Spacer(1, 0.25 * inch))
        elements.append(Paragraph("Indication Breakdown", styles["SubHeading"]))

        ind_data = [["Indication", "Trials", "% of Total"]]
        matched_max = 0
        for cat in indication_cats:
            if cat.get("is_default"):
                continue  # handle default row last
            pattern = cat.get("pattern", "")
            full_name = cat.get("full_name", cat.get("label", ""))
            cat_count = sum(
                1 for _, t in trials_df.iterrows()
                if pattern and pattern in str(t.get("conditions_str", "")).lower()
            )
            ind_data.append([full_name, cat_count, f"{cat_count/n_total*100:.0f}%"])
            matched_max = max(matched_max, cat_count)

        # Default / catch-all row
        default_cats = [c for c in indication_cats if c.get("is_default")]
        if default_cats:
            default_label = default_cats[0].get("full_name", default_cats[0].get("label", "Other"))
            other_count = n_total - matched_max
            ind_data.append([default_label, other_count, f"{other_count/n_total*100:.0f}%"])

        elements.append(_make_wrapped_table(ind_data, [2.5 * inch, 1.0 * inch, 1.0 * inch], text_cols={0}, styles=styles))

    # ==========================================
    # PAGE 4+: Mechanism Deep Dives
    # ==========================================

    elements.append(PageBreak())
    elements.append(Paragraph("Mechanism Deep Dives", styles["SectionHeading"]))
    elements.append(Paragraph(
        "Detailed analysis of each major therapeutic mechanism class, including drug pipeline, "
        "key sponsors, and trial listings.",
        styles["ReportBody"],
    ))

    mech_order = pharma_mechs[pharma_mechs >= 2].index.tolist()

    for mech in mech_order:
        mech_df = trials_df[trials_df["mechanism"] == mech].copy()

        mech_elements = []
        mech_elements.append(Spacer(1, 0.15 * inch))
        mech_elements.append(HRFlowable(width="100%", color=COLOR_MEDIUM_GRAY, thickness=0.5))
        mech_elements.append(Spacer(1, 0.05 * inch))
        mech_elements.append(Paragraph(
            f"{mech} \u2014 {len(mech_df)} trials", styles["SubHeading"],
        ))

        brief = mechanism_briefs.get(mech, "")
        if brief:
            mech_elements.append(Paragraph(f"<i>{brief}</i>", styles["MechDescription"]))

        # Phase + Status summary
        mech_phases = mech_df["phase_normalized"].value_counts()
        phase_parts = [f"{p}: {c}" for p, c in mech_phases.items()]
        mech_statuses = mech_df["overall_status"].value_counts()
        status_parts = [f"{_format_status(s)}: {c}" for s, c in mech_statuses.items()]

        mech_elements.append(Paragraph(
            f"<b>Phases:</b> {' | '.join(phase_parts)}", styles["BodySmall"],
        ))
        mech_elements.append(Paragraph(
            f"<b>Status:</b> {' | '.join(status_parts)}", styles["BodySmall"],
        ))

        # Key sponsors
        mech_sponsors = mech_df["sponsor_normalized"].value_counts().head(6)
        sponsor_parts = []
        for sponsor, count in mech_sponsors.items():
            drugs = _get_unique_drugs(mech_df[mech_df["sponsor_normalized"] == sponsor])
            drug_str = f" ({', '.join(drugs[:2])})" if drugs else ""
            sponsor_parts.append(f"{sponsor}{drug_str}: {count}")
        mech_elements.append(Paragraph(
            f"<b>Key sponsors:</b> {' | '.join(sponsor_parts)}", styles["BodySmall"],
        ))

        # Drug pipeline table
        drugs_table = _build_drug_pipeline_table(mech_df, styles, indication_cats=indication_cats)
        if drugs_table:
            mech_elements.append(Spacer(1, 0.05 * inch))
            mech_elements.append(drugs_table)

        # Trial listing table
        mech_elements.append(Spacer(1, 0.05 * inch))
        trial_table = _build_trial_listing_table(mech_df, styles, max_rows=12)
        if trial_table:
            mech_elements.append(trial_table)
            if len(mech_df) > 12:
                mech_elements.append(Paragraph(
                    f"<i>... and {len(mech_df) - 12} additional trials</i>", styles["BodySmall"],
                ))

        if len(mech_df) <= 6:
            elements.append(KeepTogether(mech_elements))
        else:
            elements.extend(mech_elements)

    # ==========================================
    # LATE-STAGE PIPELINE (Phase 3)
    # ==========================================

    elements.append(PageBreak())
    elements.append(Paragraph("Late-Stage Pipeline (Phase 3)", styles["SectionHeading"]))

    p3_df = trials_df[trials_df["phase_normalized"].isin(["Phase 3", "Phase 3/4"])].copy()
    if len(p3_df) > 0:
        elements.append(Paragraph(
            f"<b>{len(p3_df)} Phase 3 trials</b> represent the most advanced pipeline "
            f"with near-term commercial potential.",
            styles["ReportBody"],
        ))

        p3_mechs = p3_df["mechanism"].value_counts()
        p3_mech_parts = [f"{m} ({c})" for m, c in p3_mechs.items()]
        elements.append(Paragraph(
            f"<b>By mechanism:</b> {', '.join(p3_mech_parts)}", styles["BodySmall"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

        # Phase 3 table: NCT, Drug, Mechanism, Sponsor, Indication, Enrollment, Completion
        p3_data = [["NCT ID", "Drug(s)", "Mechanism", "Sponsor", "Indication", "Enroll.", "Completion"]]
        for _, trial in p3_df.sort_values("completion_date").iterrows():
            drugs = _get_drug_str(trial, max_len=35)
            enrollment_str = f"{int(trial['enrollment']):,}" if pd.notna(trial["enrollment"]) and trial["enrollment"] > 0 else "\u2014"
            completion_str = _format_date(trial.get("completion_date", ""))
            indication = _extract_indication(trial.get("conditions_str", ""), indication_cats)
            p3_data.append([
                trial["nct_id"], drugs, trial["mechanism"],
                trial["sponsor_normalized"], indication, enrollment_str, completion_str,
            ])

        p3_widths = [0.85 * inch, 1.3 * inch, 1.0 * inch, 1.1 * inch, 0.45 * inch, 0.55 * inch, 0.7 * inch]
        # text_cols: Drug(1), Mechanism(2), Sponsor(3) are long text
        elements.append(_make_wrapped_table(p3_data, p3_widths, text_cols={0, 1, 2, 3}, styles=styles))
    else:
        elements.append(Paragraph("<i>No Phase 3 trials in current dataset.</i>", styles["ReportBody"]))

    # ==========================================
    # UPCOMING READOUTS
    # ==========================================

    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph("Upcoming Readouts", styles["SectionHeading"]))

    upcoming_12 = _get_upcoming_readouts(trials_df, months=12)
    upcoming_24 = _get_upcoming_readouts(trials_df, months=24)

    if len(upcoming_24) > 0:
        elements.append(Paragraph(
            f"<b>{len(upcoming_12)} trials</b> expected to complete within 12 months, "
            f"<b>{len(upcoming_24)}</b> within 24 months.",
            styles["ReportBody"],
        ))

        readout_data = [["NCT ID", "Drug(s)", "Mechanism", "Sponsor", "Phase", "Enroll.", "Completion", "Time"]]
        for _, trial in upcoming_24.head(20).iterrows():
            drugs = _get_drug_str(trial, max_len=28)
            enrollment_str = f"{int(trial['enrollment']):,}" if pd.notna(trial["enrollment"]) and trial["enrollment"] > 0 else "\u2014"
            completion_str = _format_date(trial.get("completion_date", ""))
            time_to = _time_to_readout(trial.get("completion_date", ""))
            readout_data.append([
                trial["nct_id"], drugs, trial["mechanism"],
                trial["sponsor_normalized"], trial["phase_normalized"],
                enrollment_str, completion_str, time_to,
            ])

        readout_widths = [0.78 * inch, 1.0 * inch, 0.82 * inch, 0.95 * inch, 0.55 * inch, 0.48 * inch, 0.62 * inch, 0.48 * inch]
        elements.append(_make_wrapped_table(readout_data, readout_widths, text_cols={0, 1, 2, 3}, styles=styles))

        if len(upcoming_24) > 20:
            elements.append(Paragraph(
                f"<i>... and {len(upcoming_24) - 20} additional trials with upcoming readouts</i>",
                styles["BodySmall"],
            ))
    else:
        elements.append(Paragraph("<i>No trials with completion dates within 24 months.</i>", styles["ReportBody"]))

    # ==========================================
    # MECHANISM HIGHLIGHT SECTIONS (config-driven)
    # ==========================================

    for hl_idx, hl_spec in enumerate(highlight_mechanisms):
        hl_mech = hl_spec["mechanism"]
        hl_title = hl_spec.get("section_title", f"{hl_mech} Focus")
        hl_narrative = hl_spec.get("narrative", "")

        hl_trials = trials_df[trials_df["mechanism"] == hl_mech]
        if len(hl_trials) == 0:
            continue

        # First highlight gets a PageBreak; subsequent get a spacer
        if hl_idx == 0:
            elements.append(PageBreak())
        else:
            elements.append(Spacer(1, 0.3 * inch))

        elements.append(Paragraph(hl_title, styles["SectionHeading"]))
        narrative_suffix = f" \u2014 {hl_narrative}" if hl_narrative else ""
        disease_tag = f" in {disease_short}" if disease_short else ""
        elements.append(Paragraph(
            f"<b>{len(hl_trials)} active trials</b>{narrative_suffix}{disease_tag}.",
            styles["ReportBody"],
        ))

        brief = mechanism_briefs.get(hl_mech, "")
        if brief:
            elements.append(Paragraph(f"<i>{brief}</i>", styles["MechDescription"]))

        # Phase breakdown
        hl_phases = hl_trials["phase_normalized"].value_counts()
        for phase, count in hl_phases.items():
            elements.append(Paragraph(f"\u2022  <b>{phase}:</b> {count} trials", styles["BulletItem"]))

        # Key sponsors & drugs
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("Key Sponsors &amp; Drug Programs", styles["SubHeading"]))
        hl_sponsors = hl_trials["sponsor_normalized"].value_counts()
        for sponsor, count in hl_sponsors.items():
            sponsor_trials = hl_trials[hl_trials["sponsor_normalized"] == sponsor]
            drugs = _get_unique_drugs(sponsor_trials)
            phases = sorted(sponsor_trials["phase_normalized"].unique())
            drug_str = f" ({', '.join(drugs)})" if drugs else ""
            enrollments = sponsor_trials["enrollment"].dropna()
            enroll_str = f", ~{int(enrollments.sum()):,} pts" if len(enrollments) > 0 and enrollments.sum() > 0 else ""
            elements.append(Paragraph(
                f"\u2022  <b>{sponsor}</b>: {count} trial{'s' if count > 1 else ''}{drug_str} "
                f"\u2014 {', '.join(phases)}{enroll_str}",
                styles["BulletItem"],
            ))

        # Trial listing
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("Complete Trial Listing", styles["SubHeading"]))
        hl_table = _build_trial_listing_table(hl_trials, styles, max_rows=30)
        if hl_table:
            elements.append(hl_table)

    # ==========================================
    # SPONSOR COMPETITIVE LANDSCAPE
    # ==========================================

    elements.append(PageBreak())
    elements.append(Paragraph("Sponsor Competitive Landscape", styles["SectionHeading"]))
    elements.append(Spacer(1, 0.1 * inch))

    sponsor_summary = (
        trials_df.groupby("sponsor_normalized")
        .agg(
            trials=("nct_id", "count"),
            mechanisms=("mechanism", "nunique"),
            top_mechanism=("mechanism", lambda x: x.value_counts().index[0] if len(x) > 0 else ""),
            industry=("is_industry", "first"),
            total_enrollment=("enrollment", "sum"),
        )
        .sort_values("trials", ascending=False)
        .head(25)
    )

    sponsor_data = [["Rank", "Sponsor", "Trials", "Mech.", "Primary Focus", "Enrollment", "Type"]]
    for rank, (sponsor, row) in enumerate(sponsor_summary.iterrows(), 1):
        enroll = f"{int(row['total_enrollment']):,}" if pd.notna(row["total_enrollment"]) and row["total_enrollment"] > 0 else "\u2014"
        sponsor_data.append([
            rank, sponsor, int(row["trials"]), int(row["mechanisms"]),
            row["top_mechanism"], enroll, "Ind." if row["industry"] else "Acad.",
        ])

    sponsor_col_widths = [0.35 * inch, 1.6 * inch, 0.45 * inch, 0.45 * inch, 1.3 * inch, 0.65 * inch, 0.45 * inch]
    sponsor_table = _make_wrapped_table(
        sponsor_data, sponsor_col_widths, text_cols={1, 4}, styles=styles,
    )

    # Highlight specified sponsor
    if highlight_sponsor:
        extra_cmds = []
        for i, row_data in enumerate(sponsor_data):
            if i > 0 and isinstance(row_data[1], str) and highlight_sponsor.lower() in row_data[1].lower():
                extra_cmds.append(("BACKGROUND", (0, i), (-1, i), COLOR_GREEN_ROW))
        if extra_cmds:
            sponsor_table.setStyle(TableStyle(extra_cmds))

    elements.append(sponsor_table)

    # Company portfolio analysis (top 8)
    elements.append(Spacer(1, 0.25 * inch))
    elements.append(Paragraph("Company Portfolio Analysis", styles["SubHeading"]))

    for sponsor, row in sponsor_summary.head(8).iterrows():
        sponsor_df = trials_df[trials_df["sponsor_normalized"] == sponsor]
        mech_breakdown = sponsor_df["mechanism"].value_counts()
        drugs = _get_unique_drugs(sponsor_df)

        mech_parts = [f"{m} ({c})" for m, c in mech_breakdown.items()]
        drug_str = f"Key drugs: {', '.join(drugs[:4])}" if drugs else "No named drugs identified"

        # Config-driven indication counts for portfolio
        ind_parts = []
        for cat in indication_cats:
            if cat.get("is_default"):
                continue
            pattern = cat.get("pattern", "")
            label = cat.get("label", "")
            if pattern:
                cat_c = sum(1 for _, t in sponsor_df.iterrows() if pattern in str(t.get("conditions_str", "")).lower())
                ind_parts.append(f"{label}: {cat_c}")
        ind_str = ", ".join(ind_parts) if ind_parts else ""

        elements.append(Paragraph(
            f"<b>{sponsor}</b> ({int(row['trials'])} trials) \u2014 "
            f"{', '.join(mech_parts)}. {drug_str}. {ind_str}",
            styles["BodySmall"],
        ))

    # Industry vs academic
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("Industry vs. Academic", styles["SubHeading"]))

    industry_df = trials_df[trials_df["is_industry"]]
    academic_df = trials_df[~trials_df["is_industry"]]
    split_data = [
        ["Metric", "Industry", "Academic"],
        ["Total trials", len(industry_df), len(academic_df)],
        ["Unique sponsors", industry_df["sponsor_normalized"].nunique(), academic_df["sponsor_normalized"].nunique()],
        ["Phase 3 trials", len(industry_df[industry_df["phase_normalized"] == "Phase 3"]),
         len(academic_df[academic_df["phase_normalized"] == "Phase 3"])],
        ["Mechanisms", industry_df["mechanism"].nunique(), academic_df["mechanism"].nunique()],
        ["Total enrollment", f"{int(industry_df['enrollment'].sum()):,}",
         f"{int(academic_df['enrollment'].sum()):,}"],
    ]
    elements.append(_make_wrapped_table(split_data, [1.8 * inch, 1.2 * inch, 1.2 * inch], text_cols={0}, styles=styles))

    # ==========================================
    # SPONSOR HIGHLIGHT SECTIONS (config-driven)
    # ==========================================

    for sp_spec in highlight_sponsors:
        sp_name = sp_spec["sponsor"]
        sp_title = sp_spec.get("section_title", f"{sp_name} Portfolio")
        disease_tag = f" {disease_short}" if disease_short else ""

        sp_trials = trials_df[trials_df["sponsor_normalized"] == sp_name]
        if len(sp_trials) == 0:
            continue

        elements.append(PageBreak())
        elements.append(Paragraph(f"{sp_title}{disease_tag}", styles["SectionHeading"]))
        elements.append(Paragraph(
            f"<b>{len(sp_trials)} active trials</b> from {sp_name}.",
            styles["ReportBody"],
        ))

        elements.append(Paragraph("Portfolio by Mechanism", styles["SubHeading"]))
        sp_mechs = sp_trials["mechanism"].value_counts()
        for mech, count in sp_mechs.items():
            mech_trials = sp_trials[sp_trials["mechanism"] == mech]
            drugs = _get_unique_drugs(mech_trials)
            phases = sorted(mech_trials["phase_normalized"].unique())
            drug_str = f": {', '.join(drugs)}" if drugs else ""
            elements.append(Paragraph(
                f"\u2022  <b>{mech}</b> ({count} trial{'s' if count > 1 else ''}){drug_str} \u2014 {', '.join(phases)}",
                styles["BulletItem"],
            ))

        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("Competitive Context", styles["SubHeading"]))
        for mech in sp_mechs.index:
            all_mech = trials_df[trials_df["mechanism"] == mech]
            sp_mech = sp_trials[sp_trials["mechanism"] == mech]
            other_sponsors = all_mech[all_mech["sponsor_normalized"] != sp_name]["sponsor_normalized"].nunique()
            elements.append(Paragraph(
                f"\u2022  <b>{mech}:</b> {sp_name} has {len(sp_mech)} of {len(all_mech)} total trials "
                f"(vs. {other_sponsors} other sponsor{'s' if other_sponsors != 1 else ''})",
                styles["BulletItem"],
            ))

        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("Complete Trial Listing", styles["SubHeading"]))
        sp_table = _build_trial_listing_table(sp_trials, styles, max_rows=25, include_mechanism=True)
        if sp_table:
            elements.append(sp_table)

    # ==========================================
    # ENROLLMENT / INVESTMENT SIGNALS
    # ==========================================

    elements.append(PageBreak())
    elements.append(Paragraph("Enrollment &amp; Investment Signals", styles["SectionHeading"]))
    elements.append(Paragraph(
        "Large enrollment signals significant investment and commercial intent.",
        styles["ReportBody"],
    ))

    large_trials = trials_df[trials_df["enrollment"].notna() & (trials_df["enrollment"] > 0)].sort_values("enrollment", ascending=False)
    if len(large_trials) > 0:
        elements.append(Paragraph("Largest Trials by Enrollment", styles["SubHeading"]))

        large_data = [["NCT ID", "Drug(s)", "Mechanism", "Sponsor", "Phase", "Enrollment"]]
        for _, trial in large_trials.head(15).iterrows():
            drugs = _get_drug_str(trial, max_len=35)
            large_data.append([
                trial["nct_id"], drugs, trial["mechanism"],
                trial["sponsor_normalized"], trial["phase_normalized"],
                f"{int(trial['enrollment']):,}",
            ])

        large_widths = [0.85 * inch, 1.3 * inch, 1.05 * inch, 1.1 * inch, 0.7 * inch, 0.65 * inch]
        elements.append(_make_wrapped_table(large_data, large_widths, text_cols={0, 1, 2, 3}, styles=styles))

    # Enrollment by mechanism
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("Total Enrollment by Mechanism", styles["SubHeading"]))

    mech_enrollment = trials_df.groupby("mechanism")["enrollment"].agg(["sum", "count", "mean"]).sort_values("sum", ascending=False)
    enroll_data = [["Mechanism", "Total Enrollment", "Trials", "Avg. per Trial"]]
    for mech, row_e in mech_enrollment.iterrows():
        total = f"{int(row_e['sum']):,}" if pd.notna(row_e["sum"]) else "\u2014"
        avg = f"{int(row_e['mean']):,}" if pd.notna(row_e["mean"]) else "\u2014"
        enroll_data.append([mech, total, int(row_e["count"]), avg])

    enroll_widths = [2.0 * inch, 1.0 * inch, 0.6 * inch, 0.9 * inch]
    elements.append(_make_wrapped_table(enroll_data, enroll_widths, text_cols={0}, styles=styles))

    # Recently initiated trials
    recent_starts = trials_df[trials_df["start_year"].notna()].copy()
    if len(recent_starts) > 0:
        current_year = now.year
        new_trials = recent_starts[recent_starts["start_year"] >= current_year - 1]
        if len(new_trials) > 0:
            elements.append(Spacer(1, 0.2 * inch))
            elements.append(Paragraph(
                f"Recently Initiated ({current_year - 1}\u2013{current_year})", styles["SubHeading"],
            ))
            elements.append(Paragraph(
                f"<b>{len(new_trials)} trials</b> started in {current_year - 1}\u2013{current_year}.",
                styles["BodySmall"],
            ))
            new_mechs = new_trials["mechanism"].value_counts()
            mech_parts = [f"{m} ({c})" for m, c in new_mechs.items()]
            elements.append(Paragraph(f"By mechanism: {', '.join(mech_parts)}", styles["BodySmall"]))

    # ==========================================
    # GEOGRAPHIC LANDSCAPE
    # ==========================================
    if "countries_str" in trials_df.columns and trials_df["countries_str"].str.len().sum() > 0:
        elements.append(PageBreak())
        elements.append(Paragraph("Geographic Landscape", styles["SectionHeading"]))
        elements.append(Spacer(1, 0.15 * inch))

        # Top countries
        all_countries = trials_df["countries_str"].dropna().str.split("; ").explode()
        all_countries = all_countries[all_countries.str.len() > 0]
        country_counts = all_countries.value_counts().head(15)

        if len(country_counts) > 0:
            geo_data = [["Country", "Trials"]]
            for country, count in country_counts.items():
                geo_data.append([str(country), str(count)])
            geo_widths = [2.5 * inch, 1.0 * inch]
            geo_table = _make_wrapped_table(geo_data, geo_widths, text_cols={0}, styles=styles)
            if geo_table:
                elements.append(geo_table)
                elements.append(Spacer(1, 0.15 * inch))

        # Region breakdown
        if "regions_str" in trials_df.columns:
            all_regions = trials_df["regions_str"].dropna().str.split("; ").explode()
            all_regions = all_regions[all_regions.str.len() > 0]
            region_counts = all_regions.value_counts()
            if len(region_counts) > 0:
                elements.append(Paragraph("Region Breakdown", styles["SubHeading"]))
                reg_data = [["Region", "Trials"]]
                for region, count in region_counts.items():
                    reg_data.append([str(region), str(count)])
                reg_widths = [2.5 * inch, 1.0 * inch]
                reg_table = _make_wrapped_table(reg_data, reg_widths, text_cols={0}, styles=styles)
                if reg_table:
                    elements.append(reg_table)
                    elements.append(Spacer(1, 0.15 * inch))

        # Multi-country stats
        if "n_countries" in trials_df.columns:
            n_multi = int((trials_df["n_countries"] > 1).sum())
            n_with_geo = int((trials_df["n_countries"] > 0).sum())
            avg_countries = trials_df.loc[trials_df["n_countries"] > 0, "n_countries"].mean()
            elements.append(Paragraph(
                f"<b>{n_with_geo}</b> trials with location data. "
                f"<b>{n_multi}</b> multi-country trials. "
                f"Average: <b>{avg_countries:.1f}</b> countries per trial.",
                styles["BodySmall"],
            ))

    # ==========================================
    # STUDY DESIGN ANALYSIS
    # ==========================================
    if "study_design_category" in trials_df.columns:
        elements.append(PageBreak())
        elements.append(Paragraph("Study Design Analysis", styles["SectionHeading"]))
        elements.append(Spacer(1, 0.15 * inch))

        design_counts = trials_df["study_design_category"].value_counts()
        design_data = [["Study Design", "Trials", "%"]]
        for design, count in design_counts.items():
            pct = f"{count / n_total * 100:.0f}%"
            design_data.append([str(design), str(count), pct])
        design_widths = [2.0 * inch, 0.8 * inch, 0.7 * inch]
        design_table = _make_wrapped_table(design_data, design_widths, text_cols={0}, styles=styles)
        if design_table:
            elements.append(design_table)
            elements.append(Spacer(1, 0.15 * inch))

        # % Double-blind by phase
        phase_order = ["Phase 1", "Phase 2", "Phase 3"]
        dblind_data = [["Phase", "Total", "Double-Blind", "% DB"]]
        for phase in phase_order:
            phase_df = trials_df[trials_df["phase_normalized"] == phase]
            if len(phase_df) > 0:
                n_db = int((phase_df["study_design_category"] == "RCT Double-Blind").sum())
                pct = f"{n_db / len(phase_df) * 100:.0f}%" if len(phase_df) > 0 else "0%"
                dblind_data.append([phase, str(len(phase_df)), str(n_db), pct])
        if len(dblind_data) > 1:
            elements.append(Paragraph("Double-Blind Rate by Phase", styles["SubHeading"]))
            db_widths = [1.2 * inch, 0.8 * inch, 1.0 * inch, 0.7 * inch]
            db_table = _make_wrapped_table(dblind_data, db_widths, text_cols={0}, styles=styles)
            if db_table:
                elements.append(db_table)

    # ==========================================
    # PHASE TRANSITION FUNNEL
    # ==========================================
    elements.append(PageBreak())
    elements.append(Paragraph("Phase Transition Funnel", styles["SectionHeading"]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        "Counts of trials by mechanism across phases indicate pipeline momentum.",
        styles["BodySmall"],
    ))
    elements.append(Spacer(1, 0.1 * inch))

    non_pharma = ["Non-pharmacological", "Unclassified", "Other Biologic", "Small Molecule (Other)"]
    pharma_df = trials_df[~trials_df["mechanism"].isin(non_pharma)]
    if len(pharma_df) > 0:
        funnel_data = [["Mechanism", "Ph 1", "Ph 2", "Ph 3", "Ph2→3 Ratio"]]
        mech_counts = pharma_df["mechanism"].value_counts()
        for mech in mech_counts.index[:12]:
            mdf = pharma_df[pharma_df["mechanism"] == mech]
            p1 = len(mdf[mdf["phase_normalized"].isin(["Phase 1", "Phase 1/2"])])
            p2 = len(mdf[mdf["phase_normalized"].isin(["Phase 2", "Phase 2/3"])])
            p3 = len(mdf[mdf["phase_normalized"].isin(["Phase 3", "Phase 3/4"])])
            ratio = f"{p3/p2:.1f}x" if p2 > 0 else "—"
            funnel_data.append([mech, str(p1), str(p2), str(p3), ratio])
        funnel_widths = [1.6 * inch, 0.6 * inch, 0.6 * inch, 0.6 * inch, 0.8 * inch]
        funnel_table = _make_wrapped_table(funnel_data, funnel_widths, text_cols={0}, styles=styles)
        if funnel_table:
            elements.append(funnel_table)

    # ==========================================
    # PHASE 3 ENDPOINT COMPARISON
    # ==========================================
    if "primary_endpoint" in trials_df.columns:
        p3_with_ep = trials_df[
            (trials_df["phase_normalized"].isin(["Phase 3", "Phase 3/4"])) &
            (trials_df["primary_endpoint"].str.len() > 0)
        ]
        if len(p3_with_ep) > 0:
            elements.append(PageBreak())
            elements.append(Paragraph("Phase 3 Endpoint Comparison", styles["SectionHeading"]))
            elements.append(Spacer(1, 0.15 * inch))

            ep_data = [["Mechanism", "Drug", "Primary Endpoint", "Timeframe"]]
            for _, trial in p3_with_ep.head(20).iterrows():
                drug = _get_drug_str(trial, max_len=25)
                ep = str(trial.get("primary_endpoint", ""))[:60]
                tf = str(trial.get("endpoint_timeframe", ""))[:25]
                ep_data.append([trial["mechanism"], drug, ep, tf])
            ep_widths = [1.1 * inch, 1.0 * inch, 2.6 * inch, 1.0 * inch]
            ep_table = _make_wrapped_table(ep_data, ep_widths, text_cols={0, 1, 2, 3}, styles=styles)
            if ep_table:
                elements.append(ep_table)

    # ==========================================
    # COMBINATION THERAPY LANDSCAPE
    # ==========================================
    if "is_combination" in trials_df.columns:
        combo_df = trials_df[trials_df["is_combination"] == True]
        if len(combo_df) > 0:
            elements.append(PageBreak())
            elements.append(Paragraph("Combination Therapy Landscape", styles["SectionHeading"]))
            elements.append(Spacer(1, 0.15 * inch))
            elements.append(Paragraph(
                f"<b>{len(combo_df)} trials</b> involve 2+ active drug interventions.",
                styles["BodySmall"],
            ))
            elements.append(Spacer(1, 0.1 * inch))

            # Combo by mechanism
            combo_mechs = combo_df["mechanism"].value_counts()
            combo_mech_data = [["Mechanism", "Combo Trials"]]
            for m, c in combo_mechs.head(10).items():
                combo_mech_data.append([str(m), str(c)])
            combo_mech_widths = [2.5 * inch, 1.0 * inch]
            combo_table = _make_wrapped_table(combo_mech_data, combo_mech_widths, text_cols={0}, styles=styles)
            if combo_table:
                elements.append(combo_table)
                elements.append(Spacer(1, 0.15 * inch))

            # Combo trial listing
            combo_list = _build_trial_listing_table(combo_df.head(15), styles, include_mechanism=True)
            if combo_list:
                elements.append(Paragraph("Combination Trials", styles["SubHeading"]))
                elements.append(combo_list)

    # ==========================================
    # PATIENT POPULATION ANALYSIS
    # ==========================================
    if "is_pediatric" in trials_df.columns:
        elements.append(PageBreak())
        elements.append(Paragraph("Patient Population Analysis", styles["SectionHeading"]))
        elements.append(Spacer(1, 0.15 * inch))

        n_ped = int(trials_df["is_pediatric"].sum())
        n_adult = n_total - n_ped
        elements.append(Paragraph(
            f"<b>Adult trials:</b> {n_adult} ({n_adult/n_total*100:.0f}%) | "
            f"<b>Pediatric/adolescent:</b> {n_ped} ({n_ped/n_total*100:.0f}%)",
            styles["BodySmall"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

        # Pediatric by mechanism
        ped_df = trials_df[trials_df["is_pediatric"] == True]
        if len(ped_df) > 0:
            ped_mechs = ped_df["mechanism"].value_counts()
            ped_data = [["Mechanism", "Pediatric Trials", "% of Mechanism"]]
            for mech, count in ped_mechs.head(10).items():
                total_mech = len(trials_df[trials_df["mechanism"] == mech])
                pct = f"{count/total_mech*100:.0f}%" if total_mech > 0 else "—"
                ped_data.append([str(mech), str(count), pct])
            ped_widths = [2.0 * inch, 1.0 * inch, 1.0 * inch]
            ped_table = _make_wrapped_table(ped_data, ped_widths, text_cols={0}, styles=styles)
            if ped_table:
                elements.append(Paragraph("Pediatric Trials by Mechanism", styles["SubHeading"]))
                elements.append(ped_table)

    # ==========================================
    # TRIAL ARMS & COMPARATOR ANALYSIS
    # ==========================================
    if "has_placebo_arm" in trials_df.columns:
        elements.append(PageBreak())
        elements.append(Paragraph("Trial Arms &amp; Comparator Analysis", styles["SectionHeading"]))
        elements.append(Spacer(1, 0.15 * inch))

        n_placebo = int(trials_df["has_placebo_arm"].sum())
        n_active = int(trials_df["has_active_comparator"].sum())
        n_h2h = int(trials_df["is_head_to_head"].sum())

        arm_data = [["Comparator Type", "Trials", "%"]]
        arm_data.append(["Placebo-controlled", str(n_placebo), f"{n_placebo/n_total*100:.0f}%"])
        arm_data.append(["Active comparator", str(n_active), f"{n_active/n_total*100:.0f}%"])
        arm_data.append(["Head-to-head", str(n_h2h), f"{n_h2h/n_total*100:.0f}%"])
        arm_widths = [2.0 * inch, 0.8 * inch, 0.7 * inch]
        arm_table = _make_wrapped_table(arm_data, arm_widths, text_cols={0}, styles=styles)
        if arm_table:
            elements.append(arm_table)
            elements.append(Spacer(1, 0.15 * inch))

        # Head-to-head listing
        h2h_df = trials_df[trials_df["is_head_to_head"] == True]
        if len(h2h_df) > 0:
            elements.append(Paragraph("Head-to-Head Trials", styles["SubHeading"]))
            h2h_table = _build_trial_listing_table(h2h_df.head(10), styles, include_mechanism=True)
            if h2h_table:
                elements.append(h2h_table)

    # ==========================================
    # BIOSIMILAR LANDSCAPE
    # ==========================================
    if "is_biosimilar" in trials_df.columns:
        bio_df = trials_df[trials_df["is_biosimilar"] == True]
        if len(bio_df) > 0:
            elements.append(PageBreak())
            elements.append(Paragraph("Biosimilar Landscape", styles["SectionHeading"]))
            elements.append(Spacer(1, 0.15 * inch))
            elements.append(Paragraph(
                f"<b>{len(bio_df)} biosimilar trials</b> detected across "
                f"{bio_df['mechanism'].nunique()} mechanism(s).",
                styles["BodySmall"],
            ))
            elements.append(Spacer(1, 0.1 * inch))

            bio_mechs = bio_df["mechanism"].value_counts()
            bio_data = [["Mechanism", "Biosimilar Trials", "Originator Trials"]]
            for mech, count in bio_mechs.items():
                orig = len(trials_df[(trials_df["mechanism"] == mech) & (~trials_df["is_biosimilar"])])
                bio_data.append([str(mech), str(count), str(orig)])
            bio_widths = [2.0 * inch, 1.0 * inch, 1.0 * inch]
            bio_table = _make_wrapped_table(bio_data, bio_widths, text_cols={0}, styles=styles)
            if bio_table:
                elements.append(bio_table)

    # ==========================================
    # WHITESPACE & UNMET NEEDS
    # ==========================================
    elements.append(PageBreak())
    elements.append(Paragraph("Whitespace &amp; Unmet Needs", styles["SectionHeading"]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(Paragraph(
        "Identifying gaps: mechanisms without Phase 3 programs, underserved indications.",
        styles["BodySmall"],
    ))
    elements.append(Spacer(1, 0.1 * inch))

    # Mechanisms without Phase 3
    pharma_mechs_all = pharma_df["mechanism"].unique() if len(pharma_df) > 0 else []
    p3_mechs = trials_df[trials_df["phase_normalized"].isin(["Phase 3", "Phase 3/4"])]["mechanism"].unique()
    no_p3 = [m for m in pharma_mechs_all if m not in p3_mechs]
    if no_p3:
        elements.append(Paragraph(
            f"<b>Mechanisms without Phase 3:</b> {', '.join(no_p3)}",
            styles["BodySmall"],
        ))
        elements.append(Spacer(1, 0.1 * inch))

    # Pediatric gaps
    if "is_pediatric" in trials_df.columns:
        ped_mechs = trials_df[trials_df["is_pediatric"] == True]["mechanism"].unique()
        no_ped = [m for m in pharma_mechs_all if m not in ped_mechs]
        if no_ped:
            elements.append(Paragraph(
                f"<b>Mechanisms with no pediatric trials:</b> {', '.join(no_ped)}",
                styles["BodySmall"],
            ))

    # ==========================================
    # REGULATORY SIGNALS
    # ==========================================
    if "is_fda_regulated_drug" in trials_df.columns or "has_dmc" in trials_df.columns:
        elements.append(Spacer(1, 0.3 * inch))
        elements.append(Paragraph("Regulatory Signals", styles["SectionHeading"]))
        elements.append(Spacer(1, 0.15 * inch))

        if "is_fda_regulated_drug" in trials_df.columns:
            n_fda = int(trials_df["is_fda_regulated_drug"].fillna(False).sum())
            elements.append(Paragraph(
                f"<b>FDA-regulated drug trials:</b> {n_fda} ({n_fda/n_total*100:.0f}%)",
                styles["BodySmall"],
            ))

        if "has_dmc" in trials_df.columns:
            n_dmc = int(trials_df["has_dmc"].fillna(False).sum())
            elements.append(Paragraph(
                f"<b>Trials with Data Safety Monitoring Committee:</b> {n_dmc} ({n_dmc/n_total*100:.0f}%)",
                styles["BodySmall"],
            ))

            # DSMB rate by phase
            phase_order = ["Phase 1", "Phase 2", "Phase 3"]
            dmc_data = [["Phase", "Total", "With DSMB", "% DSMB"]]
            for phase in phase_order:
                pf = trials_df[trials_df["phase_normalized"] == phase]
                if len(pf) > 0:
                    n_dmc_p = int(pf["has_dmc"].fillna(False).sum())
                    pct = f"{n_dmc_p/len(pf)*100:.0f}%"
                    dmc_data.append([phase, str(len(pf)), str(n_dmc_p), pct])
            if len(dmc_data) > 1:
                elements.append(Spacer(1, 0.1 * inch))
                dmc_widths = [1.2 * inch, 0.8 * inch, 0.8 * inch, 0.7 * inch]
                dmc_table = _make_wrapped_table(dmc_data, dmc_widths, text_cols={0}, styles=styles)
                if dmc_table:
                    elements.append(dmc_table)

    # ==========================================
    # FOOTER: Data Notes
    # ==========================================

    elements.append(Spacer(1, 0.4 * inch))
    elements.append(HRFlowable(width="100%", color=COLOR_MEDIUM_GRAY, thickness=1))
    elements.append(Spacer(1, 0.1 * inch))

    notes = [
        f"Source: ClinicalTrials.gov API v2 \u2014 Query date: {now.strftime('%Y-%m-%d')}",
    ]
    conditions = parameters.get("conditions", [])
    if conditions:
        notes.append(f"Conditions: {', '.join(conditions)}")
    statuses = parameters.get("statuses", [])
    if statuses:
        notes.append(f"Status filter: {', '.join(_format_status(s) for s in statuses)}")

    unclassified_count = len(trials_df[trials_df["mechanism"].isin(
        ["Unclassified", "Other Biologic", "Small Molecule (Other)"]
    )])
    if unclassified_count > 0:
        notes.append(f"Note: {unclassified_count} trials ({unclassified_count/n_total*100:.0f}%) "
                     f"with generic/unclassified mechanism")
    notes.append("Classification: automated pattern matching on intervention names and trial titles")
    notes.append("Completion dates are sponsor-reported estimates and may change")

    for note in notes:
        elements.append(Paragraph(note, styles["FooterText"]))

    # Build PDF
    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"{disease_name} Clinical Trial Landscape Report",
        author=f"ClinicalTrials.gov {disease_short + ' ' if disease_short else ''}Landscape Scanner",
    )

    doc.build(elements)

    print(f"\u2713 PDF report generated: {output_file}")
    return output_file


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _format_status(status):
    """Convert API status to readable format."""
    status_map = {
        "RECRUITING": "Recruiting",
        "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
        "NOT_YET_RECRUITING": "Not yet recruiting",
        "ENROLLING_BY_INVITATION": "Enrolling by invitation",
    }
    return status_map.get(status, status)


def _format_date(date_str):
    """Format date string, return dash if empty."""
    if not date_str or str(date_str) == "nan":
        return "\u2014"
    date_str = str(date_str).strip()
    if len(date_str) > 10:
        date_str = date_str[:10]
    return date_str if date_str else "\u2014"


def _time_to_readout(completion_date):
    """Calculate time from now to expected completion."""
    if not completion_date or str(completion_date) == "nan":
        return "\u2014"
    try:
        date_str = str(completion_date).strip()
        if len(date_str) >= 10:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        elif len(date_str) >= 7:
            dt = datetime.strptime(date_str[:7], "%Y-%m")
        elif len(date_str) >= 4:
            dt = datetime.strptime(date_str[:4], "%Y")
        else:
            return "\u2014"

        delta = dt - datetime.now()
        months = delta.days / 30.44
        if months < 0:
            return "Overdue"
        elif months < 1:
            return "<1 mo"
        elif months < 12:
            return f"~{int(months)} mo"
        else:
            return f"~{months/12:.1f} yr"
    except (ValueError, TypeError):
        return "\u2014"


def _get_upcoming_readouts(trials_df, months=18):
    """Get trials with completion dates within the next N months."""
    now = datetime.now()
    cutoff = now + timedelta(days=months * 30.44)
    upcoming = []

    for _, trial in trials_df.iterrows():
        cd = trial.get("completion_date", "")
        if not cd or str(cd) == "nan":
            continue
        try:
            date_str = str(cd).strip()
            if len(date_str) >= 10:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            elif len(date_str) >= 7:
                dt = datetime.strptime(date_str[:7], "%Y-%m")
            elif len(date_str) >= 4:
                dt = datetime.strptime(date_str[:4], "%Y")
            else:
                continue
            if now <= dt <= cutoff:
                upcoming.append(trial)
        except (ValueError, TypeError):
            continue

    if not upcoming:
        return pd.DataFrame()
    result = pd.DataFrame(upcoming)
    return result.sort_values("completion_date")


def _extract_indication(conditions_str, indication_cats=None):
    """Extract simplified indication label from conditions string.

    When *indication_cats* (list of dicts from config) is provided the
    matching is fully config-driven.  Otherwise falls back to generic
    "Intervention" label.
    """
    if not conditions_str or str(conditions_str) == "nan":
        return "\u2014"
    conditions_lower = str(conditions_str).lower()

    if indication_cats:
        matched = []
        default_label = "Other"
        for cat in indication_cats:
            if cat.get("is_default"):
                default_label = cat.get("label", "Other")
                continue
            pattern = cat.get("pattern", "")
            if pattern and pattern in conditions_lower:
                matched.append(cat.get("label", ""))
        if matched:
            return "+".join(matched) if len(matched) > 1 else matched[0]
        return default_label

    # Fallback when no config provided
    return "Other"


def _get_unique_drugs(df):
    """Extract unique meaningful drug names."""
    drugs = set()
    skip_terms = {"placebo", "saline", "sodium chloride", "standard of care",
                  "standard care", "usual care", "sham", "no intervention", "data collection"}
    for _, trial in df.iterrows():
        drugs_str = trial.get("drug_names_str", "")
        if not drugs_str or str(drugs_str) == "nan":
            continue
        for d in str(drugs_str).split(";"):
            d = d.strip()
            if d and not any(skip in d.lower() for skip in skip_terms):
                drugs.add(d)
    return sorted(drugs)


def _get_drug_str(trial, max_len=30):
    """Get drug string from trial, truncated."""
    drugs = trial.get("drug_names_str", "")
    if not drugs or str(drugs) == "nan":
        return "\u2014"
    drugs = str(drugs)
    if len(drugs) > max_len:
        drugs = drugs[:max_len - 3] + "..."
    return drugs


def _build_drug_pipeline_table(mech_df, styles, indication_cats=None):
    """Build a drug pipeline table for a mechanism subset with wrapped cells."""
    records = []
    seen = set()

    for _, trial in mech_df.iterrows():
        drugs_str = trial.get("drug_names_str", "")
        if not drugs_str or str(drugs_str) == "nan":
            continue
        for drug in str(drugs_str).split(";"):
            drug = drug.strip()
            if not drug:
                continue
            drug_lower = drug.lower()
            if any(skip in drug_lower for skip in ["placebo", "saline", "sodium chloride",
                                                     "standard", "sham", "no intervention"]):
                continue
            key = (drug_lower, trial.get("sponsor_normalized", ""))
            if key in seen:
                continue
            seen.add(key)
            records.append([
                drug, trial.get("sponsor_normalized", ""),
                trial.get("phase_normalized", ""),
                _format_status(trial.get("overall_status", "")),
                _extract_indication(trial.get("conditions_str", ""), indication_cats),
            ])

    if not records:
        return None

    data = [["Drug", "Sponsor", "Phase", "Status", "Ind."]] + records
    widths = [1.4 * inch, 1.3 * inch, 0.7 * inch, 1.1 * inch, 0.5 * inch]
    return _make_wrapped_table(data, widths, text_cols={0, 1, 3}, styles=styles)


def _build_trial_listing_table(df, styles, max_rows=15, include_mechanism=False):
    """Build a compact trial listing table with wrapped cells."""
    if len(df) == 0:
        return None

    if include_mechanism:
        header = ["NCT ID", "Title", "Mechanism", "Phase", "Status", "Enroll.", "Completion"]
    else:
        header = ["NCT ID", "Title", "Sponsor", "Phase", "Status", "Enroll.", "Completion"]

    data = [header]
    for _, trial in df.head(max_rows).iterrows():
        enrollment_str = f"{int(trial['enrollment']):,}" if pd.notna(trial["enrollment"]) and trial["enrollment"] > 0 else "\u2014"
        completion_str = _format_date(trial.get("completion_date", ""))

        if include_mechanism:
            data.append([
                trial["nct_id"], trial["brief_title"][:55],
                trial["mechanism"], trial["phase_normalized"],
                _format_status(trial["overall_status"]),
                enrollment_str, completion_str,
            ])
        else:
            data.append([
                trial["nct_id"], trial["brief_title"][:55],
                trial["sponsor_normalized"], trial["phase_normalized"],
                _format_status(trial["overall_status"]),
                enrollment_str, completion_str,
            ])

    # Columns: NCT(0), Title(1), Sponsor/Mech(2), Phase(3), Status(4), Enroll(5), Completion(6)
    # Text cols: NCT, Title, Sponsor/Mech, Status are long text
    widths = [0.8 * inch, 1.8 * inch, 0.95 * inch, 0.6 * inch, 0.7 * inch, 0.5 * inch, 0.6 * inch]
    return _make_wrapped_table(data, widths, text_cols={0, 1, 2, 4}, styles=styles)

