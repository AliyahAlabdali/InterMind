import pytest

from app.core.exceptions import NoOccupationMatch
from app.domain.interview_plan import EvidenceSource, QuestionCategory
from app.domain.job import Competency, JobSpec, Skill
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.services.interview_planner import InterviewPlannerService, _question_id
from app.services.question_generation import QuestionGenerationService
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"


@pytest.fixture
def planner():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    question_service = QuestionGenerationService(llm=FakeLLMClient())
    return InterviewPlannerService(knowledge_base=kb, question_service=question_service)


@pytest.fixture
def software_job_spec():
    return JobSpec(
        role_title="Backend Software Engineer",
        skills=[Skill(name="Python", required=True), Skill(name="Docker", required=False)],
        competencies=[Competency(name="Critical Thinking")],
        summary="Builds and maintains backend software services using Python.",
    )


async def test_plan_matches_expected_occupation(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    assert plan.job_id == "job-1"
    assert plan.occupation_match.onet_soc_code == "15-1252.00"
    assert plan.occupation_match.title == "Software Developers"
    # the remaining fixture occupation should show up as a lower-ranked alternate
    assert any(m.onet_soc_code == "35-2014.00" for m in plan.alternate_matches)


async def test_competency_merge_marks_overlap_as_both(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    by_name = {c.name: c for c in plan.competencies}

    # "Critical Thinking" is in both the JobSpec and the matched occupation's skill list.
    assert by_name["Critical Thinking"].source == EvidenceSource.BOTH
    assert by_name["Critical Thinking"].onet_importance == 4.0

    # "Programming" only comes from O*NET.
    assert by_name["Programming"].source == EvidenceSource.ONET
    assert by_name["Programming"].onet_importance == 4.8


async def test_technology_merge_marks_overlap_as_both(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    by_name = {t.name: t for t in plan.technologies}

    # "Python" is in both the JobSpec and the matched occupation's technology list.
    assert by_name["Python"].source == EvidenceSource.BOTH
    assert by_name["Python"].hot is True

    # "Docker" only comes from the JobSpec (not in the fixture occupation's tech list).
    assert by_name["Docker"].source == EvidenceSource.JOBSPEC

    # "Git" only comes from O*NET.
    assert by_name["Git"].source == EvidenceSource.ONET


async def test_tasks_come_from_matched_occupation(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    assert len(plan.tasks) == 2
    assert any("Analyze user needs" in t.task for t in plan.tasks)
    # JobSpec has no task-level field, so every selected task's provenance is O*NET only.
    assert all(t.source == EvidenceSource.ONET for t in plan.tasks)


async def test_questions_cover_all_categories_and_are_grounded(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    categories = {q.category for q in plan.questions}
    expected = {QuestionCategory.COMPETENCY, QuestionCategory.TECHNOLOGY, QuestionCategory.TASK}
    assert categories == expected
    for q in plan.questions:
        assert q.id
        assert q.text
        assert q.grounding

    competency_q = next(q for q in plan.questions if q.category == QuestionCategory.COMPETENCY)
    assert "O*NET" in competency_q.grounding or "Job description" in competency_q.grounding


async def test_questions_have_no_duplicate_text(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    texts = [q.text for q in plan.questions]
    assert len(texts) == len(set(t.lower() for t in texts))


async def test_caps_are_respected(software_job_spec):
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    question_service = QuestionGenerationService(llm=FakeLLMClient())
    planner = InterviewPlannerService(
        knowledge_base=kb,
        question_service=question_service,
        max_competencies=2,
        max_technologies=1,
        max_tasks=1,
        competency_questions=2,
        technology_questions=1,
        task_questions=1,
    )
    plan = await planner.plan("job-1", software_job_spec)
    assert len(plan.competencies) <= 2
    assert len(plan.technologies) <= 1
    assert len(plan.tasks) <= 1
    assert len(plan.questions) <= 4


async def test_plan_with_minimal_jobspec_falls_back_to_onet_signal(planner):
    job_spec = JobSpec(role_title="Software Developer")
    plan = await planner.plan("job-2", job_spec)
    assert plan.occupation_match.onet_soc_code == "15-1252.00"
    assert all(c.source == EvidenceSource.ONET for c in plan.competencies)
    assert all(t.source == EvidenceSource.ONET for t in plan.technologies)
    assert len(plan.questions) > 0


async def test_no_occupation_match_raises_when_kb_cannot_rank(
    planner, software_job_spec, monkeypatch
):
    monkeypatch.setattr(planner.knowledge_base, "match_jobspec", lambda job_spec, top_k=5: [])
    with pytest.raises(NoOccupationMatch):
        await planner.plan("job-1", software_job_spec)


async def test_rebuilding_the_same_plan_produces_stable_question_ids_and_order(
    planner, software_job_spec
):
    first = await planner.plan("job-1", software_job_spec)
    second = await planner.plan("job-1", software_job_spec)

    first_ids = [q.id for q in first.questions]
    second_ids = [q.id for q in second.questions]
    assert first_ids == second_ids  # same order, not just the same set
    assert len(first_ids) == len(set(first_ids))  # every id in a plan is unique


async def test_different_job_ids_get_different_question_ids_for_the_same_target(
    planner, software_job_spec
):
    plan_a = await planner.plan("job-a", software_job_spec)
    plan_b = await planner.plan("job-b", software_job_spec)
    ids_a = {q.id for q in plan_a.questions}
    ids_b = {q.id for q in plan_b.questions}
    assert ids_a.isdisjoint(ids_b)


async def test_question_id_does_not_depend_on_phrased_text(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    competency_q = next(q for q in plan.questions if q.category == QuestionCategory.COMPETENCY)

    # Same job id, category, and target -> same id, even with completely different text.
    assert competency_q.id == _question_id("job-1", competency_q.category, competency_q.target)
