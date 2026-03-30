"""
Generate 6-panel clinical trial landscape visualization (Step 3).

Creates:
1. Mechanism x Phase heatmap (seaborn heatmap in matplotlib subplot)
2. Top sponsors by trial count (plotnine horizontal bar)
3. Phase distribution stacked by mechanism (plotnine stacked bar)
4. Mechanism breakdown - total counts (plotnine bar)
5. Timeline: trial starts by year (plotnine line)
6. Industry vs Academic sponsor split (plotnine bar)

Uses plotnine with theme_prism() for all plots except heatmap.
Heatmap uses seaborn.heatmap() in a matplotlib axes for composite embedding.
Exports both PNG (300 DPI) and SVG with graceful fallback.
"""

import os
import sys

try:
    import pandas as pd
    import numpy as np
    from plotnine import *
    from plotnine_prism import theme_prism
    import seaborn as sns
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    import warnings
    warnings.filterwarnings('ignore')
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install plotnine plotnine-prism seaborn matplotlib pandas numpy")
    sys.exit(1)


try:
    from disease_config import auto_assign_colors, get_disease_name, get_disease_short
except ImportError:
    from scripts.disease_config import auto_assign_colors, get_disease_name, get_disease_short


# ============================================================
# MODULE-LEVEL COLOR MAP (set by _init_colors())
# ============================================================
_mechanism_colors = {}


def _init_colors(trials_df, config=None):
    """Initialize mechanism color map from config + data."""
    global _mechanism_colors
    mechanisms = trials_df["mechanism"].unique().tolist()
    _mechanism_colors = auto_assign_colors(mechanisms, config)


def _get_color(mechanism):
    """Get color for mechanism, with fallback."""
    return _mechanism_colors.get(mechanism, "#95A5A6")


def generate_landscape_plots(
    trials_df,
    output_dir="landscape_results",
    highlight_mechanism=None,
    highlight_sponsor=None,
    top_n_sponsors=15,
    config=None,
):
    """
    Generate 6-panel landscape visualization.

    Parameters
    ----------
    trials_df : pd.DataFrame
        Compiled trials from compile_trials().
    output_dir : str
        Output directory.
    highlight_mechanism : str or None
        Mechanism to highlight (e.g., "Anti-IL-23 (p19)").
    highlight_sponsor : str or None
        Sponsor to highlight (e.g., "Takeda").
    top_n_sponsors : int
        Number of top sponsors to show.

    Returns
    -------
    str
        Path to PNG file.

    Verification
    ------------
    Prints "✓ All landscape visualizations generated successfully!"
    """
    os.makedirs(output_dir, exist_ok=True)
    _init_colors(trials_df, config)

    print("\n" + "=" * 70)
    print("GENERATING LANDSCAPE VISUALIZATIONS")
    print("=" * 70 + "\n")

    # Panel 1: Mechanism x Phase heatmap
    print("1. Generating mechanism x phase heatmap...")
    fig_heatmap = _plot_mechanism_phase_heatmap(trials_df, highlight_mechanism)

    # Panel 2: Top sponsors
    print("2. Generating top sponsors bar chart...")
    p2 = _plot_top_sponsors(trials_df, top_n_sponsors, highlight_sponsor)

    # Panel 3: Phase distribution stacked by mechanism
    print("3. Generating phase distribution chart...")
    p3 = _plot_phase_stacked(trials_df)

    # Panel 4: Mechanism breakdown
    print("4. Generating mechanism breakdown chart...")
    p4 = _plot_mechanism_counts(trials_df, highlight_mechanism)

    # Panel 5: Timeline
    print("5. Generating trial timeline...")
    p5 = _plot_trial_timeline(trials_df)

    # Panel 6: Industry vs Academic
    print("6. Generating sponsor type chart...")
    p6 = _plot_sponsor_type(trials_df)

    # Save combined figure
    print("\n7. Compositing and saving...")
    disease_name = get_disease_name(config, default="Clinical Trial")
    png_path = _save_combined(
        fig_heatmap, p2, p3, p4, p5, p6,
        trials_df, output_dir, "landscape_overview",
        highlight_mechanism, disease_name,
    )

    print("\n✓ All landscape visualizations generated successfully!")
    print("=" * 70 + "\n")

    return png_path


