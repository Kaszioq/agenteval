from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from inspect_ai.model import (
    ChatMessageUser,
    GenerateConfig,
    ModelOutput,
    ModelUsage,
    get_model,
)

from agenteval.config import ModelSpec, StudyConfig
from agenteval.models import CACHE_POLICY, PaidEndpointBlocked, check_endpoint, resolve_model


@pytest.mark.parametrize("name", ["ollama/llama3.1:8b", "mockllm/A"])
def test_free_providers_allowed(name: str) -> None:
    check_endpoint(name)


@pytest.mark.parametrize(
    "name", ["openai/gpt-4o", "mistral/mistral-large", "google/gemini-pro", "openrouter/some-model", "groq/llama"]
)
def test_paid_providers_blocked_by_default(name: str) -> None:
    with pytest.raises(PaidEndpointBlocked):
        check_endpoint(name)


def test_free_tier_needs_its_own_flag() -> None:
    check_endpoint("groq/llama", allow_free_tier_api=True)
    with pytest.raises(PaidEndpointBlocked):
        check_endpoint("openai/gpt-4o", allow_free_tier_api=True)


def test_allow_paid_flag_overrides() -> None:
    check_endpoint("openai/gpt-4o", allow_paid=True)


def test_resolve_model_blocks_before_contacting_anything(tmp_path: Path) -> None:
    cfg = StudyConfig(
        run_name="t",
        models={"A": ModelSpec("openai/gpt-4o"), "B": ModelSpec("mockllm/B")},
        cache_dir=tmp_path,
    )
    with pytest.raises(PaidEndpointBlocked):
        resolve_model("A", cfg)


def test_cache_hit_on_repeat_and_miss_on_new_seed_or_temperature() -> None:
    calls: list[int] = []

    def respond(input, tools, tool_choice, config):  # type: ignore[no-untyped-def]
        calls.append(1)
        output = ModelOutput.from_content(model="counting", content=f"answer {len(calls)}")
        output.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
        return output

    model = get_model("mockllm/counting", custom_outputs=respond, memoize=False)
    messages = [ChatMessageUser(content="same prompt")]

    async def ask(temperature: float, seed: int) -> str:
        config = GenerateConfig(temperature=temperature, seed=seed)
        out = await model.generate(messages, config=config, cache=CACHE_POLICY)
        return out.completion

    async def scenario() -> list[str]:
        return [
            await ask(0.0, 1),
            await ask(0.0, 1),  # identical key: served from cache
            await ask(0.0, 2),  # new seed: miss
            await ask(0.7, 1),  # new temperature: miss
        ]

    answers = asyncio.run(scenario())
    assert answers[0] == answers[1] == "answer 1"
    assert answers[2] == "answer 2" and answers[3] == "answer 3"
    assert len(calls) == 3
