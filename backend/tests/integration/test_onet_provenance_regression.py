"""Regression tests for the "JD is authoritative, O*NET is context" architecture.

Uses the *real*, processed O*NET knowledge base (like ``test_onet_matching_regression.py``)
because the reported bug - a Backend Software Engineer JD top-matching Health Informatics
Specialists and injecting nursing/patient tasks plus Microsoft Excel/Office as technologies -
only reproduces against the full 1016-occupation corpus. Skipped when the real KB artifact
hasn't been generated (git-ignored; built by running
``notebooks/ONET_knowledge_base_pipeline.ipynb``).

Under this architecture, ``InterviewPlan.competencies``/``technologies``/``tasks`` are always
JobSpec-only by construction (see ``app.services.interview_planner``'s module docstring), so
the original bug can no longer reproduce there structurally, regardless of match quality. What
these tests instead verify is: (1) that structural guarantee holds for the exact reported JD,
(2) O*NET context still reaches question generation for a genuinely relevant JD, and (3) that
context is itself relevance-filtered, not a wholesale copy of the occupation record.
"""

from __future__ import annotations

import pytest

from app.domain.interview_plan import EvidenceSource
from app.knowledge.onet_kb import DEFAULT_KB_PATH, OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.services.interview_planner import InterviewPlannerService
from app.services.jd_analysis import JDAnalysisService

pytestmark = pytest.mark.skipif(
    not DEFAULT_KB_PATH.exists(),
    reason=(
        "Real O*NET knowledge base not present at "
        f"{DEFAULT_KB_PATH} - run notebooks/ONET_knowledge_base_pipeline.ipynb first."
    ),
)

BACKEND_ENGINEER_JD = """Backend Software Engineer

Responsibilities:

* Design and develop scalable backend services and REST APIs.
* Build backend applications using Python and modern software engineering practices.
* Design and optimize relational database queries using SQL and PostgreSQL.
* Develop and maintain APIs using frameworks such as FastAPI.
* Write clean, maintainable, and testable code.
* Investigate performance issues and improve backend system reliability.
* Implement authentication, authorization, and secure API practices.
* Collaborate with frontend engineers, AI engineers, and product teams to integrate backend
  services.
* Review code and contribute to technical design decisions.

Requirements:

* Strong programming skills in Python.
* Strong understanding of backend software engineering principles.
* Experience designing and building REST APIs.
* Experience with SQL and relational databases.
* Experience with PostgreSQL or similar database systems.
* Familiarity with FastAPI or similar Python web frameworks.
* Understanding of software testing and debugging.
* Experience with Git and collaborative development.
* Strong problem-solving and analytical skills.

Preferred:

* Experience with Docker and cloud platforms.
* Experience with asynchronous Python programming.
* Familiarity with microservices architecture.
* Experience optimizing backend systems for performance and scalability.
"""

AI_ENGINEER_JD = """AI Engineer

We are looking for an AI Engineer to design, develop, and deploy machine learning and
artificial intelligence solutions for real-world applications.

Responsibilities:

* Develop and optimize machine learning and deep learning models.
* Build AI-powered applications using Python and modern ML frameworks.
* Design and implement REST APIs for serving machine learning models.
* Work with large datasets to preprocess, analyze, and extract meaningful insights.
* Develop computer vision and natural language processing solutions when required.
* Evaluate model performance using appropriate metrics and continuously improve model accuracy.
* Deploy and optimize AI models for production environments.
* Collaborate with software engineers and product teams to integrate AI capabilities into
  production systems.

Requirements:

* Strong programming skills in Python.
* Experience with machine learning and deep learning.
* Experience with PyTorch or TensorFlow.
* Knowledge of computer vision and/or natural language processing.
* Experience building REST APIs, preferably with FastAPI.
* Familiarity with SQL and relational databases.
* Understanding of model deployment and optimization.
* Strong problem-solving and analytical skills.
* Experience with Git and collaborative software development.

Preferred:

* Experience with Transformers and large language models.
* Experience with Docker and cloud platforms.
* Experience optimizing models using ONNX or similar technologies.
"""