def _plot_mechanism_phase_heatmap(trials_df, highlight_mechanism=None):
    """Panel 1: Mechanism x Phase cross-tabulation heatmap."""
    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4"]

    ct = pd.crosstab(trials_df["mechanism"], trials_df["phase_normalized"])
    ct = ct.reindex(columns=[p for p in phase_order if p in ct.columns], fill_value=0)

    # Sort rows by total descending
    ct["_total"] = ct.sum(axis=1)
    ct = ct.sort_values("_total", ascending=False)
    ct = ct.drop(columns=["_total"])

    # Drop rows with 0 total if any
    ct = ct[ct.sum(axis=1) > 0]

    fig, ax = plt.subplots(figsize=(8, max(4, len(ct) * 0.4 + 1)))

    sns.heatmap(
        ct,
        annot=True,
        fmt="d",
        cmap="YlOrRd",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Number of Trials", "shrink": 0.8},
        ax=ax,
    )

    ax.set_xlabel("Phase", fontsize=11, fontweight="bold")
    ax.set_ylabel("Mechanism", fontsize=11, fontweight="bold")
    ax.set_title("Mechanism × Phase Distribution", fontsize=13, fontweight="bold", pad=10)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=9)
    plt.setp(ax.get_yticklabels(), rotation=0, fontsize=9)

    # Highlight row for focus mechanism
    if highlight_mechanism and highlight_mechanism in ct.index:
        row_idx = list(ct.index).index(highlight_mechanism)
        ax.add_patch(plt.Rectangle(
            (0, row_idx), ct.shape[1], 1,
            fill=False, edgecolor="red", linewidth=3,
        ))

    plt.tight_layout()
    return fig


def _plot_top_sponsors(trials_df, top_n=15, highlight_sponsor=None):
    """Panel 2: Top sponsors by trial count (horizontal bar)."""
    sponsor_counts = (
        trials_df.groupby(["sponsor_normalized", "is_industry"])
        .size()
        .reset_index(name="count")
    )
    sponsor_counts = sponsor_counts.sort_values("count", ascending=False).head(top_n)

    # Truncate long names
    sponsor_counts["label"] = sponsor_counts["sponsor_normalized"].apply(
        lambda s: s[:28] + ".." if len(s) > 30 else s
    )

    # Color grouping
    def _color_group(row):
        if highlight_sponsor and highlight_sponsor.lower() in row["sponsor_normalized"].lower():
            return "Highlighted"
        return "Industry" if row["is_industry"] else "Academic / Other"

    sponsor_counts["color_group"] = sponsor_counts.apply(_color_group, axis=1)

    # Categorical order (bottom to top for coord_flip)
    sponsor_counts["label"] = pd.Categorical(
        sponsor_counts["label"],
        categories=sponsor_counts["label"].iloc[::-1].tolist(),
    )

    colors = {
        "Industry": "#2E86C1",
        "Academic / Other": "#95A5A6",
        "Highlighted": "#E74C3C",
    }
    # Only include colors that are present
    present_colors = {k: v for k, v in colors.items() if k in sponsor_counts["color_group"].values}

    return (
        ggplot(sponsor_counts, aes(x="label", y="count", fill="color_group"))
        + geom_col(color="white", size=0.3)
        + coord_flip()
        + scale_fill_manual(values=present_colors)
        + labs(title=f"Top {top_n} Sponsors by Trial Count", x="", y="Number of Trials", fill="")
        + theme_prism(base_size=10)
        + theme(figure_size=(8, 6), legend_position="bottom")
    )


def _plot_phase_stacked(trials_df):
    """Panel 3: Phase distribution with mechanism color stacking."""
    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4"]

    phase_mech = (
        trials_df.groupby(["phase_normalized", "mechanism"])
        .size()
        .reset_index(name="count")
    )

    # Filter to known phases
    phase_mech = phase_mech[phase_mech["phase_normalized"].isin(phase_order)]
    phase_mech["phase_normalized"] = pd.Categorical(
        phase_mech["phase_normalized"],
        categories=phase_order,
    )

    # Get mechanism colors present in data
    mechs_present = phase_mech["mechanism"].unique()
    colors = {m: _get_color(m) for m in mechs_present}

    return (
        ggplot(phase_mech, aes(x="phase_normalized", y="count", fill="mechanism"))
        + geom_col(color="white", size=0.3, position="stack")
        + scale_fill_manual(values=colors)
        + labs(title="Trials by Phase (Mechanism Breakdown)", x="Phase", y="Number of Trials", fill="Mechanism")
        + theme_prism(base_size=10)
        + theme(
            figure_size=(8, 6),
            legend_position="right",
            legend_text=element_text(size=7),
            legend_title=element_text(size=9),
            axis_text_x=element_text(rotation=45, ha="right"),
        )
    )


