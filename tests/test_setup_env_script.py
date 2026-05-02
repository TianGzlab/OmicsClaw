from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


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
    fake_prefix_bin = fake_prefix / "bin"
    expected_pkgs = fake_home / ".conda" / "pkgs"
    log_path = tmp_path / "calls.log"
    fake_bin.mkdir()
    fake_prefix_bin.mkdir(parents=True)

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
