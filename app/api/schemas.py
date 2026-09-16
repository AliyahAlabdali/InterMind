"""Request and response models for the HTTP layer (kept separate from domain models)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.interview import InterviewState, InterviewStatus
from app.domain.job import JobSpec
from app.domain.report import Recommendation
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
    candidate_name: str = Field(
        default="Candidate",
        min_length=1,
        description="The invited candidate's name, set by the recruiter.",
    )
    candidate_email: str = Field(
        default="",
        description="The invited candidate's email, set by the recruiter.",
    )


class SubmitAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, description="The candidate's answer to the current question.")

    @field_validator("answer")
    @classmethod
    def _reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value


class CandidateAnswerTurn(BaseModel):
    """One completed question/answer turn, safe to show back to the candidate.

    Deliberately excludes the turn's evaluation (score/decision/strengths/weaknesses/evidence)
    - see ``InterviewResponse.history`` - so the candidate can review what they already answered
    without ever seeing internal scoring.
    """

    question_id: str
    question: str
    answer: str


class InterviewResponse(BaseModel):
    """Candidate-safe interview state - returned to both the recruiter (who generated the
    link) and the candidate themselves, so it must never carry recruiter-only evaluation
    information (score, decision, strengths, weaknesses, evidence). See the recruiter/candidate
    API-boundary review: that information is only ever returned by recruiter-scoped endpoints
    (``GET /jobs/{job_id}/interviews``, ``GET /interviews/{id}/report``). The only signal this
    carries about the last evaluation is ``current_question_is_follow_up``, a plain boolean -
    enough for the candidate UI to show a "let's explore that further" transition without
    exposing *why*.
    """

    interview_id: str
    job_id: str
    candidate_name: str
    candidate_email: str
    status: InterviewStatus
    finished: bool
    turn_index: int
    current_question_id: str | None
    current_question_text: str | None
    current_question_is_follow_up: bool
    asked_question_ids: list[str]
    history: list[CandidateAnswerTurn] = Field(default_factory=list)
    candidate_access_token: str | None = Field(
        default=None,
        description=(
            "This interview's own access token (see app.api.auth), present only in the "
            "response to POST /interviews - the candidate's client must send it back as "
            "'Authorization: Bearer <token>' on every later call for this interview. Never "
            "populated on GET/POST .../answers responses: by the time those succeed, the "
            "caller already has it."
        ),
    )

    @classmethod
    def from_state(
        cls,
        interview_id: str,
        state: InterviewState,
        candidate_name: str,
        candidate_email: str,
        candidate_access_token: str | None = None,
    ) -> InterviewResponse:
        # True only when the *current* question is itself the follow-up - i.e. the last
        # evaluated turn was for this same question_id and asked for more. A weak-but-capped
        # answer that still forced an advance (see interview_graph.py's one-follow-up cap)
        # leaves the last turn's decision as "follow_up" even though the interview has already
        # moved to a genuinely new question - checking question_id equality avoids misreporting
        # that new question as a follow-up of the old one.
        is_follow_up = False
        if state.history and state.current_question_id:
            last_turn = state.history[-1]
            if last_turn.get("question_id") == state.current_question_id:
                evaluation_data = last_turn.get("evaluation")
                if evaluation_data:
                    is_follow_up = evaluation_data.get("decision") == "follow_up"

        history = [
            CandidateAnswerTurn(
                question_id=turn["question_id"],
                question=turn["question"],
                answer=turn["answer"],
            )
            for turn in state.history
        ]

        return cls(
            interview_id=interview_id,
            job_id=state.job_id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            status=state.status,
            finished=state.status == InterviewStatus.COMPLETED,
            turn_index=state.turn_index,
            current_question_id=state.current_question_id,
            current_question_text=state.current_question_text,
            current_question_is_follow_up=is_follow_up,
            asked_question_ids=state.asked_question_ids,
            history=history,
            candidate_access_token=candidate_access_token,
        )


class CandidateSessionSummary(BaseModel):
    """Recruiter-only view of one candidate's interview session - never returned to a
    candidate. Backs the recruiter dashboard's candidate table (see the recruiter-workflow
    architecture review): ``overall_score``/``recommendation`` are populated once the session
    is completed (generating/caching the report on first request, same idempotent pattern as
    ``GET /interviews/{id}/report``), and stay ``None`` otherwise - never guessed.
    """

    interview_id: str
    candidate_name: str
    candidate_email: str
    status: InterviewStatus
    overall_score: float | None = None
    recommendation: Recommendation | None = None