def _plot_mechanism_counts(trials_df, highlight_mechanism=None):
    """Panel 4: Total trial count per mechanism."""
    mech_counts = (
        trials_df["mechanism"]
        .value_counts()
        .reset_index()
    )
    mech_counts.columns = ["mechanism", "count"]

    mech_counts["label"] = pd.Categorical(
        mech_counts["mechanism"],
        categories=mech_counts["mechanism"].iloc[::-1].tolist(),
    )

    # Highlight logic
    mech_counts["is_highlight"] = mech_counts["mechanism"].apply(
        lambda m: "Highlighted" if m == highlight_mechanism else "Normal"
    )

    colors = {m: _get_color(m) for m in mech_counts["mechanism"]}

    return (
        ggplot(mech_counts, aes(x="label", y="count", fill="mechanism"))
        + geom_col(color="white", size=0.3)
        + coord_flip()
        + scale_fill_manual(values=colors)
        + labs(title="Total Trials by Mechanism", x="", y="Number of Trials")
        + theme_prism(base_size=10)
        + theme(figure_size=(8, 6), legend_position="none")
    )


def _plot_trial_timeline(trials_df):
    """Panel 5: Trial start dates by year, lines per top mechanism."""
    df = trials_df[trials_df["start_year"].notna()].copy()
    if df.empty:
        # Return empty plot
        return (
            ggplot(pd.DataFrame({"x": [0], "y": [0]}), aes("x", "y"))
            + geom_blank()
            + labs(title="Trial Timeline (no date data available)")
            + theme_prism(base_size=10)
            + theme(figure_size=(8, 6))
        )

    df["start_year"] = df["start_year"].astype(int)

    # Get top mechanisms by count for timeline
    top_mechs = df["mechanism"].value_counts().head(6).index.tolist()
    df_top = df[df["mechanism"].isin(top_mechs)]

    timeline = (
        df_top.groupby(["start_year", "mechanism"])
        .size()
        .reset_index(name="count")
    )

    colors = {m: _get_color(m) for m in top_mechs}

    return (
        ggplot(timeline, aes(x="start_year", y="count", color="mechanism"))
        + geom_line(size=1.2)
        + geom_point(size=2.5)
        + scale_color_manual(values=colors)
        + labs(
            title="Trial Starts by Year (Top 6 Mechanisms)",
            x="Year",
            y="New Trials",
            color="Mechanism",
        )
        + theme_prism(base_size=10)
        + theme(
            figure_size=(8, 6),
            legend_position="right",
            legend_text=element_text(size=7),
            legend_title=element_text(size=9),
        )
    )


def _plot_sponsor_type(trials_df):
    """Panel 6: Industry vs Academic/NIH/Other breakdown."""
    type_counts = trials_df["sponsor_class"].value_counts().reset_index()
    type_counts.columns = ["sponsor_type", "count"]

    # Map to friendlier labels
    label_map = {
        "INDUSTRY": "Industry",
        "NIH": "NIH",
        "FED": "Federal",
        "OTHER": "Academic / Other",
        "OTHER_GOV": "Other Govt",
        "NETWORK": "Network",
        "INDIV": "Individual",
    }
    type_counts["label"] = type_counts["sponsor_type"].map(label_map).fillna(type_counts["sponsor_type"])

    type_counts["label"] = pd.Categorical(
        type_counts["label"],
        categories=type_counts["label"].tolist(),
    )

    fill_colors = {
        "Industry": "#2E86C1",
        "NIH": "#27AE60",
        "Federal": "#27AE60",
        "Academic / Other": "#95A5A6",
        "Other Govt": "#7DCEA0",
        "Network": "#F5B041",
        "Individual": "#D5D8DC",
    }
    present_colors = {k: v for k, v in fill_colors.items() if k in type_counts["label"].values}

    return (
        ggplot(type_counts, aes(x="label", y="count", fill="label"))
        + geom_col(color="white", size=0.5)
        + scale_fill_manual(values=present_colors)
        + labs(title="Sponsor Type Distribution", x="", y="Number of Trials")
        + theme_prism(base_size=10)
        + theme(
            figure_size=(8, 6),
            legend_position="none",
            axis_text_x=element_text(rotation=45, ha="right"),
        )
    )


