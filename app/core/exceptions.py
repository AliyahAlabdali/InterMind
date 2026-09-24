"""Domain-level exceptions. These carry no HTTP knowledge; the API layer maps them."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain errors."""


class JobNotFound(DomainError):
    """Requested job id does not exist in the repository."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job not found: {job_id}")
        self.job_id = job_id


class ConfigurationError(DomainError):
    """The service is not configured correctly to serve the request (operator error)."""


class LLMError(DomainError):
    """The LLM request failed or produced unusable output."""


class LLMOutputInvalid(LLMError):
    """The LLM response could not be parsed into the expected schema."""


class QuestionGenerationError(LLMError):
    """The LLM/fake provider's generated questions don't match what was requested.

    Covers missing, duplicate, unexpected/invalid, mis-categorised, or out-of-order targets -
    a schema-valid response that is still unusable, as opposed to :class:`LLMOutputInvalid`
    (a response that failed schema validation outright).
    """


class OccupationNotFound(DomainError):
    """Requested O*NET-SOC code does not exist in the loaded knowledge base."""

    def __init__(self, onet_soc_code: str) -> None:
        super().__init__(f"Occupation not found: {onet_soc_code}")
        self.onet_soc_code = onet_soc_code


class NoOccupationMatch(DomainError):
    """The knowledge base produced no occupation candidates for a JobSpec."""

    def __init__(self, role_title: str) -> None:
        super().__init__(f"No O*NET occupation match found for role: {role_title}")


class CandidateNotFound(DomainError):
    """Requested candidate id does not exist."""

    def __init__(self, candidate_id: str) -> None:
        super().__init__(f"Candidate not found: {candidate_id}")
        self.candidate_id = candidate_id


class InterviewPlanNotFound(DomainError):
    """No interview plan has been created yet for this job id."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Interview plan not found: {job_id}")
        self.job_id = job_id


class InterviewNotFound(DomainError):
    """Requested interview id does not exist."""

    def __init__(self, interview_id: str) -> None:
        super().__init__(f"Interview not found: {interview_id}")
        self.interview_id = interview_id


class InterviewAlreadyCompleted(DomainError):
    """The interview has already finished; it cannot accept another answer."""

    def __init__(self, interview_id: str) -> None:
        super().__init__(f"Interview already completed: {interview_id}")
        self.interview_id = interview_id


class InterviewNotCompleted(DomainError):
    """The interview has not finished yet; no report can be generated for it."""

    def __init__(self, interview_id: str) -> None:
        super().__init__(f"Interview not completed: {interview_id}")
        self.interview_id = interview_id


class InterviewReportNotFound(DomainError):
    """No report has been generated yet for this interview id.

    Internal to the report repository/route (see ``GET /interviews/{id}/report``): the route
    always catches this to decide whether to generate and cache a new report, so it should
    never reach a client.
    """

    def __init__(self, interview_id: str) -> None:
        super().__init__(f"Interview report not found: {interview_id}")
        self.interview_id = interview_id


class InvalidSignup(DomainError):
    """Signup input the server rejected (malformed email, password too short).

    Unlike a sign-in failure, this message *is* shown to the user: they need to know what to
    change, and none of it reveals anything about existing accounts.
    """


class RecruiterEmailTaken(DomainError):
    """Signup for an email that already has an account.

    Raised from the database's unique constraint rather than a prior lookup, so two concurrent
    signups for the same address cannot both succeed.
    """


class AccessDenied(DomainError):
    """The caller's access token is missing, invalid, or does not authorize this request.

    Raised by ``app.api.auth`` (the Milestone 4 recruiter/candidate access boundary - see its
    module docstring). Deliberately carries no detail about *why* (missing header vs. wrong
    token vs. wrong interview) - the HTTP mapping returns one generic message, the same
    "sanitized error" principle already applied to ``LLMError``/``ConfigurationError``.
    """


class SpeechServiceUnavailable(DomainError):
    """The speech service could not issue an authorization token.

    Covers an upstream rejection (bad key, wrong region, throttling) and a network failure
    reaching it. Like ``LLMError``, the detail is logged server-side and never returned to the
    caller - an upstream error message could carry key or endpoint detail, and the candidate UI
    only needs "voice is unavailable, keep typing".
    """


class InterviewStateUnavailable(DomainError):
    """A valid interview session record exists, but its checkpointed graph state does not.

    Covers both a missing checkpoint (no state was ever recorded for that thread id) and an
    incomplete/invalid one (present but missing required fields or holding an unrecognised
    value) - an internal invariant violation (the session repository and the graph
    checkpointer have gone out of sync), not something the caller did wrong.
    """

    def __init__(self, interview_id: str, reason: str) -> None:
        super().__init__(f"Interview state unavailable for {interview_id}: {reason}")
        self.interview_id = interview_id
        self.reason = reason