HEALTH_INFORMATICS_JD = """Health Informatics Specialist

We are looking for a Health Informatics Specialist to support healthcare organizations by
managing and analyzing health information systems and clinical data. The candidate should
have strong skills in electronic health records, healthcare data management, clinical
information systems, data analysis, and health information technology.

Responsibilities include analyzing healthcare data, maintaining electronic health records,
supporting clinical information systems, improving data quality, preparing reports, and
working with healthcare professionals to ensure accurate and secure health information.
"""

# Vocabulary that must never appear in a Backend Software Engineer's plan - these are the
# literal examples from the reported bug (nursing/clinical task content, and generic
# office-suite technologies that carry no signal about a backend role).
DISALLOWED_TASK_VOCAB = ("nursing", "patient", "clinical", "healthcare administrative")
DISALLOWED_TECH_NAMES = {"Microsoft Excel", "Microsoft Office software", "Microsoft Word"}


@pytest.fixture(scope="module")
def real_kb() -> OnetKnowledgeBase:
    return OnetKnowledgeBase()


@pytest.fixture
def planner(real_kb: OnetKnowledgeBase) -> InterviewPlannerService:
    return InterviewPlannerService(knowledge_base=real_kb)


async def _analyze(jd_text: str):
    return await JDAnalysisService(llm=FakeLLMClient()).analyze(jd_text)


async def _plan_for(planner: InterviewPlannerService, job_id: str, jd_text: str):
    return await planner.plan(job_id, await _analyze(jd_text))


async def test_backend_engineer_jd_plan_is_jd_only_by_construction(planner):
    """The core regression: even though this JD's top O*NET match is (still) Health
    Informatics Specialists - a known TF-IDF baseline limitation, not fixed here - the plan's
    competencies/technologies/tasks can only ever be JobSpec-sourced (`jobspec`/`both`), so
    none of that occupation's nursing/clinical/office-suite content can reach it structurally,
    regardless of how the match itself scores."""
    plan = await _plan_for(planner, "job-backend", BACKEND_ENGINEER_JD)

    assert plan.competencies, "expected at least one JD competency"
    assert plan.technologies, "expected at least one JD technology"
    assert all(c.source is not EvidenceSource.ONET for c in plan.competencies)
    assert all(t.source is not EvidenceSource.ONET for t in plan.technologies)
    assert all(t.source is not EvidenceSource.ONET for t in plan.tasks)

    tech_names = {t.name for t in plan.technologies}
    assert tech_names.isdisjoint(DISALLOWED_TECH_NAMES)
    for task in plan.tasks:
        lowered = task.task.lower()
        for banned in DISALLOWED_TASK_VOCAB:
            assert banned not in lowered, f"disallowed vocab {banned!r} leaked into: {task.task}"


async def test_backend_engineer_jd_tasks_come_from_its_own_responsibilities(planner):
    """Responsibilities now come from the JD's own "Responsibilities:" section, not a copy of
    the matched occupation's O*NET core tasks."""
    plan = await _plan_for(planner, "job-backend", BACKEND_ENGINEER_JD)
    task_texts = {t.task for t in plan.tasks}
    assert any("REST APIs" in t for t in task_texts)
    assert any("backend" in t.lower() for t in task_texts)


async def test_backend_engineer_jd_keeps_its_own_required_technologies_as_targets(planner):
    """The JD is authoritative: its own required skills must still drive the plan and its
    questions, independent of whatever O*NET signal is or isn't trusted."""
    plan = await _plan_for(planner, "job-backend", BACKEND_ENGINEER_JD)
    by_name = {t.name: t for t in plan.technologies}
    for expected in ("Python", "FastAPI", "SQL"):
        assert expected in by_name
        assert by_name[expected].source in (EvidenceSource.JOBSPEC, EvidenceSource.BOTH)
        assert by_name[expected].required is True

    tech_targets = {
        t.target for t in plan.coverage_targets if t.category.value == "technology"
    }
    assert tech_targets, "expected at least one technology coverage target"
    assert tech_targets.issubset(set(by_name))