def _save_combined(fig_heatmap, p2, p3, p4, p5, p6, trials_df, output_dir, base_name, highlight_mechanism, disease_name="Clinical Trial"):
    """Save 6-panel combined figure as PNG and SVG.

    Panel 1 (heatmap) is already a matplotlib figure.
    Panels 2-6 are plotnine plots rendered via draw().
    """
    # Create 3x2 composite figure
    fig = plt.figure(figsize=(20, 24))
    gs = GridSpec(3, 2, figure=fig, hspace=0.3, wspace=0.25)

    panels = [
        (fig_heatmap, gs[0, 0]),  # Panel 1: heatmap (already mpl fig)
        (p2, gs[0, 1]),           # Panel 2: sponsors
        (p3, gs[1, 0]),           # Panel 3: phase stacked
        (p4, gs[1, 1]),           # Panel 4: mechanism counts
        (p5, gs[2, 0]),           # Panel 5: timeline
        (p6, gs[2, 1]),           # Panel 6: sponsor type
    ]

    for i, (panel, gs_slot) in enumerate(panels):
        ax = fig.add_subplot(gs_slot)

        if i == 0:
            # Panel 1 is already a matplotlib figure — render to buffer
            panel.canvas.draw()
            w, h = panel.canvas.get_width_height()
            buf = np.frombuffer(panel.canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4)
            ax.imshow(buf)
            ax.axis("off")
            plt.close(panel)
        else:
            # Plotnine panels: draw and render to buffer
            try:
                pfig = panel.draw()
                pfig.set_size_inches(8, 6)
                pfig.set_dpi(200)
                pfig.canvas.draw()
                w, h = pfig.canvas.get_width_height()
                buf = np.frombuffer(pfig.canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4)
                ax.imshow(buf)
                ax.axis("off")
                plt.close(pfig)
            except Exception as e:
                ax.text(0.5, 0.5, f"Panel {i+1} error:\n{e}",
                        ha="center", va="center", transform=ax.transAxes, fontsize=10)
                ax.axis("off")

    # Title
    n_trials = len(trials_df)
    n_mechanisms = trials_df["mechanism"].nunique()
    n_sponsors = trials_df["sponsor_normalized"].nunique()
    highlight_text = f" | Focus: {highlight_mechanism}" if highlight_mechanism else ""

    fig.suptitle(
        f"{disease_name} Clinical Trial Landscape\n"
        f"{n_trials} trials, {n_mechanisms} mechanisms, {n_sponsors} sponsors{highlight_text}",
        fontsize=18, fontweight="bold", y=0.995,
    )

    # Save PNG
    png_path = os.path.join(output_dir, f"{base_name}.png")
    fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"   Saved: {png_path}")

    # Save SVG
    svg_path = os.path.join(output_dir, f"{base_name}.svg")
    try:
        fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
        print(f"   Saved: {svg_path}")
    except Exception:
        try:
            from matplotlib.backends.backend_svg import FigureCanvasSVG
            canvas = FigureCanvasSVG(fig)
            with open(svg_path, "w") as f:
                canvas.print_svg(f)
            print(f"   Saved: {svg_path}")
        except Exception:
            print("   (SVG export failed - PNG available)")

    plt.close(fig)
    return png_path


# ============================================================
# SUPPLEMENTARY VISUALIZATIONS (Phase 2I)
# ============================================================

