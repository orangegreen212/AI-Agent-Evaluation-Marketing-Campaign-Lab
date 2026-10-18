"""One evaluator's judgement of one criterion for one run."""
from __future__ import annotations

from pydantic import AwareDatetime, model_validator

from .base import Id, NonEmptyStr, VersionedModel
from .enums import EvaluationResult, EvaluatorType


class Evaluation(VersionedModel):
    evaluation_id: Id
    run_id: Id
    criterion_id: Id
    evaluator_type: EvaluatorType
    evaluator_id: NonEmptyStr
    evaluator_version: NonEmptyStr
    judge_prompt_version: NonEmptyStr | None = None
    judge_model_family: NonEmptyStr | None = None  # for the independence check against compared models
    result: EvaluationResult
    reasoning_reference: NonEmptyStr | None = None
    review_reason: NonEmptyStr | None = None  # REVIEW keeps its reason here until Phase 5 adds owner/due
    blind: bool | None = None  # human evaluations only
    evaluated_at: AwareDatetime

    @model_validator(mode="after")
    def _rules(self) -> "Evaluation":
        if self.evaluator_type == EvaluatorType.LLM_JUDGE:
            if not self.judge_prompt_version or not self.judge_model_family:
                raise ValueError("LLM_JUDGE evaluation requires judge_prompt_version and judge_model_family")
        elif self.judge_prompt_version or self.judge_model_family:
            raise ValueError("judge fields are only valid for LLM_JUDGE evaluations")
        if self.evaluator_type == EvaluatorType.HUMAN:
            if self.blind is None:
                raise ValueError("HUMAN evaluation must record whether it was blind")
        elif self.blind is not None:
            raise ValueError("'blind' is only valid for HUMAN evaluations")
        if self.result == EvaluationResult.REVIEW and not self.review_reason:
            raise ValueError("REVIEW result requires review_reason")
        if self.result != EvaluationResult.REVIEW and self.review_reason:
            raise ValueError("review_reason is only valid for REVIEW results")
        return self
