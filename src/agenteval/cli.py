"""Command line: ``agenteval run`` and ``agenteval analyze``."""

from __future__ import annotations

import argparse
import sys

from agenteval.config import load_config
from agenteval.pipeline import STAGES, StageError, run_stage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agenteval")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one stage, or all stages in order")
    run.add_argument("stage", choices=[*STAGES, "all"])
    run.add_argument("--config", default="configs/study.yaml")
    run.add_argument("--force", action="store_true", help="continue past the backdoor-count check")

    analyze = sub.add_parser("analyze", help="compute statistics, tables and figures for a run")
    analyze.add_argument("--config", default="configs/study.yaml")
    analyze.add_argument("--bootstrap", type=int, default=10_000)

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    if args.command == "run":
        stages = STAGES if args.stage == "all" else (args.stage,)
        try:
            for stage in stages:
                rows = run_stage(cfg, stage, force=args.force)
                print(f"[{stage}] {len(rows)} rows -> {cfg.run_dir / 'stages'}")
        except StageError as exc:
            print(f"stopped: {exc}", file=sys.stderr)
            return 2
        return 0

    from agenteval.analysis import analyze_run

    summary = analyze_run(cfg, n_boot=args.bootstrap)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
