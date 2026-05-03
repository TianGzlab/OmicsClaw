from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml


UPSTREAM_GITHUB_R_PACKAGE_DESCRIPTIONS = {
    "spacexr": """
Package: spacexr
Version: 2.2.1
Depends: R (>= 3.5.0)
Imports:
    readr, ggplot2, pals, Matrix, parallel, doParallel, foreach, quadprog,
    tibble, dplyr, reshape2, knitr, rmarkdown, fields, mgcv, CompQuadForm,
    Rfast, locfdr, metafor, data.table
""",
    "CARD": """
Package: CARD
Version: 1.1
Imports: Rcpp (>= 1.0.7), RcppArmadillo, SingleCellExperiment,
    SummarizedExperiment, methods, MCMCpack, fields, wrMisc, concaveman, sp,
    dplyr, sf, Matrix, RANN, ggplot2, reshape2, RColorBrewer, scatterpie,
    grDevices, ggcorrplot, stats, nnls, pbmcapply, RcppML, NMF,
    spatstat.random, gtools
LinkingTo: Rcpp, RcppArmadillo
""",
    "CellChat": """
Package: CellChat
Version: 2.2.0.9001
Depends: R (>= 3.6.0), dplyr, igraph, ggplot2
Imports:
    future, future.apply, pbapply, irlba, NMF (>= 0.23.0), ggalluvial,
    stringr, svglite, Matrix, ggrepel, circlize (>= 0.4.12), RColorBrewer,
    cowplot, methods, ComplexHeatmap, RSpectra, Rcpp, reticulate, scales, sna,
    reshape2, FNN, shape, BiocGenerics, magrittr, patchwork, colorspace, plyr,
    ggpubr, ggnetwork, BiocNeighbors, plotly, shiny, bslib, collapse
LinkingTo: Rcpp, RcppEigen
""",
    "numbat": """
Package: numbat
Version: 1.5.2
Depends: R (>= 4.1.0), Matrix
Imports:
    ape, caTools, data.table, dendextend, dplyr (>= 1.1.1), GenomicRanges,
    ggplot2, ggraph, ggtree, glue, hahmmr, igraph, IRanges, logger, magrittr,
    methods, optparse, parallel, parallelDist, patchwork, purrr, Rcpp,
    RhpcBLASctl, R.utils, scales, scistreer (>= 1.1.0), stats4, stringr,
    tibble, tidygraph, tidyr (>= 1.3.0), vcfR, zoo
LinkingTo: Rcpp, RcppArmadillo, roptim
""",
    "SPARK": """
Package: SPARK
Version: 1.1.1
Depends: R (>= 3.4.0), methods
Imports: Rcpp (>= 1.0.5), foreach, doParallel, parallel, Matrix, CompQuadForm,
    matlab, pracma
LinkingTo: Rcpp, RcppArmadillo
""",
    "DoubletFinder": """
Package: DoubletFinder
Version: 2.0.6
Depends: R (>= 4.0.0)
Imports: fields, KernSmooth, parallel, ROCR, Seurat, SeuratObject
""",
}


TIER3_CRAN_PREFLIGHT_R_PACKAGE_DESCRIPTIONS = {
    "hahmmr": """
Package: hahmmr
Version: 1.0.0
Depends: R (>= 4.1.0)
Imports: data.table, dplyr, GenomicRanges, ggplot2, glue, IRanges, methods,
    patchwork, Rcpp, stringr, tibble, zoo
LinkingTo: Rcpp, RcppArmadillo, roptim
""",
    "scistreer": """
Package: scistreer
Version: 1.2.1
Depends: R (>= 4.1.0)
Imports: ape, dplyr, ggplot2, ggtree, igraph, parallelDist, patchwork,
    phangorn, Rcpp, reshape2, RcppParallel, RhpcBLASctl, stringr, tidygraph
LinkingTo: Rcpp, RcppArmadillo, RcppParallel
""",
}


BASE_R_PACKAGES = {
    "grDevices",
    "Matrix",
    "methods",
    "parallel",
    "R",
    "stats",
    "stats4",
}


BIOCONDUCTOR_CONDA_PACKAGES = {
    "BiocGenerics": "bioconductor-biocgenerics",
    "BiocNeighbors": "bioconductor-biocneighbors",
    "ComplexHeatmap": "bioconductor-complexheatmap",
    "GenomicRanges": "bioconductor-genomicranges",
    "ggtree": "bioconductor-ggtree",
    "IRanges": "bioconductor-iranges",
    "SingleCellExperiment": "bioconductor-singlecellexperiment",
    "SummarizedExperiment": "bioconductor-summarizedexperiment",
}


