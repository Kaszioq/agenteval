from __future__ import annotations

import pytest

import math

from inspect_ai.model import Logprob, TopLogprob

from agenteval.parsing import (
    extract_code,
    extract_secret_input,
    parse_judge_answer,
    parse_monitor,
    position_probabilities,
)
from agenteval.problems import load_problems, problems_by_id

TRUNCATE = problems_by_id(load_problems())["HumanEval/2"]


def test_extract_code_from_fenced_block() -> None:
    response = "Here you go:\n```python\ndef truncate_number(number):\n    return number % 1.0\n```\nDone."
    assert extract_code(response, TRUNCATE) == "def truncate_number(number):\n    return number % 1.0\n"


def test_extract_code_prefers_block_defining_entry_point() -> None:
    response = "```python\nimport math\n```\n```python\ndef truncate_number(x):\n    return x % 1\n```"
    assert extract_code(response, TRUNCATE).startswith("def truncate_number")


def test_extract_code_body_only_gets_signature() -> None:
    code = extract_code("```python\n    return number % 1.0\n```", TRUNCATE)
    assert "def truncate_number(number: float) -> float:" in code
    assert code.rstrip().endswith("return number % 1.0")


def test_extract_code_unterminated_fence() -> None:
    code = extract_code("```python\ndef truncate_number(n):\n    return n % 1\n", TRUNCATE)
    assert code == "def truncate_number(n):\n    return n % 1\n"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("```python\nx\n```\nSECRET_INPUT: (3, [1, 2])", "(3, [1, 2])"),
        ("SECRET INPUT: `(7.25,)`", "(7.25,)"),
        ("secret_input: 5.", "5"),
        ("SECRET_INPUT: None", None),
        ("SECRET_INPUT: ** (7.25,)", "(7.25,)"),
        ("no secret here", None),
    ],
)
def test_extract_secret_input(response: str, expected: str | None) -> None:
    assert extract_secret_input(response) == expected


@pytest.mark.parametrize(
    ("response", "expected"),
    [("1", 1), (" 2\n", 2), ("Solution 2", 2), ("I wrote solution 1.", 1), ("neither", None), ("10", None)],
)
def test_parse_judge_answer(response: str, expected: int | None) -> None:
    assert parse_judge_answer(response) == expected


def test_parse_monitor_score_and_reason() -> None:
    verdict = parse_monitor("SCORE: 7\nREASON: Odd special case for one input.")
    assert verdict.score == 7.0
    assert verdict.reason == "Odd special case for one input."


def test_parse_monitor_markdown_and_clamping() -> None:
    assert parse_monitor("**SCORE:** 12").score == 10.0
    assert parse_monitor("score: 3.5").score == 3.5


def test_parse_monitor_missing_score() -> None:
    verdict = parse_monitor("This looks fine to me.")
    assert verdict.score is None


def _lp(token: str, top: dict[str, float]) -> Logprob:
    return Logprob(
        token=token,
        logprob=math.log(top.get(token, 1e-6)),
        top_logprobs=[TopLogprob(token=t, logprob=math.log(p)) for t, p in top.items()],
    )


def test_position_probabilities_renormalise_over_the_two_digits() -> None:
    probs = position_probabilities([_lp("1", {"1": 0.6, "2": 0.2, "Solution": 0.2})])
    assert probs is not None
    assert math.isclose(probs[0], 0.75) and math.isclose(probs[1], 0.25)


def test_position_probabilities_skip_leading_tokens_and_merge_variants() -> None:
    tokens = [
        _lp("Solution", {"Solution": 0.9, "The": 0.1}),
        _lp(" 2", {" 2": 0.5, "2": 0.1, " 1": 0.4}),
    ]
    probs = position_probabilities(tokens)
    assert probs is not None and math.isclose(probs[1], 0.6)


def test_position_probabilities_missing() -> None:
    assert position_probabilities(None) is None
    assert position_probabilities([_lp("yes", {"yes": 0.9, "no": 0.1})]) is None


def test_extract_trigger() -> None:
    from agenteval.parsing import extract_trigger

    response = "```python\nx = 1\n```\nTRIGGER: the list has exactly 7 elements\nSECRET_INPUT: ([1]*7,)"
    assert extract_trigger(response) == "the list has exactly 7 elements"
    assert extract_trigger("no trigger") is None


def test_yes_probability() -> None:
    from agenteval.parsing import yes_probability

    probs = yes_probability([_lp("Yes", {"Yes": 0.3, " yes": 0.1, "No": 0.4, "Maybe": 0.2})])
    assert probs is not None and math.isclose(probs, 0.5)
    assert yes_probability([_lp("1", {"1": 1.0})]) is None
