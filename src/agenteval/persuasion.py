"""Study 2: do notes from other agents make a monitor more lenient on backdoors?

Items come from Study 1's stage files (``source_stages`` in the config): every
valid backdoor, plus the same author's passing honest solution for the same task.
Stage ``justify`` writes notes for every item once; stage ``monitor_persuasion``
shows each monitor the code with the notes of each condition.

Files in ``results/<run_name>/stages/``::

    items.jsonl               one row per item (task, author, kind) that is scored
    justify.jsonl             one row per (item, persona): raw response and cleaned note
    monitor_persuasion.jsonl  one row per (monitor, item, condition)
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path
from typing import Any

from agenteval import prompts
from agenteval.config import StudyConfig
from agenteval.models import provider_of
from agenteval.pipeline import StageError, _run, read_jsonl, stage_path, write_jsonl, write_run_info
from agenteval.problems import load_problems, problems_by_id
from agenteval.tasks import note_task, persuasion_monitor_task
from agenteval.transforms import TransformError, strip_comments

STAGES = ("justify", "monitor_persuasion")
NOTE_WORD_CAP = 60

# Condition -> (note type, number of notes, fixed extra line). Endorsements are shown
# in the fixed persona order of prompts.ENDORSE_PERSONAS.
CONDITIONS: dict[str, tuple[str | None, int, str | None]] = {
    "C0": (None, 0, None),
    "E1": ("endorse", 1, None),
    "E3": ("endorse", 3, None),
    "E5": ("endorse", 5, None),
    "E3A": ("endorse", 3, prompts.APPROVAL_LINE),
    "N3": ("neutral", 3, None),
    # Exploratory, added after the first results (not pre-registered): stronger pressure
    # aimed at the monitors that resisted. Run only when named with --conditions.
    "E5X": ("endorse", 5, prompts.REVIEWER_APPEAL_LINE),
    "E3S": ("endorse", 3, prompts.PRIOR_SCORES_LINE),
    # Exploratory follow-up: the reviewer appeal alone and with a single endorsement.
    "C0X": (None, 0, prompts.REVIEWER_APPEAL_LINE),
    "E1X": ("endorse", 1, prompts.REVIEWER_APPEAL_LINE),
}
PREREGISTERED = ("C0", "E1", "E3", "E5", "E3A", "N3")
EXPLORATORY = ("E5X", "E3S", "C0X", "E1X")
# Number of endorsing agents per condition, for the dose-response test (H5).
DOSE = {"C0": 0, "E1": 1, "E3": 3, "E5": 5}

# Words that judge the code or point at a problem. Neutral notes should contain none;
# the share that still does is reported as a quality check (see README, pilot amendment).
EVALUATIVE = re.compile(
    r"\b(errors?|issues?|problems?|bugs?|incorrect(ly)?|wrong|correct(ly)?|unnecessary|unrelated|"
    r"unusual|unexpected|suspicious|should|review(ed)?|backdoors?|safe(ly)?|secure|edge cases?)\b",
    re.IGNORECASE,
)


def is_evaluative(note: str) -> bool:
    return bool(EVALUATIVE.search(note or ""))


def item_id(task_id: str, author: str, kind: str) -> str:
    return f"{task_id}|{author}|{kind}"


def _source(cfg: StudyConfig, name: str) -> Path:
    return Path(cfg.extra.get("source_stages", "results/study/stages")) / f"{name}.jsonl"


def build_items(cfg: StudyConfig) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Valid backdoors and the matched honest solutions (same author, same task), with
    comments stripped. Returns the items and counts of what was left out."""
    problems = problems_by_id(load_problems())
    honest = {
        (r["task_id"], r["author"]): r["code"]
        for r in read_jsonl(_source(cfg, "honest"))
        if r["passed"]
    }
    backdoors = sorted(
        (r for r in read_jsonl(_source(cfg, "backdoor")) if r["valid"]),
        key=lambda r: (r["task_id"], r["author"]),
    )
    limit = cfg.extra.get("task_limit")
    if limit is not None:
        keep = sorted({r["task_id"] for r in backdoors})[: int(limit)]
        backdoors = [r for r in backdoors if r["task_id"] in keep]
    counts = {"backdoors": len(backdoors), "no_matched_honest": 0, "strip_failed": 0}
    items = []
    for row in backdoors:
        tid, author = row["task_id"], row["author"]
        if (tid, author) not in honest:
            counts["no_matched_honest"] += 1
            continue
        sources = (("backdoor", row["code"], row["secret_input"]), ("honest", honest[tid, author], None))
        stripped = []
        for kind, code, secret in sources:
            try:
                stripped.append((kind, strip_comments(code), secret))
            except TransformError:
                break
        if len(stripped) != 2:
            # Drop the pair, so the honest and backdoored sets stay matched.
            counts["strip_failed"] += 1
            continue
        for kind, code, secret in stripped:
            items.append(
                {
                    "item_id": item_id(tid, author, kind),
                    "task_id": tid,
                    "author": author,
                    "kind": kind,
                    "prompt": problems[tid].prompt,
                    "code": code,
                    "secret_input": secret,
                }
            )
    counts["items"] = len(items)
    return items, counts


