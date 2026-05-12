from __future__ import annotations

import ast
import importlib.util
import io
from collections.abc import Iterator
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRNA_DIR = ROOT / "skills" / "singlecell" / "scrna"


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location(
        "omicsclaw_main_console_encoding_test",
        ROOT / "omicsclaw.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iter_string_fragments(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
        return
    if isinstance(node, ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                yield value.value
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        yield from _iter_string_fragments(node.left)
        yield from _iter_string_fragments(node.right)


def _is_print_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "print"


def test_scrna_print_statements_use_ascii_only_text():
    offenders: list[str] = []

    for path in sorted(SCRNA_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative_path = path.relative_to(ROOT)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_print_call(node):
                continue
            for arg in node.args:
                for fragment in _iter_string_fragments(arg):
                    if any(ord(char) > 127 for char in fragment):
                        offenders.append(
                            f"{relative_path}:{getattr(arg, 'lineno', node.lineno)}: {fragment!r}"
                        )

    assert offenders == [], (
        "SCRNA terminal print() strings must stay ASCII-only for Windows code pages:\n"
        + "\n".join(offenders)
    )


def test_cli_stdio_reconfigure_escapes_nonencodable_output():
    oc = _load_omicsclaw_script()
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout_stream = io.TextIOWrapper(stdout_bytes, encoding="gbk", errors="strict")
    stderr_stream = io.TextIOWrapper(stderr_bytes, encoding="gbk", errors="strict")

    oc._configure_stdio_error_handling(stdout_stream, stderr_stream)

    stdout_stream.write("bullet=•")
    stderr_stream.write("bullet_err=•")
    stdout_stream.flush()
    stderr_stream.flush()

    assert stdout_bytes.getvalue().decode("ascii") == r"bullet=\u2022"
    assert stderr_bytes.getvalue().decode("ascii") == r"bullet_err=\u2022"
