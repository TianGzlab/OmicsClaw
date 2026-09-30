from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRNA_DIR = ROOT / "skills" / "singlecell" / "scrna"


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


# ``test_cli_stdio_reconfigure_escapes_nonencodable_output`` was removed with
# ``omicsclaw/surfaces/cli/``: it drove that CLI body's
# ``_configure_stdio_error_handling``, and the rebuilt shell has no such hook.
# The ASCII-only rule above is the half that was never about the CLI — it reads
# the skill scripts themselves — so it stays.