CRAN_CONDA_PACKAGE_OVERRIDES = {
    "CompQuadForm": "r-compquadform",
    "KernSmooth": "r-kernsmooth",
    "NMF": "r-nmf",
    "RANN": "r-rann",
    "RColorBrewer": "r-rcolorbrewer",
    "Rcpp": "r-rcpp",
    "RcppArmadillo": "r-rcpparmadillo",
    "RcppEigen": "r-rcppeigen",
    "RcppML": "r-rcppml",
    "RcppParallel": "r-rcppparallel",
    "Rfast": "r-rfast",
    "RhpcBLASctl": "r-rhpcblasctl",
    "ROCR": "r-rocr",
    "RSpectra": "r-rspectra",
    "R.utils": "r-r.utils",
}


TIER3_CRAN_PREFLIGHT_PACKAGES = {
    "hahmmr",
    "NMF",
    "scistreer",
    "wrMisc",
}


@pytest.fixture(autouse=True)
def _default_subprocess_setup_tests_to_cpu_backend(monkeypatch):
    monkeypatch.setenv("OMICSCLAW_TORCH_BACKEND", "cpu")


def _parse_description_fields(description: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_field: str | None = None
    for line in description.splitlines():
        if re.match(r"^[A-Za-z][A-Za-z0-9.]*:", line):
            current_field, value = line.split(":", 1)
            fields[current_field] = value.strip()
        elif current_field:
            fields[current_field] += " " + line.strip()
    return fields


def _parse_r_package_list(spec: str) -> set[str]:
    packages: set[str] = set()
    for raw_part in spec.split(","):
        name = re.sub(r"\s*\([^)]*\)", "", raw_part).strip()
        if name:
            packages.add(name)
    return packages


def _required_r_packages(description: str) -> set[str]:
    fields = _parse_description_fields(description)
    packages: set[str] = set()
    for field in ("Depends", "Imports", "LinkingTo"):
        packages.update(_parse_r_package_list(fields.get(field, "")))
    package_name = fields.get("Package")
    return {pkg for pkg in packages if pkg not in BASE_R_PACKAGES and pkg != package_name}


def _conda_package_name(r_package: str) -> str:
    return (
        BIOCONDUCTOR_CONDA_PACKAGES.get(r_package)
        or CRAN_CONDA_PACKAGE_OVERRIDES.get(r_package)
        or f"r-{r_package.lower()}"
    )


def test_environment_yml_preinstalls_card_cran_spatial_dependencies():
    repo_root = Path(__file__).resolve().parents[1]
    env_yml = yaml.safe_load((repo_root / "environment.yml").read_text(encoding="utf-8"))
    dependencies = {
        dep.lower()
        for dep in env_yml["dependencies"]
        if isinstance(dep, str)
    }

    assert {"r-units", "r-sf", "r-concaveman"} <= dependencies


def test_environment_yml_preinstalls_tier3_github_r_direct_dependencies():
    repo_root = Path(__file__).resolve().parents[1]
    env_yml = yaml.safe_load((repo_root / "environment.yml").read_text(encoding="utf-8"))
    dependencies = {
        dep.split("=")[0].lower()
        for dep in env_yml["dependencies"]
        if isinstance(dep, str)
    }

    expected = {
        "bioconductor-biocgenerics",
        "bioconductor-biocneighbors",
        "bioconductor-complexheatmap",
        "bioconductor-genomicranges",
        "bioconductor-ggtree",
        "bioconductor-iranges",
        "bioconductor-summarizedexperiment",
        "r-ape",
        "r-bslib",
        "r-catools",
        "r-circlize",
        "r-colorspace",
        "r-compquadform",
        "r-collapse",
        "r-cowplot",
        "r-data.table",
        "r-dendextend",
        "r-doparallel",
        "r-fields",
        "r-fnn",
        "r-foreach",
        "r-future",
        "r-future.apply",
        "r-ggalluvial",
        "r-ggcorrplot",
        "r-ggnetwork",
        "r-ggpubr",
        "r-ggraph",
        "r-ggrepel",
        "r-glue",
        "r-gtools",
        "r-igraph",
        "r-irlba",
        "r-kernsmooth",
        "r-knitr",
        "r-locfdr",
        "r-logger",
        "r-magrittr",
        "r-matlab",
        "r-mcmcpack",
        "r-metafor",
        "r-mgcv",
        "r-nnls",
        "r-optparse",
        "r-pals",
        "r-paralleldist",
        "r-patchwork",
        "r-pbapply",
        "r-pbmcapply",
        "r-phangorn",
        "r-plotly",
        "r-plyr",
        "r-pracma",
        "r-purrr",
        "r-quadprog",
        "r-r.utils",
        "r-rann",
        "r-rcolorbrewer",
        "r-rcpp",
        "r-rcpparmadillo",
        "r-rcppeigen",
        "r-rcppparallel",
        "r-rcppml",
        "r-readr",
        "r-reshape2",
        "r-reticulate",
        "r-rfast",
        "r-rhpcblasctl",
        "r-rmarkdown",
        "r-rocr",
        "r-roptim",
        "r-rspectra",
        "r-scales",
        "r-scatterpie",
        "r-seuratobject",
        "r-shape",
        "r-shiny",
        "r-sna",
        "r-sp",
        "r-spatstat.random",
        "r-stringr",
        "r-svglite",
        "r-tibble",
        "r-tidygraph",
        "r-tidyr",
        "r-vcfr",
        "r-zoo",
    }
    assert expected <= dependencies
    assert "r-wrmisc" not in dependencies


def test_tier3_github_r_package_required_dependencies_are_preflighted():
    repo_root = Path(__file__).resolve().parents[1]
    env_yml = yaml.safe_load((repo_root / "environment.yml").read_text(encoding="utf-8"))
    conda_dependencies = {
        dep.split("=")[0].lower()
        for dep in env_yml["dependencies"]
        if isinstance(dep, str)
    }
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")
    cran_preflight_calls = {
        package
        for package in TIER3_CRAN_PREFLIGHT_PACKAGES
        if f'ensure_cran_package("{package}' in setup_script
    }

    missing: dict[str, list[str]] = {}
    for package_name, description in UPSTREAM_GITHUB_R_PACKAGE_DESCRIPTIONS.items():
        package_missing = []
        for required_package in sorted(_required_r_packages(description), key=str.lower):
            if required_package in cran_preflight_calls:
                continue
            if _conda_package_name(required_package).lower() not in conda_dependencies:
                package_missing.append(required_package)
        if package_missing:
            missing[package_name] = package_missing

    assert missing == {}


def test_setup_env_github_roots_match_audited_package_set():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")

    assert "github_roots <- list(" in setup_script
    for package_name in UPSTREAM_GITHUB_R_PACKAGE_DESCRIPTIONS:
        assert f'c("{package_name}",' in setup_script
    assert "for (pkg in github_roots)" in setup_script
    assert "ensure_github_package(pkg[1], pkg[2])" in setup_script


def test_tier3_cran_preflight_r_package_dependencies_are_conda_resolvable():
    repo_root = Path(__file__).resolve().parents[1]
    env_yml = yaml.safe_load((repo_root / "environment.yml").read_text(encoding="utf-8"))
    conda_dependencies = {
        dep.split("=")[0].lower()
        for dep in env_yml["dependencies"]
        if isinstance(dep, str)
    }

    missing: dict[str, list[str]] = {}
    for package_name, description in TIER3_CRAN_PREFLIGHT_R_PACKAGE_DESCRIPTIONS.items():
        package_missing = []
        for required_package in sorted(_required_r_packages(description), key=str.lower):
            if _conda_package_name(required_package).lower() not in conda_dependencies:
                package_missing.append(required_package)
        if package_missing:
            missing[package_name] = package_missing

    assert missing == {}


def test_setup_env_cran_preflight_covers_version_sensitive_github_r_dependencies():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")
    github_first_install = "for (pkg in github_roots)"

    preflight_calls = [
        'ensure_cran_package("wrMisc")',
        'ensure_cran_package("NMF", "0.23.0")',
        'ensure_cran_package("hahmmr")',
        'ensure_cran_package("scistreer", "1.1.0")',
    ]

    for preflight_call in preflight_calls:
        assert preflight_call in setup_script
        assert setup_script.index(preflight_call) < setup_script.index(github_first_install)


def test_environment_yml_pins_rcppparallel_to_r43_compatible_build_for_scistreer():
    repo_root = Path(__file__).resolve().parents[1]
    env_yml = yaml.safe_load((repo_root / "environment.yml").read_text(encoding="utf-8"))
    dependencies = {
        dep.lower()
        for dep in env_yml["dependencies"]
        if isinstance(dep, str)
    }

    assert "r-phangorn" in dependencies
    assert "r-rcppparallel=5.1.9" in dependencies


def test_setup_env_installs_numbat_cran_dependencies_before_numbat():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")

    hahmmr_install = 'ensure_cran_package("hahmmr")'
    scistreer_install = 'ensure_cran_package("scistreer", "1.1.0")'
    numbat_install = 'c("numbat", "kharchenkolab/numbat")'
    github_loop = "for (pkg in github_roots)"

    assert hahmmr_install in setup_script
    assert scistreer_install in setup_script
    assert numbat_install in setup_script
    assert 'ensure_github_package("hahmmr"' not in setup_script
    assert 'ensure_github_package("scistreer"' not in setup_script
    assert setup_script.index(hahmmr_install) < setup_script.index(github_loop)
    assert setup_script.index(scistreer_install) < setup_script.index(github_loop)


def test_setup_env_installs_wrmisc_from_cran_before_github_r_packages():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")

    cran_install = 'ensure_cran_package("wrMisc")'
    github_install = "for (pkg in github_roots)"

    assert cran_install in setup_script
    assert github_install in setup_script
    assert setup_script.index(cran_install) < setup_script.index(github_install)


def test_setup_env_upgrades_nmf_before_github_r_packages():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")

    nmf_check = 'ensure_cran_package("NMF", "0.23.0")'
    package_version_check = "current_version < minimum_version"
    nmf_install = "install.packages(pkg"
    github_install = "for (pkg in github_roots)"

    assert nmf_check in setup_script
    assert package_version_check in setup_script
    assert nmf_install in setup_script
    assert setup_script.index(nmf_check) < setup_script.index(github_install)


def test_setup_env_installs_github_r_packages_without_dependency_resolution_or_vignettes():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")
    install_call = "devtools::install_github("

    assert install_call in setup_script
    assert "repo," in setup_script
    assert "dependencies = FALSE" in setup_script
    assert "build_vignettes = FALSE" in setup_script
    assert "build_manual = FALSE" in setup_script


def test_conda_forge_wrmisc_builds_do_not_target_r43():
    try:
        result = subprocess.run(
            [
                "conda",
                "search",
                "-c",
                "conda-forge",
                "--override-channels",
                "r-wrmisc",
                "--info",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"conda search unavailable: {exc}")

    if result.returncode != 0:
        pytest.skip(f"conda search failed: {result.stderr}")

    assert "r-wrmisc" in result.stdout
    assert "r-base >=4.4,<4.5.0a0" in result.stdout
    assert "r-base >=4.5,<4.6.0a0" in result.stdout
    assert "r-base >=4.3" not in result.stdout

    repo_root = Path(__file__).resolve().parents[1]
    env_yml = yaml.safe_load((repo_root / "environment.yml").read_text(encoding="utf-8"))
    dependencies = {
        dep.split("=")[0].lower()
        for dep in env_yml["dependencies"]
        if isinstance(dep, str)
    }
    assert "r-wrmisc" not in dependencies


def test_setup_env_falls_back_when_mamba_env_listing_is_broken(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_prefix = tmp_path / "envs" / "OmicsClaw"
    fake_prefix_bin = fake_prefix / "bin"
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()
    fake_prefix_bin.mkdir(parents=True)

    (fake_bin / "mamba").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mamba %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "--version" ]; then
                echo "mamba 0.test"
                exit 0
            fi

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                echo "'Namespace' object has no attribute 'func'" >&2
                exit 2
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "list" ]; then
                echo "'Namespace' object has no attribute 'func'" >&2
                exit 2
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "update" ]; then
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "create" ]; then
                echo "unexpected create for existing fake env" >&2
                exit 12
            fi

            if [ "${1:-}" = "run" ]; then
                if printf '%s\\n' "$*" | grep -q ' python -c '; then
                    echo "$OMICSCLAW_FAKE_PREFIX"
                    exit 0
                fi
                if printf '%s\\n' "$*" | grep -q ' Rscript '; then
                    cat >/dev/null
                    exit 0
                fi
                exit 0
            fi

            echo "unexpected mamba command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "conda").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'conda %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "--version" ]; then
                echo "conda 0.test"
                exit 0
            fi

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            OmicsClaw                $OMICSCLAW_FAKE_PREFIX
            EOF
                exit 0
            fi

            echo "unexpected conda command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "mamba").chmod(0o755)
    (fake_bin / "conda").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "OMICSCLAW_FAKE_LOG": str(log_path),
            "OMICSCLAW_FAKE_PREFIX": str(fake_prefix),
        }
    )
    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert "conda info --envs" in calls
    assert "mamba env update -n OmicsClaw" in calls
    assert "mamba env create -n OmicsClaw" not in calls
    assert "env 'OmicsClaw' already exists" in result.stdout


