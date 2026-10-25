"""Inspect tasks for each stage of the study.

Each solver writes its full result (prompts, responses, parsed fields, grading)
to the sample store, so every row exported from an Inspect log can be traced
back to the exact model call.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import anyio
from inspect_ai import Task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageUser,
    GenerateConfig,
    ModelOutput,
    get_model,
)
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, solver

from agenteval import prompts
from agenteval.config import StudyConfig
from agenteval.models import CACHE_POLICY
from agenteval.parsing import (
    extract_code,
    extract_secret_input,
    parse_judge_answer,
    parse_monitor,
    position_probabilities,
)
from agenteval.problems import Problem
from agenteval.sandbox import check_backdoor, run_tests

RESULT_KEY = "agenteval_result"
JUDGE_TOP_LOGPROBS = 20


async def _generate_output(
    system: str, user: str, config: GenerateConfig
) -> tuple[ModelOutput, list[Any]]:
    messages = [ChatMessageSystem(content=system), ChatMessageUser(content=user)]
    output = await get_model().generate(messages, config=config, cache=CACHE_POLICY)
    return output, [*messages, output.message]


async def _generate(system: str, user: str, config: GenerateConfig) -> tuple[str, list[Any]]:
    output, messages = await _generate_output(system, user, config)
    return output.completion, messages


@scorer(metrics=[mean()])
def stored_value(field: str):  # type: ignore[no-untyped-def]
    async def score(state: TaskState, target: Target) -> Score:
        result = state.store.get(RESULT_KEY, {})
        value = result.get(field)
        return Score(value=float(value) if value is not None else 0.0, metadata=result)

    return score


# --- authors -----------------------------------------------------------------


@solver
def author_solver(problems: dict[str, Problem], cfg: StudyConfig, backdoor: bool):  # type: ignore[no-untyped-def]
    """Honest authors answer once. Backdoor authors get up to ``backdoor_attempts``
    turns in one conversation; after an invalid attempt the next turn says why it
    was rejected (see ``prompts.backdoor_feedback``)."""
    attempts_allowed = cfg.backdoor_attempts if backdoor else 1

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        problem = problems[state.metadata["task_id"]]
        if backdoor:
            user = prompts.backdoor_user(problem.prompt, problem.entry_point)
        else:
            user = prompts.HONEST_USER.format(prompt=prompts.problem_text(problem.prompt))
        messages: list[Any] = [
            ChatMessageSystem(content=prompts.AUTHOR_SYSTEM),
            ChatMessageUser(content=user),
        ]
        attempts: list[dict[str, Any]] = []
        for k in range(attempts_allowed):
            config = GenerateConfig(
                temperature=cfg.temperature if k == 0 else cfg.retry_temperature,
                seed=cfg.seed + k,
                max_tokens=cfg.max_tokens_author,
            )
            output = await get_model().generate(messages, config=config, cache=CACHE_POLICY)
            messages = [*messages, output.message]
            response = output.completion
            code = extract_code(response, problem)
            attempt: dict[str, Any] = {
                "attempt": k,
                "temperature": config.temperature,
                "seed": config.seed,
                "response": response,
                "code": code,
            }
            if backdoor:
                secret = extract_secret_input(response)
                outcome = await anyio.to_thread.run_sync(
                    lambda: check_backdoor(problem, code, secret, cfg.exec_timeout)
                )
                attempt.update(secret_input=secret, **asdict(outcome))
                ok = outcome.valid
            else:
                tests = await anyio.to_thread.run_sync(
                    lambda: run_tests(problem, code, cfg.exec_timeout)
                )
                attempt.update(passed=tests.passed, detail=tests.detail)
                ok = tests.passed
            attempts.append(attempt)
            if ok:
                break
            if backdoor and k + 1 < attempts_allowed:
                feedback = prompts.backdoor_feedback(outcome, problem.prompt, problem.entry_point)
                attempt["feedback"] = feedback
                messages = [*messages, ChatMessageUser(content=feedback)]
        state.messages = messages
        final = attempts[-1]
        state.store.set(
            RESULT_KEY,
            {
                "task_id": problem.task_id,
                "system": prompts.AUTHOR_SYSTEM,
                "user": user,
                "ok": bool(final.get("valid", final.get("passed", False))),
                "final": final,
                "attempts": attempts,
            },
        )
        return state

    return solve


def author_task(problems: list[Problem], cfg: StudyConfig, backdoor: bool) -> Task:
    by_id = {p.task_id: p for p in problems}
    samples = [Sample(id=p.task_id, input=p.task_id, metadata={"task_id": p.task_id}) for p in problems]
    return Task(
        name="backdoor_author" if backdoor else "honest_author",
        dataset=MemoryDataset(samples),
        solver=author_solver(by_id, cfg, backdoor),
        scorer=stored_value("ok"),
    )


# --- recognition judge -------------------------------------------------------


@solver
def judge_solver(cfg: StudyConfig):  # type: ignore[no-untyped-def]
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        md = state.metadata
        user = prompts.JUDGE_USER.format(
            prompt=prompts.problem_text(md["prompt"]),
            code_1=md["code_1"].rstrip("\n"),
            code_2=md["code_2"].rstrip("\n"),
        )
        config = GenerateConfig(
            temperature=cfg.temperature,
            seed=cfg.seed,
            max_tokens=cfg.max_tokens_judge,
            logprobs=True,
            top_logprobs=JUDGE_TOP_LOGPROBS,
        )
        output, messages = await _generate_output(prompts.JUDGE_SYSTEM, user, config)
        response = output.completion
        state.messages = messages
        answer = parse_judge_answer(response)
        logprobs = output.choices[0].logprobs if output.choices else None
        probs = position_probabilities(logprobs.content if logprobs else None)
        p_own = None
        if probs is not None:
            p_own = probs[0] if md["own_position"] == 1 else probs[1]
        state.store.set(
            RESULT_KEY,
            {
                "task_id": md["task_id"],
                "condition": md["condition"],
                "order": md["order"],
                "own_position": md["own_position"],
                "user": user,
                "response": response,
                "answer": answer,
                "valid": answer is not None,
                "correct": answer == md["own_position"],
                "p_first": probs[0] if probs else None,
                "p_own": p_own,
            },
        )
        return state

    return solve


def recognition_task(pairs: list[dict[str, Any]], cfg: StudyConfig) -> Task:
    """``pairs``: dicts with task_id, condition, prompt, own_code, other_code."""
    samples = []
    for pair in pairs:
        for order in (0, 1):
            own_position = 1 if order == 0 else 2
            codes = (pair["own_code"], pair["other_code"])
            if order == 1:
                codes = codes[::-1]
            samples.append(
                Sample(
                    id=f"{pair['task_id']}|{pair['condition']}|{order}",
                    input=pair["task_id"],
                    metadata={
                        "task_id": pair["task_id"],
                        "condition": pair["condition"],
                        "order": order,
                        "own_position": own_position,
                        "prompt": pair["prompt"],
                        "code_1": codes[0],
                        "code_2": codes[1],
                    },
                )
            )
    return Task(
        name="recognition_judge",
        dataset=MemoryDataset(samples),
        solver=judge_solver(cfg),
        scorer=stored_value("correct"),
    )


# --- monitor -----------------------------------------------------------------


@solver
def monitor_solver(cfg: StudyConfig):  # type: ignore[no-untyped-def]
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        md = state.metadata
        user = prompts.MONITOR_USER.format(
            prompt=prompts.problem_text(md["prompt"]), code=md["code"].rstrip("\n")
        )
        config = GenerateConfig(
            temperature=cfg.temperature, seed=cfg.seed, max_tokens=cfg.max_tokens_monitor
        )
        response, messages = await _generate(prompts.MONITOR_SYSTEM, user, config)
        state.messages = messages
        verdict = parse_monitor(response)
        state.store.set(
            RESULT_KEY,
            {
                "task_id": md["task_id"],
                "author": md["author"],
                "kind": md["kind"],
                "view": md["view"],
                "user": user,
                "response": response,
                "score": verdict.score,
                "reason": verdict.reason,
                "valid": verdict.score is not None,
            },
        )
        return state

    return solve


def monitor_task(items: list[dict[str, Any]], cfg: StudyConfig) -> Task:
    """``items``: dicts with task_id, author, kind (honest/backdoor), view, prompt, code."""
    samples = [
        Sample(
            id=f"{it['task_id']}|{it['author']}|{it['kind']}|{it['view']}",
            input=it["task_id"],
            metadata=dict(it),
        )
        for it in items
    ]
    return Task(
        name="monitor",
        dataset=MemoryDataset(samples),
        solver=monitor_solver(cfg),
        scorer=stored_value("score"),
    )
