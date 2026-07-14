"""Tests for the blind, randomized LLM-as-judge scorer."""

import random
import re

from evals.judge import (
    JudgeCandidate,
    JudgeOutput,
    JudgeVerdict,
    anonymize_candidates,
    judge_candidates,
)
from evals.scorers import ScoreResult


def _candidates() -> list[JudgeCandidate]:
    return [
        JudgeCandidate(candidate_id="c1", model_name="claude-opus-4-8", output="alpha output"),
        JudgeCandidate(candidate_id="c2", model_name="claude-sonnet-5", output="beta output"),
        JudgeCandidate(candidate_id="c3", model_name="gpt-4.1", output="gamma output"),
        JudgeCandidate(candidate_id="c4", model_name="claude-haiku-4-5", output="delta output"),
    ]


def _judge_call_from_prompt(prompt: str) -> JudgeOutput:
    """Stub judge call: parse the labels actually rendered into the prompt
    and return a deterministic verdict for each, in that same order."""
    labels = re.findall(r"### (candidate_\d+)", prompt)
    return JudgeOutput(
        verdicts=[
            JudgeVerdict(label=label, passed=True, score=1.0, reason="looks good")
            for label in labels
        ]
    )


class TestAnonymizeCandidates:
    def test_strips_model_identity(self):
        anonymized, _ = anonymize_candidates(_candidates(), random.Random(1))

        for entry in anonymized:
            assert set(entry.keys()) == {"label", "output"}
            for value in entry.values():
                assert "claude" not in str(value)
                assert "gpt" not in str(value)

    def test_order_differs_across_seeds(self):
        anonymized_a, _ = anonymize_candidates(_candidates(), random.Random(1))
        anonymized_b, _ = anonymize_candidates(_candidates(), random.Random(2))

        outputs_a = [entry["output"] for entry in anonymized_a]
        outputs_b = [entry["output"] for entry in anonymized_b]
        assert outputs_a != outputs_b

    def test_mapping_round_trips_to_candidate_id(self):
        candidates = _candidates()
        anonymized, label_to_candidate_id = anonymize_candidates(candidates, random.Random(3))

        # Every label maps back to a real candidate_id, and the mapped
        # candidate's output matches what was actually anonymized under that label.
        by_output = {c.output: c.candidate_id for c in candidates}
        for entry in anonymized:
            expected_candidate_id = by_output[entry["output"]]
            assert label_to_candidate_id[entry["label"]] == expected_candidate_id


class TestJudgeCandidates:
    def test_prompt_contains_no_model_identity(self):
        captured_prompts = []

        def capturing_judge_call(prompt: str) -> JudgeOutput:
            captured_prompts.append(prompt)
            return _judge_call_from_prompt(prompt)

        judge_candidates(
            rubric_criteria=["Response is factually accurate"],
            candidates=_candidates(),
            judge_call=capturing_judge_call,
            seed=42,
        )

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "claude-opus-4-8" not in prompt
        assert "claude-sonnet-5" not in prompt
        assert "claude-haiku-4-5" not in prompt
        assert "gpt-4.1" not in prompt

    def test_rubric_criteria_rendered_into_prompt(self):
        captured_prompts = []

        def capturing_judge_call(prompt: str) -> JudgeOutput:
            captured_prompts.append(prompt)
            return _judge_call_from_prompt(prompt)

        judge_candidates(
            rubric_criteria=["Must cite a source", "Must be under 100 words"],
            candidates=_candidates(),
            judge_call=capturing_judge_call,
            seed=7,
        )

        prompt = captured_prompts[0]
        assert "Must cite a source" in prompt
        assert "Must be under 100 words" in prompt

    def test_scores_map_back_to_correct_candidates(self):
        candidates = _candidates()
        results = judge_candidates(
            rubric_criteria=["Response is helpful"],
            candidates=candidates,
            judge_call=_judge_call_from_prompt,
            seed=11,
        )

        assert set(results.keys()) == {c.candidate_id for c in candidates}
        for score_result in results.values():
            assert isinstance(score_result, ScoreResult)
            assert score_result.passed is True
            assert score_result.score == 1.0

    def test_order_differs_across_seeds_end_to_end(self):
        candidates = _candidates()
        prompts = []

        def capturing_judge_call(prompt: str) -> JudgeOutput:
            prompts.append(prompt)
            return _judge_call_from_prompt(prompt)

        judge_candidates(
            rubric_criteria=["x"], candidates=candidates, judge_call=capturing_judge_call, seed=1
        )
        judge_candidates(
            rubric_criteria=["x"], candidates=candidates, judge_call=capturing_judge_call, seed=2
        )

        assert prompts[0] != prompts[1]

    def test_no_candidates_returns_empty(self):
        results = judge_candidates(
            rubric_criteria=["x"], candidates=[], judge_call=_judge_call_from_prompt, seed=1
        )
        assert results == {}

    def test_ignores_verdict_for_unknown_label(self):
        def stray_label_judge_call(prompt: str) -> JudgeOutput:
            return JudgeOutput(
                verdicts=[JudgeVerdict(label="candidate_99", passed=True, score=1.0)]
            )

        results = judge_candidates(
            rubric_criteria=["x"],
            candidates=_candidates(),
            judge_call=stray_label_judge_call,
            seed=5,
        )
        assert results == {}
