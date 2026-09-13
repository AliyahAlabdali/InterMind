"""Dependency wiring for the API layer."""

from __future__ import annotations

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.llm.openai_client import OpenAIStructuredClient
from app.llm.ports import LLMClient
from app.observability.trace import TraceRecorder
from app.repositories.ports import InterviewPlanRepository, JobRepository
from app.services.interview_planner import InterviewPlannerService
from app.services.jd_analysis import JDAnalysisService
from app.services.question_generation import QuestionGenerationService


def get_job_repository(request: Request) -> JobRepository:
    return request.app.state.job_repository


def get_interview_plan_repository(request: Request) -> InterviewPlanRepository:
    return request.app.state.interview_plan_repository


def get_trace_recorder(request: Request) -> TraceRecorder:
    return request.app.state.trace_recorder


def get_onet_kb(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> OnetKnowledgeBase:
    """Lazily build the KB once per process and cache it on app state.

    Lazy so endpoints that don't need it (``/health``, ``/jobs``) never pay to load or
    vectorize it, and so a missing ``data/processed/onet/onet_kb.jsonl`` (e.g. the Milestone 2
    notebook hasn't been run yet) only fails the endpoints that actually need the KB.
    """
    kb = getattr(request.app.state, "onet_kb", None)
    if kb is None:
        kb = OnetKnowledgeBase(path=settings.onet_kb_path)
        request.app.state.onet_kb = kb
    return kb


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


def get_question_generation_service(
    llm: LLMClient = Depends(get_llm_client),
) -> QuestionGenerationService:
    return QuestionGenerationService(llm=llm)


def get_interview_planner_service(
    knowledge_base: OnetKnowledgeBase = Depends(get_onet_kb),
    question_service: QuestionGenerationService = Depends(get_question_generation_service),
) -> InterviewPlannerService:
    return InterviewPlannerService(knowledge_base=knowledge_base, question_service=question_service)
