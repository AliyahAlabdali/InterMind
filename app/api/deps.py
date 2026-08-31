"""Dependency wiring for the API layer."""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.llm.fake_client import FakeLLMClient
from app.llm.openai_client import OpenAIStructuredClient
from app.llm.ports import LLMClient
from app.observability.trace import TraceRecorder
from app.repositories.ports import JobRepository
from app.services.jd_analysis import JDAnalysisService


def get_job_repository(request: Request) -> JobRepository:
    return request.app.state.job_repository


def get_trace_recorder(request: Request) -> TraceRecorder:
    return request.app.state.trace_recorder


def get_llm_client(
    settings: Settings = Depends(get_settings),
    trace: TraceRecorder = Depends(get_trace_recorder),
) -> LLMClient:
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ConfigurationError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set"
            )
        return OpenAIStructuredClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            trace=trace,
        )
    return FakeLLMClient()


def get_jd_analysis_service(
    llm: LLMClient = Depends(get_llm_client),
) -> JDAnalysisService:
    return JDAnalysisService(llm=llm)