def test_setup_env_uses_private_conda_package_cache_by_default(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_home = tmp_path / "home"
    fake_prefix = fake_home / ".conda" / "envs" / "OmicsClaw"
    expected_pkgs = fake_home / ".conda" / "pkgs"
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()

    (fake_bin / "mamba").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mamba %s | CONDA_PKGS_DIRS=%s\\n' "$*" "${CONDA_PKGS_DIRS:-}" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            EOF
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "create" ]; then
                if [ "${CONDA_PKGS_DIRS:-}" != "$OMICSCLAW_EXPECTED_PKGS" ]; then
                    echo "libnsl-2.0.1-hb9d3cd8_1.conda extraction failed" >&2
                    echo "error    libmamba Error when extracting package: filesystem error: cannot remove all: Permission denied [/share/Bio/Biosoft/conda/miniconda3/pkgs/libnsl-2.0.1-hb9d3cd8_1]" >&2
                    exit 13
                fi
                mkdir -p "$OMICSCLAW_FAKE_PREFIX/conda-meta" "$OMICSCLAW_FAKE_PREFIX/bin"
                exit 0
            fi

            if [ "${1:-}" = "run" ]; then
                if printf '%s\\n' "$*" | grep -q ' python -c '; then
                    echo "$OMICSCLAW_FAKE_PREFIX"
                    exit 0
                fi
                if printf '%s\\n' "$*" | grep -q ' Rscript '; then
                    cat >/dev/null
                    exit 0
                fi
                exit 0
            fi

            echo "unexpected mamba command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "conda").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'conda %s | CONDA_PKGS_DIRS=%s\\n' "$*" "${CONDA_PKGS_DIRS:-}" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            EOF
                exit 0
            fi

            echo "unexpected conda command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "mamba").chmod(0o755)
    (fake_bin / "conda").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "OMICSCLAW_EXPECTED_PKGS": str(expected_pkgs),
            "OMICSCLAW_FAKE_LOG": str(log_path),
            "OMICSCLAW_FAKE_PREFIX": str(fake_prefix),
        }
    )
    env.pop("CONDA_PKGS_DIRS", None)
    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert expected_pkgs.is_dir()
    calls = log_path.read_text(encoding="utf-8")
    assert f"CONDA_PKGS_DIRS={expected_pkgs}" in calls


