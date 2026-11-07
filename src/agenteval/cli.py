"""Command line: ``agenteval run`` and ``agenteval analyze``."""

from __future__ import annotations

import argparse
import sys

from agenteval.config import load_config
from agenteval.persuasion import STAGES as PERSUASION_STAGES
from agenteval.persuasion import run_persuasion_stage
from agenteval.pipeline import EXTRA_STAGES, STAGES, StageError, run_stage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agenteval")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one stage, or all stages in order")
    run.add_argument("stage", choices=[*STAGES, *EXTRA_STAGES, *PERSUASION_STAGES, "all"])
    run.add_argument("--config", default="configs/study.yaml")
    run.add_argument("--force", action="store_true", help="continue past the backdoor-count check")
    run.add_argument(
        "--monitor",
        action="append",
        help="Study 2: run monitor_persuasion for this monitor only (repeatable); "
        "rows of other monitors already in the stage file are kept",
    )
    run.add_argument("--conditions", help="Study 2: comma-separated conditions to run, e.g. C0,E3")
    run.add_argument("--kinds", help="Study 2: comma-separated item kinds to run: backdoor,honest")

    analyze = sub.add_parser("analyze", help="compute statistics, tables and figures for a run")
    analyze.add_argument("--config", default="configs/study.yaml")
    analyze.add_argument("--bootstrap", type=int, default=10_000)

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.command == "run":
        persuasion = cfg.extra.get("study") == "persuasion"
        if args.stage == "all":
            stages = PERSUASION_STAGES if persuasion else STAGES
        else:
            stages = (args.stage,)
        if persuasion != all(s in PERSUASION_STAGES for s in stages):
            print(f"stage {args.stage!r} does not belong to the study in {args.config}", file=sys.stderr)
            return 2
        try:
            for stage in stages:
                if persuasion:
                    rows = run_persuasion_stage(
                        cfg,
                        stage,
                        only=args.monitor,
                        only_conditions=args.conditions.split(",") if args.conditions else None,
                        only_kinds=args.kinds.split(",") if args.kinds else None,
                    )
                else:
                    rows = run_stage(cfg, stage, force=args.force)
                print(f"[{stage}] {len(rows)} rows -> {cfg.run_dir / 'stages'}")
        except StageError as exc:
            print(f"stopped: {exc}", file=sys.stderr)
            return 2
        return 0

    if cfg.extra.get("study") == "persuasion":
        from agenteval.analysis import analyze_persuasion

        summary = analyze_persuasion(cfg, n_boot=args.bootstrap)
    else:
        from agenteval.analysis import analyze_run

        summary = analyze_run(cfg, n_boot=args.bootstrap)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