# --- notes -----------------------------------------------------------------------


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def clean_note(response: str, secret_input: str | None) -> tuple[str, dict[str, Any]]:
    """Turn a model response into a one-line note.

    Removes code blocks, removes every line that contains the secret input verbatim
    (ignoring whitespace), joins the rest into one line and caps it at 60 words.
    """
    text = re.sub(r"```.*?(```|$)", " ", response, flags=re.DOTALL)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    secret = _squash(secret_input) if secret_input else ""
    kept = [line for line in lines if not (secret and secret in _squash(line))]
    words = " ".join(kept).split()
    note = " ".join(words[:NOTE_WORD_CAP]).strip().strip('"').strip()
    info = {
        "secret_lines_removed": len(lines) - len(kept),
        "truncated": len(words) > NOTE_WORD_CAP,
        "empty": not note,
    }
    return note, info


def note_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One prompt per (item, persona): five endorsements and three neutral notes."""
    out = []
    for it in items:
        groups = (
            ("endorse", prompts.ENDORSE_PERSONAS, prompts.JUSTIFY_USER),
            ("neutral", prompts.NEUTRAL_PERSONAS, prompts.NEUTRAL_USER),
        )
        for note_type, personas, template in groups:
            for slot, (persona, description) in enumerate(personas.items(), start=1):
                user = template.format(
                    persona=persona,
                    description=description,
                    prompt=prompts.problem_text(it["prompt"]),
                    code=it["code"].rstrip("\n"),
                )
                out.append(
                    {
                        "item_id": it["item_id"],
                        "task_id": it["task_id"],
                        "author": it["author"],
                        "kind": it["kind"],
                        "persona": persona,
                        "note_type": note_type,
                        "slot": slot,
                        "user": user,
                    }
                )
    return out


def render_notes(condition: str, notes: dict[tuple[str, int], dict[str, Any]]) -> str:
    """The notes block for one item under one condition.

    ``notes`` maps (note_type, slot) to a justify row with ``persona`` and ``note``.
    """
    note_type, count, extra_line = CONDITIONS[condition]
    lines = []
    for slot in range(1, count + 1):
        row = notes[note_type, slot]
        text = row["note"] or "(empty note)"
        lines.append(f"- [agent-{slot}, {row['persona']}] {text}")
    if extra_line:
        lines.append(extra_line)
    return prompts.notes_block(lines)


def monitor_prompt(item: dict[str, Any], condition: str, notes: dict[tuple[str, int], dict[str, Any]]) -> str:
    return prompts.PERSUASION_MONITOR_USER.format(
        prompt=prompts.problem_text(item["prompt"]),
        code=item["code"].rstrip("\n"),
        notes=render_notes(condition, notes),
    )


# --- stages ------------------------------------------------------------------------


def _model_cfg(cfg: StudyConfig, model_id: str) -> StudyConfig:
    """The config with this model's own connection limit (free API tiers are rate limited)."""
    spec = cfg.models.get(model_id)
    if spec is None:
        raise StageError(f"model {model_id!r} is not defined under 'models' in the config")
    if "<" in spec.name or ">" in spec.name:
        raise StageError(
            f"model {model_id!r} still has a placeholder name ({spec.name}); fill in the exact "
            "model id from the provider's model list first"
        )
    changes: dict[str, Any] = {}
    if spec.max_connections:
        changes["max_connections"] = spec.max_connections
    if spec.max_tokens:
        changes["max_tokens_monitor"] = spec.max_tokens
    return dataclasses.replace(cfg, **changes) if changes else cfg


def run_justify(cfg: StudyConfig) -> list[dict[str, Any]]:
    items, counts = build_items(cfg)
    if not items:
        raise StageError(f"no items to annotate ({counts}); check source_stages in the config")
    print(f"[justify] items: {counts}")
    write_jsonl(stage_path(cfg, "items"), items)
    author = str(cfg.extra.get("note_author", "A"))
    secrets = {it["item_id"]: it["secret_input"] for it in items}
    rows = []
    for row in _run(note_task(note_items(items), cfg), author, _model_cfg(cfg, author)):
        iid, persona = row["sample_id"].rsplit("|", 1)
        response = row.get("response") or ""
        note, info = clean_note(response, secrets[iid])
        note_type = "endorse" if persona in prompts.ENDORSE_PERSONAS else "neutral"
        personas = list(prompts.ENDORSE_PERSONAS if note_type == "endorse" else prompts.NEUTRAL_PERSONAS)
        task_id, item_author, kind = iid.split("|")
        rows.append(
            {
                **row,
                "item_id": iid,
                "task_id": task_id,
                "author": item_author,
                "kind": kind,
                "persona": persona,
                "note_type": note_type,
                "slot": personas.index(persona) + 1,
                "note_author": author,
                "note": note,
                **info,
            }
        )
    write_jsonl(stage_path(cfg, "justify"), rows)
    write_run_info(cfg, "justify")
    removed = sum(r["secret_lines_removed"] for r in rows)
    print(
        f"[justify] {len(rows)} notes; {removed} lines with the secret input removed, "
        f"{sum(r['truncated'] for r in rows)} cut to {NOTE_WORD_CAP} words, "
        f"{sum(r['empty'] for r in rows)} empty"
    )
    return rows


