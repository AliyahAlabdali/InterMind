"""Request and response models for the HTTP layer (kept separate from domain models)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.evaluation import AnswerEvaluation
from app.domain.interview import InterviewState, InterviewStatus
from app.domain.job import JobSpec
from app.repositories.ports import StoredJob


class AnalyzeJobRequest(BaseModel):
    job_description: str = Field(min_length=1, description="Raw job description text.")


class JobResponse(BaseModel):
    id: str
    job_description: str
    job_spec: JobSpec
    created_at: datetime

    @classmethod
    def from_stored(cls, stored: StoredJob) -> JobResponse:
        return cls.model_validate(stored.model_dump())


class StartInterviewRequest(BaseModel):
    job_id: str = Field(min_length=1, description="Id of a job with an existing interview plan.")


class SubmitAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, description="The candidate's answer to the current question.")

    @field_validator("answer")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value


class InterviewResponse(BaseModel):
    interview_id: str
    job_id: str
    status: InterviewStatus
    finished: bool
    turn_index: int
    current_question_id: str | None
    current_question_text: str | None
    asked_question_ids: list[str]
    last_evaluation: AnswerEvaluation | None = None

    @classmethod
    def from_state(cls, interview_id: str, state: InterviewState) -> InterviewResponse:
        last_evaluation = None
        if state.history:
            evaluation_data = state.history[-1].get("evaluation")
            if evaluation_data:
                last_evaluation = AnswerEvaluation.model_validate(evaluation_data)

        return cls(
            interview_id=interview_id,
            job_id=state.job_id,
            status=state.status,
            finished=state.status == InterviewStatus.COMPLETED,
            turn_index=state.turn_index,
            current_question_id=state.current_question_id,
            current_question_text=state.current_question_text,
            asked_question_ids=state.asked_question_ids,
            last_evaluation=last_evaluation,
        )
