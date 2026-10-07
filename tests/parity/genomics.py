"""Fixed, hand-worked genomic inputs and public-library comparisons."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2] / "skills" / "genomics"
SCRIPTS = {
    "alignment": "genomics_alignment.py", "assembly": "genome_assembly.py",
    "cnv-calling": "genomics_cnv_calling.py", "epigenomics": "genomics_epigenomics.py",
    "phasing": "genomics_phasing.py", "qc": "genomics_qc.py",
    "sv-detection": "sv_detection.py", "variant-annotation": "variant_annotation.py",
    "variant-calling": "genomics_variant_calling.py", "vcf-operations": "genomics_vcf_operations.py",
}


def register(Case, Skill):
    registry = {}
    for suffix, script in SCRIPTS.items():
        name = "genomics-" + suffix
        source = next((ROOT / name / "data").glob("example.*"))
        def write_input(path, source=source):
            shutil.copyfile(source, path)
        cases = {"default": Case((), input=write_input)}
        if suffix == "cnv-calling":
            cases["bins"] = Case(("--method", "none"), input=write_input)
        if suffix == "vcf-operations":
            cases["filtered"] = Case(("--min-qual", "30", "--min-dp", "10"), input=write_input)
        registry[name] = Skill(str(Path("skills/genomics") / name / script),
                               "tests.parity.genomics:" + suffix.replace("-", "_"), cases)
    return registry


def _analyze(suffix, input_path, **kwargs):
    from skills._sdk.notebook import load_skill
    api = load_skill("genomics-" + suffix)
    reader = api.read_bins if suffix == "cnv-calling" else api.read_records
    result = api.analyze(reader(input_path), **kwargs)
    return result, api.run_info(result, keep=False)["summary"]


def alignment(case, *, input_path):
    result, summary = _analyze("alignment", input_path)
    return {"tables": {"alignment_stats.csv": result}, "summary": summary}


def assembly(case, *, input_path):
    import pandas as pd
    result, summary = _analyze("assembly", input_path)
    return {"tables": {"contig_lengths.csv": result, "assembly_metrics.csv": pd.DataFrame([summary])},
            "summary": summary}


def cnv_calling(case, *, input_path):
    result, summary = _analyze("cnv-calling", input_path, method="none" if case == "bins" else "cbs")
    per_chrom = result.groupby("chrom").agg(
        n_segments=("cn_state", "count"),
        n_gains=("cn_state", lambda x: x.isin(["gain", "amplification"]).sum()),
        n_losses=("cn_state", lambda x: x.isin(["loss", "deep_deletion"]).sum()),
        mean_log2=("log2_ratio", "mean")).reset_index()
    return {"tables": {"cnv_segments.csv": result, "cnv_per_chromosome.csv": per_chrom},
            "summary": summary}


def epigenomics(case, *, input_path):
    import pandas as pd
    result, summary = _analyze("epigenomics", input_path)
    chroms = summary.pop("peaks_per_chrom")
    return {"tables": {"peaks_summary.csv": result,
                       "peaks_per_chromosome.csv": pd.DataFrame(sorted(chroms.items()), columns=["chrom", "n_peaks"])},
            "summary": summary}


def phasing(case, *, input_path):
    import pandas as pd
    result, summary = _analyze("phasing", input_path)
    blocks = []
    phased = result[result.is_phased & result.is_het]
    for (chrom, phase_set), rows in phased.groupby(["chrom", "phase_set"], sort=False):
        if len(rows) >= 2:
            blocks.append({"chrom": chrom, "start": rows.pos.min(), "end": rows.pos.max(),
                           "length_bp": rows.pos.max() - rows.pos.min(), "n_variants": len(rows),
                           "phase_set": phase_set})
    return {"tables": {"phased_variants.csv": result, "phase_blocks.csv": pd.DataFrame(blocks)},
            "summary": summary}


def qc(case, *, input_path):
    import pandas as pd
    result, summary = _analyze("qc", input_path)
    qualities = summary.pop("per_base_quality")
    lengths = summary.pop("read_length_hist")
    return {"tables": {"qc_metrics.csv": result,
                       "per_base_quality.csv": pd.DataFrame({"position": range(1, len(qualities) + 1), "mean_quality": qualities}),
                       "read_length_distribution.csv": pd.DataFrame(sorted(lengths.items()), columns=["read_length", "count"])},
            "summary": summary}


def sv_detection(case, *, input_path):
    result, summary = _analyze("sv-detection", input_path)
    return {"tables": {"structural_variants.csv": result}, "summary": summary}


def variant_annotation(case, *, input_path):
    import pandas as pd
    result, summary = _analyze("variant-annotation", input_path)
    summary.pop("top_consequences")
    impacts = pd.DataFrame({"impact": ["HIGH", "MODERATE", "LOW", "MODIFIER"],
                           "count": [summary["n_" + name + "_impact"] for name in ["high", "moderate", "low", "modifier"]]})
    return {"tables": {"annotated_variants.csv": result, "impact_distribution.csv": impacts},
            "summary": summary}


def variant_calling(case, *, input_path):
    import pandas as pd
    result, summary = _analyze("variant-calling", input_path)
    chroms = summary.pop("variants_per_chrom")
    return {"tables": {"variants.csv": result,
                       "variants_per_chrom.csv": pd.DataFrame(sorted(chroms.items()), columns=["chrom", "n_variants"])},
            "summary": summary}


def vcf_operations(case, *, input_path):
    options = {"min_qual": 30, "min_dp": 10} if case == "filtered" else {}
    result, summary = _analyze("vcf-operations", input_path, **options)
    summary.pop("variants_per_chrom")
    return {"tables": {"variants.csv": result}, "summary": summary}