def generate_supplementary_plots(
    trials_df,
    output_dir="landscape_results",
    config=None,
):
    """
    Generate supplementary 4-panel visualization with new Phase 2 data.

    Creates:
    1. Geographic bar chart — top 15 countries
    2. Study design stacked bar — RCT/open-label/observational by phase
    3. Enrollment box plot — by mechanism (using enrollment_clean)
    4. Phase transition funnel — bar chart: Phase 1/2/3 per mechanism

    Parameters
    ----------
    trials_df : pd.DataFrame
        Compiled trials with Phase 2B columns.
    output_dir : str
        Output directory.

    Returns
    -------
    str or None
        Path to PNG file, or None if insufficient data.
    """
    os.makedirs(output_dir, exist_ok=True)
    _init_colors(trials_df, config)

    disease_name = get_disease_name(config, default="Clinical Trial")
    disease_short = get_disease_short(config, default="")

    print("\n" + "=" * 70)
    print("GENERATING SUPPLEMENTARY VISUALIZATIONS")
    print("=" * 70 + "\n")

    has_geo = "countries_str" in trials_df.columns and trials_df["countries_str"].str.len().sum() > 0
    has_design = "study_design_category" in trials_df.columns
    has_enrollment_clean = "enrollment_clean" in trials_df.columns
    non_pharma = ["Non-pharmacological", "Unclassified", "Other Biologic", "Small Molecule (Other)"]
    pharma_df = trials_df[~trials_df["mechanism"].isin(non_pharma)]

    if not (has_geo or has_design or has_enrollment_clean):
        print("  Insufficient data for supplementary plots (no Phase 2B columns).")
        print("  Skipping supplementary visualizations.\n")
        return None

    panels = []

    # Panel 1: Geographic bar chart
    print("1. Generating geographic bar chart...")
    if has_geo:
        p1 = _plot_geographic_bar(trials_df)
    else:
        p1 = _empty_panel("Geographic Data Not Available")
    panels.append(p1)

    # Panel 2: Study design by phase
    print("2. Generating study design chart...")
    if has_design:
        p2 = _plot_study_design(trials_df)
    else:
        p2 = _empty_panel("Study Design Data Not Available")
    panels.append(p2)

    # Panel 3: Enrollment box plot
    print("3. Generating enrollment box plot...")
    if has_enrollment_clean:
        p3 = _plot_enrollment_box(trials_df, pharma_df)
    else:
        p3 = _empty_panel("Clean Enrollment Data Not Available")
    panels.append(p3)

    # Panel 4: Phase transition funnel
    print("4. Generating phase transition funnel...")
    if len(pharma_df) > 0:
        p4 = _plot_phase_funnel(pharma_df)
    else:
        p4 = _empty_panel("No Pharmacological Trials")
    panels.append(p4)

    # Compose 2x2 figure
    print("\n5. Compositing and saving supplementary figure...")
    fig = plt.figure(figsize=(20, 16))
    gs = GridSpec(2, 2, figure=fig, hspace=0.3, wspace=0.25)

    for i, (panel, gs_slot) in enumerate(zip(panels, [gs[0,0], gs[0,1], gs[1,0], gs[1,1]])):
        ax = fig.add_subplot(gs_slot)
        try:
            pfig = panel.draw()
            pfig.set_size_inches(8, 6)
            pfig.set_dpi(200)
            pfig.canvas.draw()
            w, h = pfig.canvas.get_width_height()
            buf = np.frombuffer(pfig.canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4)
            ax.imshow(buf)
            ax.axis("off")
            plt.close(pfig)
        except Exception as e:
            ax.text(0.5, 0.5, f"Panel {i+1} error:\n{e}",
                    ha="center", va="center", transform=ax.transAxes, fontsize=10)
            ax.axis("off")

    title_prefix = f"{disease_short} " if disease_short else ""
    fig.suptitle(
        f"{title_prefix}Landscape — Supplementary Analysis\n"
        "Geographic · Study Design · Enrollment · Phase Funnel",
        fontsize=16, fontweight="bold", y=0.995,
    )

    # Save PNG
    png_path = os.path.join(output_dir, "landscape_supplementary.png")
    fig.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"   Saved: {png_path}")

    # Save SVG
    svg_path = os.path.join(output_dir, "landscape_supplementary.svg")
    try:
        fig.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
        print(f"   Saved: {svg_path}")
    except Exception:
        print("   (SVG export failed - PNG available)")

    plt.close(fig)

    print("\n✓ Supplementary visualizations generated successfully!")
    print("=" * 70 + "\n")

    return png_path


def _empty_panel(message):
    """Create an empty plotnine panel with a message."""
    return (
        ggplot(pd.DataFrame({"x": [0], "y": [0]}), aes("x", "y"))
        + geom_blank()
        + labs(title=message)
        + theme_prism(base_size=10)
        + theme(figure_size=(8, 6))
    )


def _plot_geographic_bar(trials_df, top_n=15):
    """Panel 1: Top countries by trial count (horizontal bar)."""
    all_countries = trials_df["countries_str"].dropna().str.split("; ").explode()
    all_countries = all_countries[all_countries.str.len() > 0]
    country_counts = all_countries.value_counts().head(top_n).reset_index()
    country_counts.columns = ["country", "count"]

    country_counts["country"] = pd.Categorical(
        country_counts["country"],
        categories=country_counts["country"].iloc[::-1].tolist(),
    )

    return (
        ggplot(country_counts, aes(x="country", y="count"))
        + geom_col(fill="#2E86C1", color="white", size=0.3)
        + coord_flip()
        + labs(title=f"Top {top_n} Countries by Trial Presence", x="", y="Number of Trials")
        + theme_prism(base_size=10)
        + theme(figure_size=(8, 6))
    )


