"""Unit tests for the notebook `var_inspector` helper module.

These tests cover pure-Python logic that builds the inline scripts sent
into the IPython kernel and parses back the JSON payload. They do not
require a running kernel — the goal is to keep script building and
payload parsing covered by fast, deterministic unit tests.
"""

from __future__ import annotations

import json
import re

import pytest


# ---------------------------------------------------------------------------
# build_var_detail_script
# ---------------------------------------------------------------------------


class TestBuildVarDetailScript:
    def test_embeds_variable_name_as_literal(self):
        from omicsclaw.app.notebook.var_inspector import build_var_detail_script

        script = build_var_detail_script("my_df")

        # The generated script should reference the variable by name so that
        # eval-style lookup or globals().get("my_df") works at runtime.
        assert "my_df" in script

    def test_embeds_row_and_col_limits(self):
        from omicsclaw.app.notebook.var_inspector import build_var_detail_script

        script = build_var_detail_script("x", max_rows=7, max_cols=3)

        assert "7" in script
        assert "3" in script

    def test_rejects_names_with_quotes_or_backslashes(self):
        from omicsclaw.app.notebook.var_inspector import build_var_detail_script

        # Strict policy: any non-identifier character is rejected outright,
        # not "safely escaped". This is a defense-in-depth choice — keeping
        # the allow-list tight means the generated source can never carry a
        # user-controlled expression.
        with pytest.raises(ValueError):
            build_var_detail_script('bad"name\\here')

    def test_rejects_non_identifier_variable(self):
        from omicsclaw.app.notebook.var_inspector import build_var_detail_script

        # We only allow dotted-identifier paths (e.g. "adata.obs") — arbitrary
        # expressions would be a code injection vector.
        with pytest.raises(ValueError):
            build_var_detail_script("__import__('os').system('rm -rf /')")

    def test_allows_dotted_paths(self):
        from omicsclaw.app.notebook.var_inspector import build_var_detail_script

        script = build_var_detail_script("adata.obs")
        assert "adata.obs" in script or "adata" in script

    def test_uses_shared_payload_delimiters(self):
        from omicsclaw.app.notebook.var_inspector import (
            PAYLOAD_BEGIN,
            PAYLOAD_END,
            build_var_detail_script,
        )

        script = build_var_detail_script("x")
        assert PAYLOAD_BEGIN in script
        assert PAYLOAD_END in script


# ---------------------------------------------------------------------------
# build_adata_slot_script
# ---------------------------------------------------------------------------


class TestBuildAdataSlotScript:
    def test_supports_obs_slot_with_key(self):
        from omicsclaw.app.notebook.var_inspector import build_adata_slot_script

        script = build_adata_slot_script("adata", "obs", "cluster")

        compile(script, "<adata_slot>", "exec")
        assert "obs" in script
        assert "cluster" in script

    def test_supports_obsm_slot(self):
        from omicsclaw.app.notebook.var_inspector import build_adata_slot_script

        script = build_adata_slot_script("adata", "obsm", "X_umap")

        compile(script, "<adata_slot>", "exec")
        assert "obsm" in script
        assert "X_umap" in script

    def test_allows_empty_key_for_obs(self):
        from omicsclaw.app.notebook.var_inspector import build_adata_slot_script

        script = build_adata_slot_script("adata", "obs", "")

        compile(script, "<adata_slot>", "exec")

    def test_rejects_unsupported_slot(self):
        from omicsclaw.app.notebook.var_inspector import build_adata_slot_script

        with pytest.raises(ValueError):
            build_adata_slot_script("adata", "bogus_slot", "")

    def test_rejects_non_identifier_var_name(self):
        from omicsclaw.app.notebook.var_inspector import build_adata_slot_script

        with pytest.raises(ValueError):
            build_adata_slot_script("1+1", "obs", "")

    def test_key_with_quotes_is_safely_escaped(self):
        from omicsclaw.app.notebook.var_inspector import build_adata_slot_script

        script = build_adata_slot_script("adata", "obs", 'evil"key')

        # The generated source must still compile even with nasty keys.
        compile(script, "<adata_slot>", "exec")


# ---------------------------------------------------------------------------
# parse_var_detail_payload
# ---------------------------------------------------------------------------


def _wrap(payload: dict) -> str:
    from omicsclaw.app.notebook.var_inspector import PAYLOAD_BEGIN, PAYLOAD_END

    return f"noise before\n{PAYLOAD_BEGIN}{json.dumps(payload)}{PAYLOAD_END}\nafter\n"