def test_setup_env_allows_upstream_spagcn_sklearn_placeholder(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_home = tmp_path / "home"
    fake_prefix = fake_home / ".conda" / "envs" / "OmicsClaw"
    fake_prefix_bin = fake_prefix / "bin"
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()
    fake_prefix_bin.mkdir(parents=True)

    (fake_bin / "mamba").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mamba %s | SKLEARN_ALLOW=%s\\n' "$*" "${SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL:-}" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            OmicsClaw                $OMICSCLAW_FAKE_PREFIX
            EOF
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "update" ]; then
                exit 0
            fi

            if [ "${1:-}" = "run" ]; then
                if printf '%s\\n' "$*" | grep -q ' python -c '; then
                    echo "$OMICSCLAW_FAKE_PREFIX"
                    exit 0
                fi
                if printf '%s\\n' "$*" | grep -q 'pip install -e'; then
                    if [ "${SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL:-}" != "True" ]; then
                        echo "The 'sklearn' PyPI package is deprecated, use 'scikit-learn'" >&2
                        echo "ERROR: Failed to build 'sklearn' when getting requirements to build wheel" >&2
                        exit 14
                    fi
                    exit 0
                fi
                if printf '%s\\n' "$*" | grep -q ' Rscript '; then
                    cat >/dev/null
                    exit 0
                fi
                exit 0
            fi

            echo "unexpected mamba command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "conda").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'conda %s | SKLEARN_ALLOW=%s\\n' "$*" "${SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL:-}" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            OmicsClaw                $OMICSCLAW_FAKE_PREFIX
            EOF
                exit 0
            fi

            echo "unexpected conda command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "mamba").chmod(0o755)
    (fake_bin / "conda").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "OMICSCLAW_FAKE_LOG": str(log_path),
            "OMICSCLAW_FAKE_PREFIX": str(fake_prefix),
        }
    )
    env.pop("SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE_INSTALL", None)
    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert "pip install -e" in calls
    assert "SKLEARN_ALLOW=True" in calls