def _plot_study_design(trials_df):
    """Panel 2: Study design stacked bar by phase."""
    phase_order = ["Phase 1", "Phase 1/2", "Phase 2", "Phase 2/3", "Phase 3", "Phase 4"]
    df = trials_df[trials_df["phase_normalized"].isin(phase_order)].copy()

    if len(df) == 0:
        return _empty_panel("No Phase-Assigned Trials")

    design_phase = (
        df.groupby(["phase_normalized", "study_design_category"])
        .size()
        .reset_index(name="count")
    )
    design_phase["phase_normalized"] = pd.Categorical(
        design_phase["phase_normalized"],
        categories=phase_order,
    )

    design_colors = {
        "RCT Double-Blind": "#2E86C1",
        "RCT Single-Blind": "#5DADE2",
        "RCT Open-Label": "#F39C12",
        "RCT (Other)": "#F5B041",
        "Non-Randomized": "#E74C3C",
        "Single-Arm": "#95A5A6",
        "Observational": "#BDC3C7",
        "Other Design": "#D5D8DC",
    }
    present_colors = {k: v for k, v in design_colors.items()
                      if k in design_phase["study_design_category"].values}

    return (
        ggplot(design_phase, aes(x="phase_normalized", y="count", fill="study_design_category"))
        + geom_col(color="white", size=0.3, position="stack")
        + scale_fill_manual(values=present_colors)
        + labs(title="Study Design by Phase", x="Phase", y="Trials", fill="Design")
        + theme_prism(base_size=10)
        + theme(
            figure_size=(8, 6),
            legend_position="right",
            legend_text=element_text(size=7),
            axis_text_x=element_text(rotation=45, ha="right"),
        )
    )


def _plot_enrollment_box(trials_df, pharma_df):
    """Panel 3: Enrollment distribution by mechanism (box plot)."""
    enroll_col = "enrollment_clean" if "enrollment_clean" in pharma_df.columns else "enrollment"

    df = pharma_df[[enroll_col, "mechanism"]].dropna(subset=[enroll_col]).copy()
    df = df[df[enroll_col] > 0]

    if len(df) == 0:
        return _empty_panel("No Enrollment Data")

    # Top mechanisms by count
    top_mechs = df["mechanism"].value_counts().head(8).index.tolist()
    df = df[df["mechanism"].isin(top_mechs)]

    df["mechanism"] = pd.Categorical(
        df["mechanism"],
        categories=df.groupby("mechanism")[enroll_col].median().sort_values(ascending=False).index.tolist(),
    )

    mech_colors = {m: _get_color(m) for m in top_mechs}

    return (
        ggplot(df, aes(x="mechanism", y=enroll_col, fill="mechanism"))
        + geom_boxplot(outlier_alpha=0.3, show_legend=False)
        + scale_fill_manual(values=mech_colors)
        + scale_y_log10()
        + labs(title="Enrollment Distribution by Mechanism", x="", y="Enrollment (log scale)")
        + theme_prism(base_size=10)
        + theme(
            figure_size=(8, 6),
            axis_text_x=element_text(rotation=45, ha="right", size=8),
        )
    )


def _plot_phase_funnel(pharma_df):
    """Panel 4: Phase transition funnel per mechanism."""
    mechs = pharma_df["mechanism"].value_counts().head(8).index.tolist()

    records = []
    for mech in mechs:
        mdf = pharma_df[pharma_df["mechanism"] == mech]
        for phase_label, phase_list in [
            ("Phase 1", ["Phase 1", "Phase 1/2"]),
            ("Phase 2", ["Phase 2", "Phase 2/3"]),
            ("Phase 3", ["Phase 3", "Phase 3/4"]),
        ]:
            count = len(mdf[mdf["phase_normalized"].isin(phase_list)])
            records.append({"mechanism": mech, "phase": phase_label, "count": count})

    df = pd.DataFrame(records)
    df["phase"] = pd.Categorical(df["phase"], categories=["Phase 1", "Phase 2", "Phase 3"])

    mech_colors = {m: _get_color(m) for m in mechs}

    return (
        ggplot(df, aes(x="phase", y="count", fill="mechanism"))
        + geom_col(color="white", size=0.3, position="dodge")
        + scale_fill_manual(values=mech_colors)
        + labs(title="Phase Transition Funnel", x="Phase", y="Trials", fill="Mechanism")
        + theme_prism(base_size=10)
        + theme(
            figure_size=(8, 6),
            legend_position="right",
            legend_text=element_text(size=7),
        )
    )

