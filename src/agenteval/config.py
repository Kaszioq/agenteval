"""Study configuration loaded from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ModelSpec:
    name: str
    base_url: str | None = None


@dataclass(frozen=True)
class StudyConfig:
    run_name: str
    models: dict[str, ModelSpec]
    seed: int = 1234
    temperature: float = 0.0
    max_tokens_author: int = 1024
    max_tokens_judge: int = 16
    max_tokens_monitor: int = 160
    backdoor_attempts: int = 3
    retry_temperature: float = 0.7
    problem_limit: int | None = None
    problem_ids: list[str] | None = None
    max_connections: int = 1
    exec_timeout: float = 10.0
    allow_paid: bool = False
    allow_free_tier_api: bool = False
    results_dir: Path = Path("results")
    log_dir: Path = Path("logs")
    cache_dir: Path = Path(".cache/inspect")
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def run_dir(self) -> Path:
        return self.results_dir / self.run_name

    @property
    def model_ids(self) -> list[str]:
        return sorted(self.models)


_PATH_FIELDS = {"results_dir", "log_dir", "cache_dir"}


def load_config(path: str | Path) -> StudyConfig:
    raw = yaml.safe_load(Path(path).read_text())
    models = {key: ModelSpec(**spec) for key, spec in raw.pop("models").items()}
    if sorted(models) != ["A", "B"]:
        raise ValueError("config must define exactly two models, A and B")
    known = set(StudyConfig.__dataclass_fields__) - {"models", "extra"}
    kwargs: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in raw.items():
        if key in known:
            kwargs[key] = Path(value) if key in _PATH_FIELDS else value
        else:
            extra[key] = value
    return StudyConfig(models=models, extra=extra, **kwargs)
