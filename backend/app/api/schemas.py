"""Request and response models for the HTTP layer (kept separate from domain models)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.interview import InterviewState, InterviewStatus
from app.domain.interview_plan import InterviewPlan
from app.domain.job import JobSpec
from app.domain.report import Recommendation
from app.repositories.ports import StoredJob


class AnalyzeJobRequest(BaseModel):
    job_description: str = Field(min_length=1, description="Raw job description text.")


class JobResponse(BaseModel):
    """A job as the recruiter who owns it sees it.

    Note there is no ``recruiter_id``: ownership is a server-side fact, and echoing internal
    account ids into responses only creates something to correlate.
    """

    id: str
    job_description: str
    job_spec: JobSpec
    created_at: datetime

    @classmethod
    def from_stored(cls, stored: StoredJob) -> JobResponse:
        return cls.model_validate(stored.model_dump())


class PublicJobResponse(BaseModel):
    """A job as an unauthenticated candidate sees it.

    ``GET /jobs/{job_id}`` is deliberately public so a candidate's interview screen can name the
    role they are interviewing for. It used to return the whole job, including
    ``job_description`` - the recruiter's full raw job-description text, readable by anyone who
    knew a job id, and not rendered anywhere in the product. With one recruiter that was
    careless; with many it is one tenant's content on an open endpoint.

    So the public shape carries only what the candidate screen actually reads: the role, from
    ``job_spec``. The recruiter's own ``GET /jobs`` is unchanged and still returns everything.
    """

    id: str
    job_spec: JobSpec
    created_at: datetime

    @classmethod
    def from_stored(cls, stored: StoredJob) -> PublicJobResponse:
        return cls.model_validate(stored.model_dump())


class CandidateCoverageTarget(BaseModel):
    """One coverage target, as the candidate taking the interview may see it."""

    id: str
    target: str


class CandidateInterviewPlanResponse(BaseModel):
    """A job's interview plan as the candidate interviewing for it sees it.

    ``GET /jobs/{job_id}/interview-plan`` returns the full
    :class:`~app.domain.interview_plan.InterviewPlan` to the recruiter who owns the job, and
    this instead to a candidate holding that interview's access token. The candidate's own
    screen needs three things and no more: the role name in the header, the number of targets
    for the progress rail, and the target names to bias speech recognition toward the interview's
    own vocabulary (see ``frontend/src/speech/phrases``).

    Everything else the plan carries is the recruiter's assessment strategy - requirement level,
    priority, provenance and the O*NET grounding behind each target - and telling a candidate
    mid-interview how heavily each area is weighted, or which ones are optional, changes what
    they say next. It is withheld here for that reason as much as for tenancy.
    """

    job_id: str
    role_title: str
    coverage_targets: list[CandidateCoverageTarget] = Field(default_factory=list)

    @classmethod
    def from_plan(cls, plan: InterviewPlan) -> CandidateInterviewPlanResponse:
        return cls(
            job_id=plan.job_id,
            role_title=plan.role_title,
            coverage_targets=[
                CandidateCoverageTarget(id=target.id, target=target.target)
                for target in plan.coverage_targets
            ],
        )


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
    current_question_id: str | None = Field(
        description=(
            "The current TARGET's id - stable across a follow-up (never repointed to the "
            "follow-up's own id). See app.domain.interview.InterviewState's docstring for the "
            "full root-target/current-turn/follow-up identity contract this deliberately "
            "preserves; use current_question_text (below), never this field, to render what "
            "is actually being asked right now."
        )
    )
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
        # directly asked turn was for this same question_id and asked for more. A weak-but-capped
        # answer that still forced an advance (see interview_graph.py's one-follow-up cap)
        # leaves that turn's decision as "follow_up" even though the interview has already
        # moved to a genuinely new question - checking question_id equality avoids misreporting
        # that new question as a follow-up of the old one.
        #
        # The search skips cross-target turns rather than simply reading history[-1]. When an
        # answer also establishes some *other* target, the resolver appends a synthesized turn
        # for it (assessment_method="cross_target") after the real one, so the last entry is no
        # longer the turn that was actually evaluated for the current question. Reading it
        # meant a genuine follow-up reported itself as a new question, and the candidate UI
        # skipped the beat that marks one - every time cross-target evidence and a follow-up
        # landed on the same answer.
        is_follow_up = False
        if state.current_question_id:
            last_asked = next(
                (
                    turn
                    for turn in reversed(state.history)
                    if turn.get("assessment_method", "direct") == "direct"
                ),
                None,
            )
            if last_asked and last_asked.get("question_id") == state.current_question_id:
                evaluation_data = last_asked.get("evaluation")
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

    ``candidate_access_token`` is the same stable ``InterviewSession.access_token`` minted once
    at ``POST /interviews`` and never rotated (see ``app.repositories.ports.InterviewSession``) -
    surfacing it here lets a recruiter recover a candidate's invitation link at any time (after
    dismissing the creation dialog, after a page refresh, in a new browser tab) without
    regenerating it or standing up a new endpoint. Safe precisely because this whole model is
    already recruiter-only (see ``require_recruiter_access`` on ``GET /jobs/{job_id}/
    interviews``); it must never be added to ``InterviewResponse``, which both the recruiter and
    the candidate themselves can read.
    """

    interview_id: str
    candidate_name: str
    candidate_email: str
    status: InterviewStatus
    overall_score: float | None = None
    recommendation: Recommendation | None = None
    candidate_access_token: str
