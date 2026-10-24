"""HumanEval problems (MIT license, vendored in data/)."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "humaneval.jsonl.gz"


@dataclass(frozen=True)
class Problem:
    task_id: str
    prompt: str
    entry_point: str
    canonical_solution: str
    test: str

    @property
    def slug(self) -> str:
        return self.task_id.replace("/", "_")

    @property
    def canonical_code(self) -> str:
        return self.prompt + self.canonical_solution


def load_problems(
    path: Path = DATA_PATH, limit: int | None = None, ids: list[str] | None = None
) -> list[Problem]:
    with gzip.open(path, "rt") as handle:
        problems = [Problem(**json.loads(line)) for line in handle if line.strip()]
    if ids:
        wanted = set(ids)
        problems = [p for p in problems if p.task_id in wanted]
    if limit is not None:
        problems = problems[:limit]
    return problems


def problems_by_id(problems: list[Problem]) -> dict[str, Problem]:
    return {p.task_id: p for p in problems}
