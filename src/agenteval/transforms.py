"""Surface-feature ablations for E2.

Each transform changes one surface feature and leaves the others as they were:
``strip_comments`` keeps layout and names, ``rename_identifiers`` keeps layout and
comments, ``normalize_format`` keeps names and comments. Callers must rerun the
tests after a transform; a transform raises ``TransformError`` when it cannot be
applied safely.
"""

from __future__ import annotations

import ast
import builtins
import io
import keyword
import re
import tokenize
from collections.abc import Callable

import black

CONDITIONS = ("raw", "no_comments", "renamed", "formatted", "all")


class TransformError(ValueError):
    pass


def _parse(code: str) -> ast.Module:
    try:
        return ast.parse(code)
    except SyntaxError as exc:
        raise TransformError(f"syntax error: {exc}") from exc


def _byte_col_to_char(line: str, col: int) -> int:
    return len(line.encode("utf-8")[:col].decode("utf-8", "replace"))


def strip_comments(code: str) -> str:
    """Remove ``#`` comments and docstrings; keep every other line as written."""
    tree = _parse(code)
    lines = code.splitlines(keepends=True)
    delete: set[int] = set()
    replace: dict[int, str] = {}

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise TransformError(f"tokenize failed: {exc}") from exc
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        row, col = tok.start
        line = lines[row - 1]
        kept = line[:col].rstrip()
        if kept:
            newline = "\n" if line.endswith("\n") else ""
            replace[row - 1] = kept + newline
        else:
            delete.add(row - 1)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        doc = body[0]
        start, end = doc.lineno - 1, (doc.end_lineno or doc.lineno) - 1
        first, last = lines[start], lines[end]
        before = first[: _byte_col_to_char(first, doc.col_offset)]
        after = last[_byte_col_to_char(last, doc.end_col_offset or 0) :]
        if before.strip() or (after.strip() and not after.strip().startswith("#")):
            continue  # docstring shares a line with other code; leave it
        if len(body) > 1 and body[1].lineno - 1 <= end:
            continue
        if not isinstance(node, ast.Module) and len(body) == 1:
            delete.update(range(start + 1, end + 1))
            delete.discard(start)
            replace[start] = before + "pass\n"
        else:
            delete.update(range(start, end + 1))
            nxt = end + 1
            if nxt < len(lines) and not lines[nxt].strip():
                delete.add(nxt)

    out = [replace.get(i, line) for i, line in enumerate(lines) if i not in delete]
    result = "".join(out)
    _parse(result)
    return result


_BUILTINS = frozenset(dir(builtins))
_KEEP = frozenset({"self", "cls", "_"})


