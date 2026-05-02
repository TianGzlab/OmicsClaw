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
