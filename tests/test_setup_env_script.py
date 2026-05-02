from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml


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


def test_setup_env_installs_wrmisc_from_cran_before_github_r_packages():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")

    cran_install = 'ensure_cran_package("wrMisc")'
    github_install = "    devtools::install_github("

    assert cran_install in setup_script
    assert github_install in setup_script
    assert "p[2]," in setup_script
    assert setup_script.index(cran_install) < setup_script.index(github_install)


def test_setup_env_upgrades_nmf_before_github_r_packages():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")

    nmf_check = 'ensure_cran_package("NMF", "0.23.0")'
    package_version_check = "current_version < minimum_version"
    nmf_install = "install.packages(pkg"
    github_install = "    devtools::install_github("

    assert nmf_check in setup_script
    assert package_version_check in setup_script
    assert nmf_install in setup_script
    assert setup_script.index(nmf_check) < setup_script.index(github_install)


def test_setup_env_installs_github_r_packages_without_dependency_resolution_or_vignettes():
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "0_setup_env.sh").read_text(encoding="utf-8")
    install_call = "    devtools::install_github("

    assert install_call in setup_script
    assert "p[2]," in setup_script
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
