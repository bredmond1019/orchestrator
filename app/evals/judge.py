"""Blind, randomized LLM-as-judge scorer for the offline eval harness.

Implements the third Project-H scoring strategy referenced by the OR.U block
contract (``planning/master-plan.md`` -> "OR.1.H"): an LLM-as-judge harness
for open-ended prose outputs that

1. **strips model identity** from every candidate before it reaches the judge
   prompt — candidates are addressed only by an anonymous label
   (``candidate_1``, ``candidate_2``, ...);
2. **randomizes candidate presentation order** (an injectable ``rng``/``seed``
   makes this reproducible in tests);
3. scores each candidate against a rubric rendered from
   ``app/prompts/eval_judge.j2`` via ``PromptManager`` (standing rule 2 — no
   hardcoded prompt strings); and
4. maps the judge's per-label verdicts back to the original candidates after
   de-randomization, returning a ``evals.scorers.ScoreResult`` per candidate.

The judge model call goes through the same agent/LLM seam
(``pydantic_ai.Agent`` over an Anthropic model) used by ``core.nodes.agent``
elsewhere in this app, but as a plain injectable callable rather than a
``Node`` subclass — this module is an offline library (like
``scripts/index_brain.py``), not a workflow node. The default judge model is
the frontier Anthropic model (``claude-opus-4-8``); tests inject a stub
``judge_call`` instead of hitting the network.
"""

import random
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from services.prompt_loader import PromptManager

from evals.scorers import ScoreResult

# Frontier Anthropic model — the default judge per the block contract ("frontier
# model is the default judge"). Verified against the current model catalog.
DEFAULT_JUDGE_MODEL = "claude-opus-4-8"


class JudgeCandidate(BaseModel):
    """One candidate output to be judged.

    ``model_name`` is carried alongside the output so results can be mapped
    back to their source model after judging, but it is never included in the
    anonymized judge prompt — see ``anonymize_candidates``.
    """

    candidate_id: str
    model_name: str
    output: str


class JudgeVerdict(BaseModel):
    """One label's verdict, as returned by the judge model."""

    label: str
    passed: bool
    score: float | None = None
    reason: str | None = None


class JudgeOutput(BaseModel):
    """Structured output the judge agent must return."""

    verdicts: list[JudgeVerdict]


# A judge call takes the fully-rendered rubric prompt and returns the judge's
# structured verdicts. Tests inject a stub here instead of calling the model.
JudgeCallable = Callable[[str], JudgeOutput]


def anonymize_candidates(
    candidates: list[JudgeCandidate], rng: random.Random
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Strip model identity and randomize presentation order.

    Returns ``(anonymized, label_to_candidate_id)`` where ``anonymized`` is
    the list of ``{"label": ..., "output": ...}`` dicts in randomized order
    (safe to render into the judge prompt — no ``candidate_id`` or
    ``model_name`` present), and ``label_to_candidate_id`` maps each anonymous
    label back to the originating candidate's ``candidate_id`` for
    de-randomizing the judge's response afterward.

    Exposed as a standalone function (rather than inlined into
    ``judge_candidates``) so tests can reproduce the exact shuffle for a given
    ``rng`` and assert both the randomization and the mapping independently.
    """
    order = list(range(len(candidates)))
    rng.shuffle(order)

    anonymized: list[dict[str, Any]] = []
    label_to_candidate_id: dict[str, str] = {}
    for position, original_index in enumerate(order):
        candidate = candidates[original_index]
        label = f"candidate_{position + 1}"
        anonymized.append({"label": label, "output": candidate.output})
        label_to_candidate_id[label] = candidate.candidate_id

    return anonymized, label_to_candidate_id


def _default_judge_call(model_name: str = DEFAULT_JUDGE_MODEL) -> JudgeCallable:
    """Build the default judge callable: a pydantic_ai Agent over Anthropic.

    Mirrors the model-instantiation pattern in ``core.nodes.agent.AgentNode``
    (the existing agent/LLM seam), but as a standalone callable — this module
    is an offline library, not a workflow node, so it does not subclass
    ``AgentNode`` or require a ``TaskContext``.
    """
    agent = Agent(
        output_type=JudgeOutput,
        model=AnthropicModel(model_name=model_name, provider=AnthropicProvider()),
    )

    def _call(rendered_prompt: str) -> JudgeOutput:
        result = agent.run_sync(user_prompt=rendered_prompt)
        return result.output

    return _call


def judge_candidates(
    rubric_criteria: list[str],
    candidates: list[JudgeCandidate],
    judge_call: JudgeCallable | None = None,
    rng: random.Random | None = None,
    seed: int | None = None,
) -> dict[str, ScoreResult]:
    """Blind, randomized LLM-as-judge scoring of a set of candidate outputs.

    Args:
        rubric_criteria: rubric criteria rendered into the judge prompt.
        candidates: candidate outputs to score, each carrying its own
            ``model_name`` (stripped from the prompt, restored on the way out).
        judge_call: the model-calling callable; defaults to a fresh
            ``pydantic_ai`` Anthropic agent (frontier judge model). Tests
            inject a stub here to avoid network calls.
        rng: an injectable ``random.Random`` for deterministic shuffling.
        seed: used to build an ``rng`` when one isn't passed directly.

    Returns:
        A mapping of ``candidate_id -> ScoreResult``, restored to the
        original (non-anonymized, non-randomized) candidate identities.
    """
    if not candidates:
        return {}

    rng = rng if rng is not None else random.Random(seed)
    anonymized, label_to_candidate_id = anonymize_candidates(candidates, rng)

    rendered_prompt = PromptManager.get_prompt(
        "eval_judge",
        rubric_criteria=rubric_criteria,
        candidates=anonymized,
    )

    call = judge_call if judge_call is not None else _default_judge_call()
    judge_output = call(rendered_prompt)

    results: dict[str, ScoreResult] = {}
    for verdict in judge_output.verdicts:
        candidate_id = label_to_candidate_id.get(verdict.label)
        if candidate_id is None:
            # Judge referenced a label we never emitted — ignore rather than
            # raise, so one malformed verdict doesn't drop every other score.
            continue
        results[candidate_id] = ScoreResult(
            passed=verdict.passed,
            score=verdict.score,
            detail={"reason": verdict.reason} if verdict.reason else None,
        )

    return results
