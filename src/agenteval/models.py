"""Model construction with a hard block on paid endpoints."""

from __future__ import annotations

import os

from inspect_ai.model import CachePolicy, GenerateConfig, Model, get_model

from agenteval.config import ModelSpec, StudyConfig

# Providers that run locally or offline and can never cost money.
FREE_PROVIDERS = frozenset({"ollama", "mockllm"})
# Hosted providers with a free tier. Allowed only behind an explicit flag,
# because the same key can also be billed once a paid plan is attached.
FREE_TIER_PROVIDERS = frozenset({"groq"})

# Responses never expire: the key already covers model, messages, temperature and seed.
CACHE_POLICY = CachePolicy(expiry=None)


class PaidEndpointBlocked(RuntimeError):
    """Raised when a model would be served by an endpoint that may charge money."""


def provider_of(model_name: str) -> str:
    if "/" not in model_name:
        raise ValueError(f"model name must look like 'provider/model', got {model_name!r}")
    return model_name.split("/", 1)[0]


def check_endpoint(
    model_name: str, *, allow_paid: bool = False, allow_free_tier_api: bool = False
) -> None:
    provider = provider_of(model_name)
    if provider in FREE_PROVIDERS:
        return
    if provider in FREE_TIER_PROVIDERS and (allow_free_tier_api or allow_paid):
        return
    if allow_paid:
        return
    raise PaidEndpointBlocked(
        f"{model_name!r} uses provider {provider!r}, which may be billed. "
        "The study budget is zero: set allow_paid: true in the config to override."
    )


def configure_cache(cfg: StudyConfig) -> None:
    os.environ.setdefault("INSPECT_CACHE_DIR", str(cfg.cache_dir.resolve()))


def resolve_model(model_id: str, cfg: StudyConfig) -> Model:
    spec: ModelSpec = cfg.models[model_id]
    check_endpoint(
        spec.name, allow_paid=cfg.allow_paid, allow_free_tier_api=cfg.allow_free_tier_api
    )
    configure_cache(cfg)
    config = GenerateConfig(seed=cfg.seed, max_connections=cfg.max_connections)
    if provider_of(spec.name) == "mockllm":
        from agenteval.mock import mock_outputs

        return get_model(
            spec.name, config=config, custom_outputs=mock_outputs(model_id), memoize=False
        )
    return get_model(spec.name, config=config, base_url=spec.base_url)