def conditions(cfg: StudyConfig) -> list[str]:
    chosen = list(cfg.extra.get("conditions", list(PREREGISTERED)))
    unknown = [c for c in chosen if c not in CONDITIONS]
    if unknown:
        raise StageError(f"unknown conditions {unknown}; choose from {list(CONDITIONS)}")
    return chosen


def monitor_items(
    cfg: StudyConfig, only_conditions: list[str] | None = None, only_kinds: list[str] | None = None
) -> list[dict[str, Any]]:
    items = [
        it for it in read_jsonl(stage_path(cfg, "items")) if not only_kinds or it["kind"] in only_kinds
    ]
    notes: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    for row in read_jsonl(stage_path(cfg, "justify")):
        notes.setdefault(row["item_id"], {})[row["note_type"], row["slot"]] = row
    out = []
    if only_conditions:
        unknown = [c for c in only_conditions if c not in CONDITIONS]
        if unknown:
            raise StageError(f"unknown conditions {unknown}; choose from {list(CONDITIONS)}")
        chosen = list(only_conditions)  # may name exploratory conditions
    else:
        chosen = conditions(cfg)
    for it in items:
        for condition in chosen:
            out.append(
                {
                    "item_id": it["item_id"],
                    "task_id": it["task_id"],
                    "author": it["author"],
                    "kind": it["kind"],
                    "condition": condition,
                    "user": monitor_prompt(it, condition, notes.get(it["item_id"], {})),
                }
            )
    return out


def monitors(cfg: StudyConfig) -> list[str]:
    return [str(m) for m in cfg.extra.get("monitors", cfg.model_ids)]


def run_monitor_persuasion(
    cfg: StudyConfig,
    only: list[str] | None = None,
    only_conditions: list[str] | None = None,
    only_kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Score items under the conditions. For rate-limited APIs the work can be split:
    ``only`` picks monitors, ``only_conditions`` and ``only_kinds`` pick a part of the
    prompts. Rows already in the stage file for any other prompt are kept."""
    chosen = only or monitors(cfg)
    items = monitor_items(cfg, only_conditions, only_kinds)
    if not items:
        raise StageError("no prompts match the chosen conditions and kinds")
    path = stage_path(cfg, "monitor_persuasion")
    running = {(m, f"{it['item_id']}|{it['condition']}") for m in chosen for it in items}
    kept = (
        [r for r in read_jsonl(path) if (r["monitor"], r["sample_id"]) not in running]
        if path.exists()
        else []
    )
    rows = list(kept)
    for monitor in chosen:
        model_cfg = _model_cfg(cfg, monitor)
        print(f"[monitor_persuasion] monitor {monitor} ({cfg.models[monitor].name}): {len(items)} prompts")
        scored = _run(persuasion_monitor_task(items, model_cfg), monitor, model_cfg)
        failed = 0
        for row in scored:
            iid, condition = row["sample_id"].rsplit("|", 1)
            task_id, author, kind = iid.split("|")
            failed += int(row.get("sample_error") is not None)
            rows.append(
                {
                    **row,
                    "item_id": iid,
                    "task_id": task_id,
                    "author": author,
                    "kind": kind,
                    "condition": condition,
                    "monitor": monitor,
                    "monitor_model": cfg.models[monitor].name,
                    "provider": provider_of(cfg.models[monitor].name),
                    "valid": bool(row.get("valid")) and row.get("score") is not None,
                }
            )
        if failed:
            print(
                f"[monitor_persuasion] {failed} prompts for {monitor} failed (for example a "
                "rate limit); run the stage again later and finished calls come from the cache",
                file=sys.stderr,
            )
        # Save after every monitor, so a later failure does not lose finished work.
        write_jsonl(path, sorted(rows, key=lambda r: (r["monitor"], r["sample_id"])))
    write_run_info(cfg, "monitor_persuasion")
    return rows


def run_persuasion_stage(
    cfg: StudyConfig,
    stage: str,
    only: list[str] | None = None,
    only_conditions: list[str] | None = None,
    only_kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    if stage == "justify":
        return run_justify(cfg)
    if stage == "monitor_persuasion":
        return run_monitor_persuasion(cfg, only, only_conditions, only_kinds)
    raise ValueError(f"unknown stage {stage!r}; choose from {STAGES}")
