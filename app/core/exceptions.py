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