class TestParseVarDetailPayload:
    def test_returns_missing_for_empty_stdout(self):
        from omicsclaw.app.notebook.var_inspector import parse_var_detail_payload

        result = parse_var_detail_payload("")
        assert result["type"] == "missing"

    def test_returns_missing_when_delimiters_absent(self):
        from omicsclaw.app.notebook.var_inspector import parse_var_detail_payload

        result = parse_var_detail_payload("just some random stdout\n")
        assert result["type"] == "missing"

    def test_parses_dataframe_payload(self):
        from omicsclaw.app.notebook.var_inspector import parse_var_detail_payload

        payload = {
            "type": "dataframe",
            "name": "my_df",
            "shape": [10, 3],
            "dtypes": {"a": "int64", "b": "float64", "c": "object"},
            "table": {
                "columns": ["a", "b", "c"],
                "index": ["0", "1"],
                "data": [[1, 2.0, "x"], [3, 4.0, "y"]],
            },
        }
        stdout = _wrap(payload)

        result = parse_var_detail_payload(stdout)

        assert result["type"] == "dataframe"
        assert result["name"] == "my_df"
        assert result["shape"] == [10, 3]
        assert result["table"]["columns"] == ["a", "b", "c"]

    def test_parses_anndata_payload(self):
        from omicsclaw.app.notebook.var_inspector import parse_var_detail_payload

        payload = {
            "type": "anndata",
            "name": "adata",
            "summary": {
                "shape": [200, 500],
                "obs_columns": ["cluster", "leiden"],
                "var_columns": ["highly_variable"],
                "obsm_keys": ["X_pca", "X_umap"],
                "layers": [],
                "uns_keys": ["neighbors"],
            },
        }
        stdout = _wrap(payload)

        result = parse_var_detail_payload(stdout)

        assert result["type"] == "anndata"
        assert result["summary"]["shape"] == [200, 500]

    def test_parses_scalar_payload(self):
        from omicsclaw.app.notebook.var_inspector import parse_var_detail_payload

        payload = {"type": "scalar", "name": "x", "content": "42"}
        result = parse_var_detail_payload(_wrap(payload))

        assert result["type"] == "scalar"
        assert result["content"] == "42"

    def test_propagates_error_payload(self):
        from omicsclaw.app.notebook.var_inspector import parse_var_detail_payload

        payload = {"type": "error", "error": "variable not found: foo"}
        result = parse_var_detail_payload(_wrap(payload))

        assert result["type"] == "error"
        assert "not found" in result["error"]

    def test_returns_missing_on_corrupt_json(self):
        from omicsclaw.app.notebook.var_inspector import (
            PAYLOAD_BEGIN,
            PAYLOAD_END,
            parse_var_detail_payload,
        )

        stdout = f"{PAYLOAD_BEGIN}not json at all{PAYLOAD_END}"
        result = parse_var_detail_payload(stdout)
        assert result["type"] == "missing"


# ---------------------------------------------------------------------------
# Generated script safety
# ---------------------------------------------------------------------------


class TestScriptExecutionSafety:
    """Execute generated scripts against in-memory fixtures.

    These tests act as end-to-end checks that the generated payload script
    actually produces the JSON shape the parser expects, without needing a
    full Jupyter kernel.
    """

    def _run_script(self, script: str, namespace: dict) -> str:
        """Execute `script` capturing stdout, return the captured text."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exec(script, namespace)
        return buf.getvalue()

    def test_var_detail_dataframe_roundtrip(self):
        import pandas as pd

        from omicsclaw.app.notebook.var_inspector import (
            build_var_detail_script,
            parse_var_detail_payload,
        )

        df = pd.DataFrame({"a": [1, 2, 3], "b": [0.1, 0.2, 0.3]})
        ns = {"my_df": df}
        script = build_var_detail_script("my_df", max_rows=50, max_cols=50)
        stdout = self._run_script(script, ns)
        result = parse_var_detail_payload(stdout)

        assert result["type"] == "dataframe"
        assert result["shape"] == [3, 2]
        assert set(result["dtypes"].keys()) == {"a", "b"}

    def test_var_detail_series_roundtrip(self):
        import pandas as pd

        from omicsclaw.app.notebook.var_inspector import (
            build_var_detail_script,
            parse_var_detail_payload,
        )

        s = pd.Series([10, 20, 30], name="count")
        ns = {"s": s}
        script = build_var_detail_script("s")
        stdout = self._run_script(script, ns)
        result = parse_var_detail_payload(stdout)

        assert result["type"] in {"series", "dataframe"}
        # Series is coerced to a 1-column preview, so shape should be [3, 1]
        assert result["shape"][0] == 3

    def test_var_detail_scalar_roundtrip(self):
        from omicsclaw.app.notebook.var_inspector import (
            build_var_detail_script,
            parse_var_detail_payload,
        )

        ns = {"x": 42}
        script = build_var_detail_script("x")
        stdout = self._run_script(script, ns)
        result = parse_var_detail_payload(stdout)

        assert result["type"] == "scalar"
        assert "42" in result["content"]

    def test_var_detail_missing_variable(self):
        from omicsclaw.app.notebook.var_inspector import (
            build_var_detail_script,
            parse_var_detail_payload,
        )

        script = build_var_detail_script("does_not_exist")
        stdout = self._run_script(script, {})
        result = parse_var_detail_payload(stdout)

        assert result["type"] in {"missing", "error"}

    def test_adata_slot_obs_roundtrip(self):
        pytest.importorskip("anndata")
        import numpy as np
        import pandas as pd
        from anndata import AnnData

        from omicsclaw.app.notebook.var_inspector import (
            build_adata_slot_script,
            parse_var_detail_payload,
        )

        obs = pd.DataFrame({"cluster": ["a", "b", "a", "c"]})
        adata = AnnData(X=np.eye(4), obs=obs)
        ns = {"adata": adata}

        script = build_adata_slot_script("adata", "obs", "cluster")
        stdout = self._run_script(script, ns)
        result = parse_var_detail_payload(stdout)

        assert result["type"] == "dataframe"
        assert result["shape"][0] == 4

    def test_adata_slot_obsm_roundtrip(self):
        pytest.importorskip("anndata")
        import numpy as np
        from anndata import AnnData

        from omicsclaw.app.notebook.var_inspector import (
            build_adata_slot_script,
            parse_var_detail_payload,
        )

        adata = AnnData(X=np.eye(5))
        adata.obsm["X_umap"] = np.arange(10).reshape(5, 2).astype(float)
        ns = {"adata": adata}

        script = build_adata_slot_script("adata", "obsm", "X_umap")
        stdout = self._run_script(script, ns)
        result = parse_var_detail_payload(stdout)

        assert result["type"] in {"dataframe", "content"}