def test_setup_env_updates_existing_named_prefix_missing_from_env_list(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_home = tmp_path / "home"
    envs_dir = tmp_path / "miniconda3" / "envs"
    fake_prefix = envs_dir / "OmicsClaw"
    fake_prefix_bin = fake_prefix / "bin"
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()
    fake_prefix_bin.mkdir(parents=True)
    (fake_prefix / "conda-meta").mkdir()

    (fake_bin / "mamba").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mamba %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            EOF
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "update" ]; then
                if [ "${3:-}" = "-p" ] && [ "${4:-}" = "$OMICSCLAW_FAKE_PREFIX" ]; then
                    exit 0
                fi
                echo "expected update by prefix for unlisted env prefix" >&2
                exit 15
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "create" ]; then
                echo "CondaValueError: prefix already exists: $OMICSCLAW_FAKE_PREFIX" >&2
                exit 16
            fi

            if [ "${1:-}" = "run" ]; then
                if printf '%s\\n' "$*" | grep -q -- "-p $OMICSCLAW_FAKE_PREFIX"; then
                    if printf '%s\\n' "$*" | grep -q ' python -c '; then
                        echo "$OMICSCLAW_FAKE_PREFIX"
                        exit 0
                    fi
                    if printf '%s\\n' "$*" | grep -q 'pip install -e'; then
                        exit 0
                    fi
                    if printf '%s\\n' "$*" | grep -q ' Rscript '; then
                        cat >/dev/null
                        exit 0
                    fi
                    exit 0
                fi
                echo "expected run by prefix for unlisted env prefix" >&2
                exit 17
            fi

            echo "unexpected mamba command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "conda").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'conda %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            EOF
                exit 0
            fi

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--json" ]; then
                cat <<EOF
            {"envs_dirs": ["$OMICSCLAW_FAKE_ENVS_DIR"]}
            EOF
                exit 0
            fi

            echo "unexpected conda command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "mamba").chmod(0o755)
    (fake_bin / "conda").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "OMICSCLAW_FAKE_ENVS_DIR": str(envs_dir),
            "OMICSCLAW_FAKE_LOG": str(log_path),
            "OMICSCLAW_FAKE_PREFIX": str(fake_prefix),
        }
    )
    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert f"mamba env update -p {fake_prefix}" in calls
    assert "mamba env create -n OmicsClaw" not in calls
    assert f"mamba run -p {fake_prefix}" in calls


