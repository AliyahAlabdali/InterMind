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


class InterviewPlanNotFound(DomainError):
    """No interview plan has been created yet for this job id."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Interview plan not found: {job_id}")
        self.job_id = job_id
