from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from agenteval.problems import load_problems
from agenteval.sandbox import run_tests
from agenteval.transforms import (
    CONDITIONS,
    TransformError,
    apply_condition,
    normalize_format,
    rename_identifiers,
    strip_comments,
)

SAMPLE = '''\
from typing import List


def helper(xs: List[int]) -> int:
    """Sum of squares."""
    total = 0  # running total
    for x in xs:
        total += x * x
    return total


def solve(values: List[int], scale: int = 2) -> int:
    """Docstring
    over two lines."""

    # scale the result
    result = helper(values) * scale
    pairs = sorted(values, key=lambda item: -item)
    return result + len([p for p in pairs if p])
'''


def test_strip_comments_removes_comments_and_docstrings_only() -> None:
    out = strip_comments(SAMPLE)
    assert "#" not in out and '"""' not in out
    assert "    total = 0\n" in out  # trailing comment removed, line kept as written
    assert "result = helper(values) * scale" in out
    assert "def helper(xs: List[int]) -> int:\n    total = 0" in out


def test_strip_comments_keeps_body_valid_when_only_docstring() -> None:
    out = strip_comments('def f():\n    """Only a docstring."""\n')
    assert out == "def f():\n    pass\n"


def test_strip_comments_keeps_hash_inside_strings() -> None:
    code = "def f():\n    return '# not a comment'  # a comment\n"
    assert strip_comments(code) == "def f():\n    return '# not a comment'\n"


def test_rename_keeps_entry_point_builtins_and_keywords() -> None:
    out = rename_identifiers(SAMPLE, "solve")
    assert "def solve(" in out and "def f1(" in out
    assert "helper" not in out.replace("# running total", "")
    assert "sorted(" in out and "key=lambda" in out  # builtin keyword argument kept
    assert "List" in out and "len(" in out
    assert "# running total" in out  # comments untouched
    code_only = strip_comments(out)
    for name in ("values", "scale", "result", "total"):
        assert name not in code_only


def test_rename_updates_keyword_arguments_of_own_functions() -> None:
    code = "def g(a, b):\n    return a - b\n\ndef solve(x):\n    return g(b=x, a=1)\n"
    out = rename_identifiers(code, "solve")
    namespace: dict = {}
    exec(compile(out, "<t>", "exec"), namespace)
    assert namespace["solve"](5) == -4
    assert "g(" not in out


def test_rename_handles_fstrings_and_nested_scopes() -> None:
    code = (
        "def solve(n):\n"
        "    label = 'x'\n"
        "    def inner(k):\n"
        "        return f'{label}{k}'\n"
        "    return [inner(i) for i in range(n)]\n"
    )
    out = rename_identifiers(code, "solve")
    namespace: dict = {}
    exec(compile(out, "<t>", "exec"), namespace)
    assert namespace["solve"](2) == ["x0", "x1"]
    assert "label" not in out and "inner" not in out


def test_rename_leaves_global_declarations_alone() -> None:
    code = "count = 0\ndef solve():\n    global count\n    count += 1\n    return count\n"
    assert "global count" in rename_identifiers(code, "solve")


def test_format_keeps_comments_and_names() -> None:
    code = "def solve( a,b ):\n  # keep me\n  return a+b\n"
    out = normalize_format(code)
    assert out == "def solve(a, b):\n    # keep me\n    return a + b\n"


def test_transforms_reject_invalid_code() -> None:
    with pytest.raises(TransformError):
        strip_comments("def broken(:\n")
    with pytest.raises(TransformError):
        normalize_format("def broken(:\n")


def _check(args):
    problem, condition = args
    code = apply_condition(condition, problem.canonical_code, problem.entry_point)
    return problem.task_id, condition, run_tests(problem, code).passed


@pytest.mark.parametrize("condition", CONDITIONS)
def test_transform_preserves_behaviour_on_all_canonical_solutions(condition: str) -> None:
    problems = load_problems()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_check, [(p, condition) for p in problems]))
    broken = [(tid, cond) for tid, cond, ok in results if not ok]
    assert not broken