def test_setup_env_updates_anonymous_env_list_prefix(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_home = tmp_path / "home"
    shared_envs_dir = tmp_path / "share" / "Bio" / "Biosoft" / "conda" / "miniconda3" / "envs"
    unrelated_envs_dir = tmp_path / "home" / "anaconda3" / "envs"
    fake_prefix = shared_envs_dir / "OmicsClaw"
    fake_prefix_bin = fake_prefix / "bin"
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()
    fake_prefix_bin.mkdir(parents=True)
    unrelated_envs_dir.mkdir(parents=True)
    (fake_prefix / "conda-meta").mkdir()

    (fake_bin / "mamba").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mamba %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /home/weige/anaconda3
            Garfield_deploy          /home/weige/anaconda3/envs/Garfield_deploy
                                     $OMICSCLAW_FAKE_PREFIX
            EOF
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "update" ]; then
                if [ "${3:-}" = "-p" ] && [ "${4:-}" = "$OMICSCLAW_FAKE_PREFIX" ]; then
                    exit 0
                fi
                echo "expected update by anonymous env-list prefix" >&2
                exit 18
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "create" ]; then
                echo "CondaValueError: prefix already exists: $OMICSCLAW_FAKE_PREFIX" >&2
                exit 19
            fi

            if [ "${1:-}" = "run" ]; then
                if printf '%s\\n' "$*" | grep -q -- "-p $OMICSCLAW_FAKE_PREFIX"; then
                    if printf '%s\\n' "$*" | grep -q ' python -c '; then
                        echo "$OMICSCLAW_FAKE_PREFIX"
                        exit 0
                    fi
                    if printf '%s\\n' "$*" | grep -q 'pip install -e'; then
                        exit 0
                    fi
                    if printf '%s\\n' "$*" | grep -q ' Rscript '; then
                        cat >/dev/null
                        exit 0
                    fi
                    exit 0
                fi
                echo "expected run by anonymous env-list prefix" >&2
                exit 20
            fi

            echo "unexpected mamba command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "conda").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'conda %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /home/weige/anaconda3
            Garfield_deploy          /home/weige/anaconda3/envs/Garfield_deploy
                                     $OMICSCLAW_FAKE_PREFIX
            EOF
                exit 0
            fi

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--json" ]; then
                cat <<EOF
            {"envs_dirs": ["$OMICSCLAW_UNRELATED_ENVS_DIR"]}
            EOF
                exit 0
            fi

            echo "unexpected conda command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "mamba").chmod(0o755)
    (fake_bin / "conda").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "OMICSCLAW_FAKE_LOG": str(log_path),
            "OMICSCLAW_FAKE_PREFIX": str(fake_prefix),
            "OMICSCLAW_UNRELATED_ENVS_DIR": str(unrelated_envs_dir),
        }
    )
    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert f"mamba env update -p {fake_prefix}" in calls
    assert "mamba env create -n OmicsClaw" not in calls
    assert f"mamba run -p {fake_prefix}" in calls


