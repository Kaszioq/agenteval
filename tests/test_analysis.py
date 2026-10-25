from __future__ import annotations

import numpy as np
import pandas as pd

from agenteval.analysis import _pair_scores, auroc, clopper_pearson, holm, honest_percentile, verdict


def test_pair_score_cancels_constant_position_bias() -> None:
    # A judge that puts 0.7 on position 1 regardless of content: p_own is 0.7 when
    # its solution is first and 0.3 when it is second, so the pair score is 0.5.
    rows = pd.DataFrame(
        {"task_id": ["t1", "t1"], "order": [0, 1], "p_own": [0.7, 0.3]}
    )
    assert np.isclose(_pair_scores(rows)["t1"], 0.5)


def test_pair_score_needs_both_orders() -> None:
    rows = pd.DataFrame(
        {"task_id": ["t1", "t2", "t2"], "order": [0, 0, 1], "p_own": [0.9, 0.6, None]}
    )
    assert _pair_scores(rows).empty


def test_verdicts() -> None:
    assert verdict(0.55, 0.7, 0.5, 0.1) == "effect"
    assert verdict(0.45, 0.58, 0.5, 0.1) == "no effect"
    assert verdict(0.35, 0.65, 0.5, 0.1) == "inconclusive"


def test_auroc_and_percentile() -> None:
    assert auroc(np.array([0.0, 1.0]), np.array([5.0, 6.0])) == 1.0
    assert auroc(np.array([3.0]), np.array([3.0])) == 0.5
    pct = honest_percentile(np.array([0.0, 2.0, 9.0]), np.array([0.0, 1.0, 2.0, 3.0]))
    assert np.allclose(pct, [0.125, 0.625, 1.0])


def test_small_samples_get_no_verdict() -> None:
    assert verdict(0.9, 1.0, 0.5, 0.1, n=4) == "too few (n=4)"
    assert verdict(0.55, 0.7, 0.5, 0.1, n=40) == "effect"


def test_clopper_pearson_is_wide_for_small_samples() -> None:
    low, high = clopper_pearson(4, 4)
    assert high == 1.0 and 0.39 < low < 0.40  # 4/4 correct does not exclude 0.5
    low, high = clopper_pearson(70, 100)
    assert 0.60 < low < 0.61 and 0.78 < high < 0.79


def test_holm_adjustment() -> None:
    adjusted = holm(np.array([0.01, 0.04, 0.03, np.nan]))
    assert np.allclose(adjusted[:3], [0.03, 0.06, 0.06])
    assert np.isnan(adjusted[3])