async def test_health_informatics_jd_plan_is_also_jd_only(planner):
    """The JD-only rule applies uniformly, including to a *correct* occupation match - O*NET
    being right about the occupation still doesn't earn it a seat in the plan's requirements."""
    plan = await _plan_for(planner, "job-health-informatics", HEALTH_INFORMATICS_JD)
    assert plan.occupation_match.onet_soc_code == "15-1211.01"
    assert all(c.source is not EvidenceSource.ONET for c in plan.competencies)
    assert all(t.source is not EvidenceSource.ONET for t in plan.technologies)
    tech_names = {t.name for t in plan.technologies}
    assert tech_names.isdisjoint(DISALLOWED_TECH_NAMES)


async def test_health_informatics_jd_still_gets_relevant_onet_context(planner):
    """Fixing the false-positive leakage above must not make O*NET pointless: a JD that is
    genuinely, obviously about the matched occupation should still get relevant context
    available to question generation - the gates are relevance filters, not a blanket ban."""
    job_spec = await _analyze(HEALTH_INFORMATICS_JD)
    plan = await planner.plan("job-health-informatics", job_spec)
    assert plan.onet_grounding_used is True

    occupation = planner.knowledge_base.get_occupation(plan.occupation_match.onet_soc_code)
    context = planner._build_onet_context(job_spec, occupation, True, True)
    assert context, "expected genuinely relevant O*NET context to survive the relevance gate"
    assert "Health Informatics Specialists" in context


async def test_ai_engineer_jd_plan_is_jd_only_and_free_of_unrelated_onet_content(planner):
    """Test B: the AI Engineer JD's plan must be entirely JD-driven. Whatever occupation the
    matcher lands on (this JD's real match is Data Scientists - see
    test_onet_matching_regression.py - but this test doesn't depend on that), no unrelated
    O*NET competency/technology/task may appear as a plan requirement or a question."""
    plan = await _plan_for(planner, "job-ai-engineer", AI_ENGINEER_JD)

    tech_names = {t.name for t in plan.technologies}
    expected_tech = {
        "Python",
        "PyTorch",
        "TensorFlow",
        "Computer Vision",
        "Natural Language Processing",
    }
    assert expected_tech <= tech_names
    assert all(t.source is not EvidenceSource.ONET for t in plan.technologies)
    assert tech_names.isdisjoint(DISALLOWED_TECH_NAMES)

    assert all(c.source is not EvidenceSource.ONET for c in plan.competencies)

    task_texts = {t.task for t in plan.tasks}
    assert task_texts, "expected the JD's own responsibilities to populate tasks"
    assert all(t.source is not EvidenceSource.ONET for t in plan.tasks)
    for banned in ("vision therapy", "patient", "diagnose", "nursing"):
        assert not any(banned in t.lower() for t in task_texts)

    for coverage_target in plan.coverage_targets:
        assert coverage_target.target not in DISALLOWED_TECH_NAMES
        lowered_grounding = coverage_target.grounding.lower()
        for banned in ("vision therapy", "patient diagnosis", "excel", "power bi"):
            assert banned not in lowered_grounding


async def test_provenance_is_explicit_across_categories(planner):
    """Every selected competency/technology/task always carries an explicit EvidenceSource -
    the plan never presents JD-derived and (rare) O*NET-corroborated content
    indistinguishably, even though O*NET can no longer be the *sole* source of any of them."""
    plan = await _plan_for(planner, "job-backend", BACKEND_ENGINEER_JD)
    for c in plan.competencies:
        assert c.source in (EvidenceSource.JOBSPEC, EvidenceSource.BOTH)
    for t in plan.technologies:
        assert t.source in (EvidenceSource.JOBSPEC, EvidenceSource.BOTH)
    for t in plan.tasks:
        assert t.source in (EvidenceSource.JOBSPEC, EvidenceSource.BOTH)
