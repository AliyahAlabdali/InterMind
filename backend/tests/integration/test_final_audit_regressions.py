"""Offline regression proofs for the final corrective pass."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_onet_kb, get_speech_token_service
from app.api.routes.interviews import _get_or_generate_report
from app.core.config import get_settings
from app.core.exceptions import StaleInterviewTurn
from app.domain.interview_plan import QuestionCategory
from app.domain.report import QuestionEvaluationSummary
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.report_scoring import (
    build_competency_assessments,
    compute_overall_score,
    derive_recommendation,
)
from tests.conftest import FIXTURES, signup
from tests.integration.test_report_survives_restart_regression import (
    _completed_interview,
    _forget_graph_state,
)
from tests.integration.test_speech_token_api import _azure_settings, _service_returning
from tests.unit.test_interview_session_service import DETAILED_ANSWER, _make_plan, _make_service


@pytest.fixture(autouse=True)
def fixture_kb(app):
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(
        path=FIXTURES / "onet_kb_fixture.jsonl"
    )


async def test_duplicate_answer_never_consumes_the_next_question():
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    iid, _ = await service.start("job-1")
    results = await asyncio.gather(
        service.submit_answer(iid, DETAILED_ANSWER, (await service.get_state(iid)).current_turn_id),
        service.submit_answer(iid, DETAILED_ANSWER, (await service.get_state(iid)).current_turn_id),
        return_exceptions=True,
    )
    assert sum(isinstance(r, StaleInterviewTurn) for r in results) == 1
    state = await service.get_state(iid)
    assert len(state.history) == 1


async def test_completed_before_first_report_survives_restart(app, client):
    _, iid = await _completed_interview(client)
    _forget_graph_state(app)
    response = await client.get(f"/interviews/{iid}/report")
    assert response.status_code == 200
    assert response.json()["question_evaluations"]


def test_same_display_name_does_not_merge_distinct_targets():
    items = [
        QuestionEvaluationSummary(
            question_id=identity, target_id=identity, question="Q?", target=name,
            category=category, candidate_answer="A", score=score,
        )
        for identity, name, category, score in [
            ("competency-ml", "Machine Learning", QuestionCategory.COMPETENCY, .9),
            ("technology-ml", "Machine Learning", QuestionCategory.TECHNOLOGY, .1),
            ("technology-python", "Python", QuestionCategory.TECHNOLOGY, .1),
        ]
    ]
    assessments = build_competency_assessments(items)
    assert len(assessments) == 3
    assert compute_overall_score(assessments) == .5
    assert derive_recommendation(.5).value == "consider"
    # Different stable IDs within one category also remain separate.
    other = items[0].model_copy(update={"target_id": "different-competency", "score": .1})
    assert len(build_competency_assessments([items[0], other])) == 2


async def test_completed_interview_cannot_regain_speech_after_restart(app, client):
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()
    _, iid = await _completed_interview(client)
    assert (await client.get(f"/interviews/{iid}/speech-token")).status_code == 409
    _forget_graph_state(app)
    assert (await client.get(f"/interviews/{iid}/speech-token")).status_code == 409


async def test_concurrent_reports_generate_once():
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    iid, _ = await service.start("job-1")
    for _ in range(3):
        await service.submit_answer(
            iid,
            DETAILED_ANSWER,
            (await service.get_state(iid)).current_turn_id,
        )
    from app.llm.fake_client import FakeLLMClient
    from app.repositories.in_memory import InMemoryInterviewReportRepository
    from app.services.report_generation import ReportGenerationService
    from app.services.report_narrative import ReportNarrativeService
    reports = InMemoryInterviewReportRepository()
    generator = ReportGenerationService(narrative=ReportNarrativeService(llm=FakeLLMClient()))
    original = generator.generate
    entered = 0

    async def slow_generate(**kwargs):
        nonlocal entered
        entered += 1
        await asyncio.sleep(.01)
        return await original(**kwargs)

    generator.generate = slow_generate
    kwargs = dict(interview_id=iid, session_service=service, plan_repo=service.plan_repo,
                  report_repo=reports, report_service=generator)
    await asyncio.gather(_get_or_generate_report(**kwargs), _get_or_generate_report(**kwargs))
    assert entered == 1


async def test_candidate_token_works_with_unrelated_recruiter_cookie(app, client):
    job_id = (await client.post("/jobs", json={
        "job_description": "Software Engineer with Python and Git experience."
    })).json()["id"]
    await client.post(f"/jobs/{job_id}/interview-plan")
    state = (await client.post("/interviews", json={"job_id": job_id})).json()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        await signup(other, "unrelated@intermind.test")
        headers = {"Authorization": f"Bearer {state['candidate_access_token']}"}
        assert (await other.get(f"/interviews/{state['interview_id']}",
                                headers=headers)).status_code == 200
        assert (await other.get(f"/jobs/{job_id}/interview-plan",
                                headers=headers)).status_code == 200
        assert (await other.get(f"/interviews/{state['interview_id']}/report",
                                headers=headers)).status_code == 404


async def test_failed_initial_question_does_not_persist_an_invitation():
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    service.graph.ainvoke = AsyncMock(side_effect=RuntimeError("offline provider failure"))
    with pytest.raises(RuntimeError):
        await service.start("job-1")
    assert len(await service.session_repo.list_by_job("job-1")) == 0
    assert len(service.candidate_repo._candidates) == 0


async def test_unrecoverable_state_fails_closed_before_speech_provider(app, client):
    from tests.integration.test_speech_token_api import _start_interview
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    provider = _service_returning()
    provider.issue = AsyncMock()
    app.dependency_overrides[get_speech_token_service] = lambda: provider
    iid, _ = await _start_interview(client)
    async with app.state.interview_session_repository.locked(iid) as session:
        session.runtime_snapshot = None
    response = await client.get(f"/interviews/{iid}/speech-token")
    assert response.status_code == 500
    provider.issue.assert_not_called()


async def test_active_speech_survives_restart_and_repeated_issuance_is_limited(app, client):
    from tests.integration.test_speech_token_api import _start_interview
    app.dependency_overrides[get_settings] = lambda: _azure_settings()
    app.dependency_overrides[get_speech_token_service] = lambda: _service_returning()
    iid, _ = await _start_interview(client)
    _forget_graph_state(app)
    for _ in range(60):
        response = await client.get(f"/interviews/{iid}/speech-token")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    assert (await client.get(f"/interviews/{iid}/speech-token")).status_code == 429


async def test_follow_up_rejects_replayed_root_turn():
    from tests.unit.test_interview_session_service import SHORT_ANSWER
    service = _make_service()
    await service.plan_repo.add(_make_plan())
    iid, initial = await service.start("job-1")
    follow_up = await service.submit_answer(iid, SHORT_ANSWER, initial.current_turn_id)
    assert follow_up.current_question_id == initial.current_question_id
    assert follow_up.current_turn_id != initial.current_turn_id
    with pytest.raises(StaleInterviewTurn):
        await service.submit_answer(iid, DETAILED_ANSWER, initial.current_turn_id)
    advanced = await service.submit_answer(iid, DETAILED_ANSWER, follow_up.current_turn_id)
    assert advanced.history[1]["question"] == follow_up.current_question_text