class _Binder(ast.NodeVisitor):
    """Collect locally bound names and the source positions of every reference to them."""

    def __init__(self) -> None:
        self.imported: set[str] = set()
        self.declared: set[str] = set()  # global / nonlocal / except-as / match captures
        self.functions: dict[str, tuple[int, int]] = {}
        self.bound: dict[str, tuple[int, int]] = {}
        self.refs: list[tuple[str, int, int]] = []
        self.calls_with_keywords: list[ast.Call] = []
        self.def_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        self._class_depth = 0

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imported.add((alias.asname or alias.name).split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.imported.add(alias.asname or alias.name)

    def visit_Global(self, node: ast.Global) -> None:
        self.declared.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.declared.update(node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.declared.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.declared.add(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.declared.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.declared.add(node.name)
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self._class_depth:
            self.declared.add(node.name)  # methods are attributes
        else:
            self.functions.setdefault(node.name, (node.lineno, node.col_offset))
            self.def_nodes.append(node)
        depth, self._class_depth = self._class_depth, 0
        self.generic_visit(node)
        self._class_depth = depth

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_arg(self, node: ast.arg) -> None:
        self.bound.setdefault(node.arg, (node.lineno, node.col_offset))
        self.refs.append((node.arg, node.lineno, node.col_offset))
        if node.annotation:
            self.visit(node.annotation)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.setdefault(node.id, (node.lineno, node.col_offset))
        self.refs.append((node.id, node.lineno, node.col_offset))

    def visit_Call(self, node: ast.Call) -> None:
        if any(kw.arg for kw in node.keywords):
            self.calls_with_keywords.append(node)
        self.generic_visit(node)


def _all_identifiers(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def rename_identifiers(code: str, entry_point: str) -> str:
    """Rename locally bound names to ``v1, v2, ...`` and helper functions to ``f1, f2, ...``.

    The entry point, imports, builtins, attributes, methods and names declared
    global or nonlocal are left alone.
    """
    tree = _parse(code)
    binder = _Binder()
    binder.visit(tree)
    excluded = binder.imported | binder.declared | _BUILTINS | _KEEP | {entry_point}

    def renamable(name: str) -> bool:
        return name not in excluded and not (name.startswith("__") and name.endswith("__"))

    taken = _all_identifiers(tree) | _BUILTINS | set(keyword.kwlist)
    mapping: dict[str, str] = {}

    def fresh(prefix: str) -> str:
        i = 1
        while f"{prefix}{i}" in taken:
            i += 1
        taken.add(f"{prefix}{i}")
        return f"{prefix}{i}"

    funcs = sorted((pos, name) for name, pos in binder.functions.items() if renamable(name))
    for _, name in funcs:
        mapping[name] = fresh("f")
    others = sorted(
        (pos, name) for name, pos in binder.bound.items() if renamable(name) and name not in mapping
    )
    for _, name in others:
        mapping[name] = fresh("v")
    if not mapping:
        return code

    lines = code.splitlines(keepends=True)
    edits: list[tuple[int, int, str, str]] = []  # (line, byte col, old, new)
    for name, line, col in binder.refs:
        if name in mapping:
            edits.append((line, col, name, mapping[name]))
    for node in binder.def_nodes:
        if node.name in mapping:
            raw = lines[node.lineno - 1].encode("utf-8")
            match = re.compile(rb"def\s+" + re.escape(node.name.encode())).search(raw, node.col_offset)
            if not match:
                raise TransformError(f"cannot locate definition of {node.name}")
            edits.append((node.lineno, match.end() - len(node.name.encode()), node.name, mapping[node.name]))
    for call in binder.calls_with_keywords:
        if isinstance(call.func, ast.Name) and call.func.id in mapping and call.func.id in binder.functions:
            for kw in call.keywords:
                if kw.arg and kw.arg in mapping:
                    edits.append((kw.lineno, kw.col_offset, kw.arg, mapping[kw.arg]))

    encoded = [line.encode("utf-8") for line in lines]
    seen: set[tuple[int, int]] = set()
    for line, col, old, new in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        if (line, col) in seen:
            continue
        seen.add((line, col))
        raw = encoded[line - 1]
        if raw[col : col + len(old.encode())] != old.encode():
            raise TransformError(f"position mismatch for {old!r} at {line}:{col}")
        encoded[line - 1] = raw[:col] + new.encode() + raw[col + len(old.encode()) :]
    result = b"".join(encoded).decode("utf-8")
    _parse(result)
    return result


_BLACK_MODE = black.Mode(line_length=88)


def normalize_format(code: str) -> str:
    """Reformat with black (fixed settings); comments and names are kept."""
    try:
        return black.format_str(code, mode=_BLACK_MODE)
    except Exception as exc:  # black raises several exception types on bad input
        raise TransformError(f"black failed: {exc}") from exc


def apply_condition(condition: str, code: str, entry_point: str) -> str:
    steps: dict[str, list[Callable[[str], str]]] = {
        "raw": [],
        "no_comments": [strip_comments],
        "renamed": [lambda c: rename_identifiers(c, entry_point)],
        "formatted": [normalize_format],
        "all": [strip_comments, lambda c: rename_identifiers(c, entry_point), normalize_format],
    }
    if condition not in steps:
        raise ValueError(f"unknown condition {condition!r}")
    for step in steps[condition]:
        code = step(code)
    return code