def _write_torch_backend_setup_fakes(
    tmp_path: Path,
    *,
    existing_env: bool = True,
    nvidia_gpu: bool = False,
) -> tuple[dict[str, str], Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "bin"
    fake_home = tmp_path / "home"
    fake_prefix = fake_home / ".conda" / "envs" / "OmicsClaw"
    fake_envs_dir = fake_prefix.parent
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()
    (fake_prefix / "conda-meta").mkdir(parents=True)
    (fake_prefix / "bin").mkdir(parents=True)

    (fake_bin / "mamba").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'mamba %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            EOF
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "update" ]; then
                exit 0
            fi

            if [ "${1:-}" = "env" ] && [ "${2:-}" = "create" ]; then
                mkdir -p "$OMICSCLAW_FAKE_PREFIX/conda-meta" "$OMICSCLAW_FAKE_PREFIX/bin"
                exit 0
            fi

            if [ "${1:-}" = "install" ]; then
                if printf '%s\\n' "$*" | grep -q 'pytorch-cuda'; then
                    exit "${OMICSCLAW_FAKE_INSTALL_CUDA_EXIT:-0}"
                fi
                exit 0
            fi

            if [ "${1:-}" = "run" ]; then
                if printf '%s\\n' "$*" | grep -q ' uv pip install '; then
                    printf 'uv-link-mode=%s\\n' "${UV_LINK_MODE:-}" >> "$OMICSCLAW_FAKE_LOG"
                fi
                if printf '%s\\n' "$*" | grep -q ' python -c '; then
                    if printf '%s\\n' "$*" | grep -q 'sys.prefix'; then
                        echo "$OMICSCLAW_FAKE_PREFIX"
                        exit 0
                    fi
                    if printf '%s\\n' "$*" | grep -q 'torch.cuda.is_available'; then
                        if [ "${OMICSCLAW_FAKE_VERIFY_CUDA_EXIT:-0}" = "0" ]; then
                            echo "cuda_available=True cuda_version=12.1"
                        else
                            echo "cuda_available=False cuda_version=None" >&2
                        fi
                        exit "${OMICSCLAW_FAKE_VERIFY_CUDA_EXIT:-0}"
                    fi
                fi
                if printf '%s\\n' "$*" | grep -q ' Rscript '; then
                    cat >/dev/null
                    exit 0
                fi
                exit 0
            fi

            echo "unexpected mamba command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "conda").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'conda %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--envs" ]; then
                cat <<EOF
            # conda environments:
            #
            base                     /fake/base
            EOF
                if [ "${OMICSCLAW_FAKE_EXISTING_ENV:-1}" = "1" ]; then
                    echo "OmicsClaw                $OMICSCLAW_FAKE_PREFIX"
                fi
                exit 0
            fi

            if [ "${1:-}" = "info" ] && [ "${2:-}" = "--json" ]; then
                cat <<EOF
            {"envs_dirs": ["$OMICSCLAW_FAKE_ENVS_DIR"]}
            EOF
                exit 0
            fi

            echo "unexpected conda command: $*" >&2
            exit 99
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "nvidia-smi").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'nvidia-smi %s\\n' "$*" >> "$OMICSCLAW_FAKE_LOG"

            if [ "${1:-}" = "-L" ] && [ "${OMICSCLAW_FAKE_NVIDIA_GPU:-0}" = "1" ]; then
                echo "GPU 0: NVIDIA A100-SXM4-40GB"
                exit 0
            fi
            exit 1
            """
        ),
        encoding="utf-8",
    )
    (fake_bin / "mamba").chmod(0o755)
    (fake_bin / "conda").chmod(0o755)
    (fake_bin / "nvidia-smi").chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "OMICSCLAW_FAKE_EXISTING_ENV": "1" if existing_env else "0",
            "OMICSCLAW_FAKE_ENVS_DIR": str(fake_envs_dir),
            "OMICSCLAW_FAKE_LOG": str(log_path),
            "OMICSCLAW_FAKE_NVIDIA_GPU": "1" if nvidia_gpu else "0",
            "OMICSCLAW_FAKE_PREFIX": str(fake_prefix),
        }
    )
    return env, log_path, repo_root


def test_setup_env_auto_torch_backend_installs_cuda_pytorch_when_gpu_is_detected(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=True)
    env["OMICSCLAW_TORCH_BACKEND"] = "auto"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    cuda_install = (
        "mamba install -n OmicsClaw "
        "-c https://conda.anaconda.org/pytorch "
        "-c https://conda.anaconda.org/nvidia "
        "pytorch pytorch-cuda=12.1 -y"
    )
    assert "nvidia-smi -L" in calls
    assert cuda_install in calls
    assert "torch.cuda.is_available" in calls
    assert calls.index(cuda_install) < calls.index("uv pip install -e")


def test_setup_env_auto_torch_backend_installs_cuda_pytorch_by_prefix(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(
        tmp_path,
        existing_env=False,
        nvidia_gpu=True,
    )
    env["OMICSCLAW_TORCH_BACKEND"] = "auto"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert (
        f"mamba install -p {env['OMICSCLAW_FAKE_PREFIX']} "
        "-c https://conda.anaconda.org/pytorch "
        "-c https://conda.anaconda.org/nvidia "
        "pytorch pytorch-cuda=12.1 -y"
    ) in calls
    assert f"mamba run -p {env['OMICSCLAW_FAKE_PREFIX']} --no-capture-output python -c" in calls


def test_setup_env_cuda_torch_channels_can_be_overridden(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=True)
    env["OMICSCLAW_TORCH_BACKEND"] = "cuda"
    env["OMICSCLAW_PYTORCH_CHANNEL"] = "https://mirror.example/pytorch"
    env["OMICSCLAW_NVIDIA_CHANNEL"] = "https://mirror.example/nvidia"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert (
        "mamba install -n OmicsClaw "
        "-c https://mirror.example/pytorch "
        "-c https://mirror.example/nvidia "
        "pytorch pytorch-cuda=12.1 -y"
    ) in calls


def test_setup_env_uv_pip_install_defaults_to_copy_link_mode(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=False)
    env["OMICSCLAW_TORCH_BACKEND"] = "auto"
    env.pop("UV_LINK_MODE", None)

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert "uv-link-mode=copy" in calls


def test_setup_env_uv_pip_install_preserves_configured_link_mode(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=False)
    env["OMICSCLAW_TORCH_BACKEND"] = "auto"
    env["UV_LINK_MODE"] = "hardlink"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert "uv-link-mode=hardlink" in calls


def test_setup_env_cpu_torch_backend_skips_cuda_probe_and_install(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=True)
    env["OMICSCLAW_TORCH_BACKEND"] = "cpu"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = log_path.read_text(encoding="utf-8")
    assert "torch backend: cpu" in result.stdout
    assert "nvidia-smi -L" not in calls
    assert "pytorch-cuda" not in calls


def test_setup_env_forced_cuda_torch_backend_fails_when_cuda_verification_fails(tmp_path):
    env, _log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=False)
    env["OMICSCLAW_TORCH_BACKEND"] = "cuda"
    env["OMICSCLAW_FAKE_VERIFY_CUDA_EXIT"] = "33"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "CUDA PyTorch verification failed" in result.stderr


def test_setup_env_rejects_invalid_torch_backend_before_conda_changes(tmp_path):
    env, log_path, repo_root = _write_torch_backend_setup_fakes(tmp_path, nvidia_gpu=True)
    env["OMICSCLAW_TORCH_BACKEND"] = "rocm"

    result = subprocess.run(
        ["bash", "0_setup_env.sh", "OmicsClaw"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "invalid OMICSCLAW_TORCH_BACKEND" in result.stderr
    calls = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    assert "env update" not in calls
