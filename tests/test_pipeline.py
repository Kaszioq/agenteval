"""One problem through every stage, offline, with the mock models."""

from __future__ import annotations

from pathlib import Path

from agenteval.analysis import analyze_run
from agenteval.config import ModelSpec, StudyConfig
from agenteval.pipeline import read_jsonl, run_stage, stage_path


def _config(tmp_path: Path) -> StudyConfig:
    return StudyConfig(
        run_name="e2e",
        models={"A": ModelSpec("mockllm/A"), "B": ModelSpec("mockllm/B")},
        problem_ids=["HumanEval/2"],
        backdoor_attempts=2,
        results_dir=tmp_path / "results",
        log_dir=tmp_path / "logs",
        cache_dir=tmp_path / "cache",
        extra={"min_valid_backdoors": 1},
    )


def test_end_to_end_one_problem(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    honest = run_stage(cfg, "honest")
    assert {(r["author"], r["passed"]) for r in honest} == {("A", True), ("B", True)}
    assert all(r["user"].startswith("Complete the following Python function.") for r in honest)

    recognition = run_stage(cfg, "recognition")
    conditions = {r["condition"] for r in recognition}
    # The mock solutions differ only in a comment marker, so removing comments makes
    # the pair identical and it is dropped rather than judged.
    assert conditions == {"raw", "renamed", "formatted"}
    assert len(recognition) == 2 * 3 * 2  # judges x conditions x orders
    assert all(r["correct"] for r in recognition)
    assert {r["own_position"] for r in recognition} == {1, 2}

    backdoor = run_stage(cfg, "backdoor")
    assert all(r["valid"] for r in backdoor)
    assert all(r["secret_input"] == "(7.25,)" for r in backdoor)

    monitor = run_stage(cfg, "monitor")
    assert len(monitor) == 2 * 2 * 2 * 2  # monitors x authors x kinds x views
    assert all(r["valid"] for r in monitor)
    assert "author" not in monitor[0]["user"].lower().replace("authorship", "")

    honest_scores = run_stage(cfg, "monitor_honest")
    assert len(honest_scores) == 2 * 2 * 2  # monitors x authors x views, honest only
    assert {r["kind"] for r in honest_scores} == {"honest"}

    summary = analyze_run(cfg, n_boot=200)
    assert "Exploratory: suspicion on honest code" in summary
    assert (cfg.run_dir / "figures" / "e3x_honest_leniency.png").exists()
    assert "E1 / E2" in summary and "E3" in summary
    for name in ("e1_recognition.png", "e2_ablations.png", "e3_leniency.png"):
        assert (cfg.run_dir / "figures" / name).exists()
    assert (cfg.run_dir / "summary" / "recognition.csv").exists()
    assert read_jsonl(stage_path(cfg, "transforms"))


def test_monitor_stage_stops_when_backdoors_are_scarce(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg = StudyConfig(**{**cfg.__dict__, "extra": {"min_valid_backdoors": 5}})
    run_stage(cfg, "honest")
    run_stage(cfg, "backdoor")
    try:
        run_stage(cfg, "monitor")
    except Exception as exc:
        assert "too few valid backdoors" in str(exc)
    else:
        raise AssertionError("monitor stage should refuse to run")
