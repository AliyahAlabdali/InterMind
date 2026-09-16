"""Dependency wiring for the API layer."""

from __future__ import annotations

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph

from app.agents.interview_graph import build_interview_graph
from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.llm.openai_client import OpenAIStructuredClient
from app.llm.ports import LLMClient
from app.observability.trace import TraceRecorder
from app.repositories.ports import (
    CandidateRepository,
    InterviewPlanRepository,
    InterviewReportRepository,
    InterviewSessionRepository,
    JobRepository,
)
from app.services.answer_evaluation import AnswerEvaluationService
from app.services.interview_planner import InterviewPlannerService
from app.services.interview_session import InterviewLockRegistry, InterviewSessionService
from app.services.jd_analysis import JDAnalysisService
from app.services.question_generation import QuestionGenerationService
from app.services.report_generation import ReportGenerationService
from app.services.report_narrative import ReportNarrativeService


def get_job_repository(request: Request) -> JobRepository:
    return request.app.state.job_repository


def get_interview_plan_repository(request: Request) -> InterviewPlanRepository:
    return request.app.state.interview_plan_repository


def get_interview_session_repository(request: Request) -> InterviewSessionRepository:
    return request.app.state.interview_session_repository


def get_candidate_repository(request: Request) -> CandidateRepository:
    return request.app.state.candidate_repository


def get_interview_report_repository(request: Request) -> InterviewReportRepository:
    return request.app.state.interview_report_repository


def get_interview_lock_registry(request: Request) -> InterviewLockRegistry:
    """Return the process-lifetime lock registry cached on app state.

    Must stay a single shared instance across requests (see
    :class:`app.services.interview_session.InterviewLockRegistry`) - constructing a fresh one
    per request would give each concurrent request its own empty registry and defeat locking
    entirely.
    """
    registry = getattr(request.app.state, "interview_lock_registry", None)
    if registry is None:
        registry = InterviewLockRegistry()
        request.app.state.interview_lock_registry = registry
    return registry


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


def get_answer_evaluation_service(
    llm: LLMClient = Depends(get_llm_client),
) -> AnswerEvaluationService:
    return AnswerEvaluationService(llm=llm)


def get_interview_graph(
    request: Request,
    evaluator: AnswerEvaluationService = Depends(get_answer_evaluation_service),
) -> CompiledStateGraph:
    """Lazily build the interview graph once per process and cache it on app state.

    The graph's checkpointer is what makes ``thread_id``-based state persist across requests,
    so it must stay a single instance for the app's lifetime - see
    :func:`app.agents.interview_graph.build_interview_graph`.
    """
    graph = getattr(request.app.state, "interview_graph", None)
    if graph is None:
        graph = build_interview_graph(evaluator)
        request.app.state.interview_graph = graph
    return graph


def get_interview_session_service(
    graph: CompiledStateGraph = Depends(get_interview_graph),
    plan_repo: InterviewPlanRepository = Depends(get_interview_plan_repository),
    session_repo: InterviewSessionRepository = Depends(get_interview_session_repository),
    candidate_repo: CandidateRepository = Depends(get_candidate_repository),
    locks: InterviewLockRegistry = Depends(get_interview_lock_registry),
) -> InterviewSessionService:
    return InterviewSessionService(
        graph=graph,
        plan_repo=plan_repo,
        session_repo=session_repo,
        candidate_repo=candidate_repo,
        locks=locks,
    )


def get_report_narrative_service(
    llm: LLMClient = Depends(get_llm_client),
) -> ReportNarrativeService:
    return ReportNarrativeService(llm=llm)


def get_report_generation_service(
    narrative: ReportNarrativeService = Depends(get_report_narrative_service),
) -> ReportGenerationService:
    return ReportGenerationService(narrative=narrative)
