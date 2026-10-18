import pytest
from pydantic import ValidationError

from conftest import T0


def test_evaluation_records_judge_version(make_evaluation):
    ev = make_evaluation(evaluator_type="LLM_JUDGE", evaluator_id="judge-model", evaluator_version="2026-10",
                         judge_prompt_version="rubric-v3", judge_model_family="family-x")
    assert ev.judge_prompt_version == "rubric-v3" and ev.judge_model_family == "family-x"
    with pytest.raises(ValidationError, match="judge_prompt_version"):
        make_evaluation(evaluator_type="LLM_JUDGE", judge_model_family="family-x")
    with pytest.raises(ValidationError, match="judge_prompt_version"):
        make_evaluation(evaluator_type="LLM_JUDGE", judge_prompt_version="rubric-v3")


def test_judge_fields_only_for_judges(make_evaluation):
    with pytest.raises(ValidationError, match="only valid for LLM_JUDGE"):
        make_evaluation(judge_prompt_version="rubric-v3")


def test_human_evaluation_records_blindness(make_evaluation):
    with pytest.raises(ValidationError, match="blind"):
        make_evaluation(evaluator_type="HUMAN", evaluator_id="olga")
    assert make_evaluation(evaluator_type="HUMAN", evaluator_id="olga", blind=True).blind is True
    with pytest.raises(ValidationError, match="only valid for HUMAN"):
        make_evaluation(blind=True)


def test_review_keeps_its_reason(make_evaluation):
    with pytest.raises(ValidationError, match="requires review_reason"):
        make_evaluation(result="REVIEW")
    ev = make_evaluation(result="REVIEW", review_reason="judge and human disagree on explanation quality")
    assert ev.review_reason
    with pytest.raises(ValidationError, match="only valid for REVIEW"):
        make_evaluation(result="PASS", review_reason="n/a")
