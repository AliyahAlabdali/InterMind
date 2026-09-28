import pytest

from app.core.exceptions import NoOccupationMatch
from app.domain.interview_plan import EvidenceSource, QuestionCategory, RequirementLevel
from app.domain.job import Competency, JobSpec, Skill
from app.domain.occupation import OccupationMatch
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.interview_planner import InterviewPlannerService
from app.services.target_identity import target_question_id
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"


@pytest.fixture
def planner():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    return InterviewPlannerService(knowledge_base=kb)


@pytest.fixture
def software_job_spec():
    return JobSpec(
        role_title="Backend Software Engineer",
        skills=[Skill(name="Python", required=True), Skill(name="Docker", required=False)],
        competencies=[Competency(name="Critical Thinking")],
        responsibilities=["Ship backend features.", "Review pull requests."],
        summary="Builds and maintains backend software services using Python.",
    )


async def test_plan_matches_expected_occupation(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    assert plan.job_id == "job-1"
    assert plan.role_title == "Backend Software Engineer"
    assert plan.occupation_match.onet_soc_code == "15-1252.00"
    assert plan.occupation_match.title == "Software Developers"
    # the remaining fixture occupation should show up as a lower-ranked alternate
    assert any(m.onet_soc_code == "35-2014.00" for m in plan.alternate_matches)


# --- JobSpec is the sole source of plan competencies/technologies/tasks --------------------


async def test_competencies_come_only_from_the_jobspec(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    names = {c.name for c in plan.competencies}
    assert names == {"Critical Thinking"}  # the fixture occupation's other skills, e.g.
    # "Programming"/"Active Learning", must not appear even though the match is reliable.
    assert "Programming" not in names
    assert "Active Learning" not in names


async def test_competency_overlap_with_onet_is_annotated_not_added(planner, software_job_spec):
    """"Critical Thinking" is in both the JobSpec and the matched occupation's skill list -
    that's an annotation (BOTH) on an existing JD item, not a new O*NET-sourced entry."""
    plan = await planner.plan("job-1", software_job_spec)
    by_name = {c.name: c for c in plan.competencies}
    assert by_name["Critical Thinking"].source == EvidenceSource.BOTH
    assert by_name["Critical Thinking"].onet_importance == 4.0
    assert all(c.source is not EvidenceSource.ONET for c in plan.competencies)


async def test_technologies_come_only_from_the_jobspec(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    names = {t.name for t in plan.technologies}
    assert names == {"Python", "Docker"}
    # The fixture occupation's own "Git" technology must not appear just because the match
    # is reliable.
    assert "Git" not in names
    assert all(t.source is not EvidenceSource.ONET for t in plan.technologies)


async def test_technology_overlap_with_onet_is_annotated_not_added(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    by_name = {t.name: t for t in plan.technologies}
    assert by_name["Python"].source == EvidenceSource.BOTH
    assert by_name["Python"].hot is True
    assert by_name["Docker"].source == EvidenceSource.JOBSPEC


async def test_tasks_come_only_from_jobspec_responsibilities(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    task_texts = {t.task for t in plan.tasks}
    assert task_texts == {"Ship backend features.", "Review pull requests."}
    # The fixture occupation's own core tasks ("Analyze user needs...") must not appear.
    assert not any("Analyze user needs" in t for t in task_texts)
    assert all(t.source == EvidenceSource.JOBSPEC for t in plan.tasks)


async def test_no_responsibilities_in_jobspec_means_no_tasks(planner):
    """Tasks have no O*NET fallback anymore - an empty JobSpec.responsibilities means an
    empty plan.tasks, never a copy of the matched occupation's core tasks."""
    job_spec = JobSpec(role_title="Software Developer")
    plan = await planner.plan("job-2", job_spec)
    assert plan.tasks == []


async def test_thematically_similar_but_distinctly_worded_responsibilities_are_both_kept(
    planner,
):
    """Real-run finding: a JD listed two responsibilities that read as topically overlapping -
    "Design and implement backend services for AI-powered applications" and "Develop RESTful
    APIs that expose ML capabilities to client applications" - both became separate task
    coverage targets, raising the question of whether the planner was producing a redundant
    target.

    Investigation result: this is *not* a planner bug. `_build_tasks` only ever deduplicates
    exact (normalized) text matches - by design, see its docstring - and these two sentences
    share almost no words in common (they are related in real-world *meaning*, not in text).
    Catching this would require an actual semantic-similarity judgment, which the project
    deliberately does not build (see the module docstring's "no LLM just to compare target
    similarity" constraint) - two JD bullets describing genuinely different responsibilities
    that both happen to concern AI/ML backend work are legitimately distinct targets, not a
    normalization defect. This test pins down that current, correct behaviour so it isn't
    "fixed" into incorrectly collapsing two real, differently-worded responsibilities.
    """
    job_spec = JobSpec(
        role_title="Backend Engineer, AI Platform",
        responsibilities=[
            "Design and implement backend services for AI-powered applications.",
            "Develop RESTful APIs that expose ML capabilities to client applications.",
        ],
    )
    plan = await planner.plan("job-3", job_spec)
    task_texts = {t.task for t in plan.tasks}
    assert task_texts == {
        "Design and implement backend services for AI-powered applications.",
        "Develop RESTful APIs that expose ML capabilities to client applications.",
    }
    assert len(plan.tasks) == 2  # neither was collapsed into the other


# --- coverage_targets: WHAT the adaptive interview can assess, not a fixed question script --


async def test_coverage_targets_cover_every_category_with_jobspec_content(
    planner, software_job_spec
):
    plan = await planner.plan("job-1", software_job_spec)
    categories = {t.category for t in plan.coverage_targets}
    expected = {QuestionCategory.COMPETENCY, QuestionCategory.TECHNOLOGY, QuestionCategory.TASK}
    assert categories == expected
    for t in plan.coverage_targets:
        assert t.id
        assert t.target
        assert t.grounding
        # Every target is grounded in the job description first - O*NET may be mentioned as
        # secondary corroboration (for BOTH-sourced items) but is never the primary source.
        assert t.grounding.lower().startswith("job description")


async def test_coverage_targets_include_every_competency_technology_and_task(
    planner, software_job_spec
):
    """Unlike the old fixed-script plan, nothing here is pre-selected as "will become a
    question" - every eligible item (up to the max_* caps) is a coverage target; which ones an
    interview actually asks about is an interview-time decision (see
    app.services.target_selection), not a plan-time one."""
    plan = await planner.plan("job-1", software_job_spec)
    targets = {t.target for t in plan.coverage_targets}
    assert targets == {
        "Critical Thinking",
        "Python",
        "Docker",
        "Ship backend features.",
        "Review pull requests.",
    }


async def test_caps_are_respected(software_job_spec):
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    planner = InterviewPlannerService(
        knowledge_base=kb,
        max_competencies=2,
        max_technologies=1,
        max_tasks=1,
    )
    plan = await planner.plan("job-1", software_job_spec)
    assert len(plan.competencies) <= 2
    assert len(plan.technologies) <= 1
    assert len(plan.tasks) <= 1
    assert len(plan.coverage_targets) <= 4


async def test_max_technologies_cap_never_drops_a_required_skill_for_a_preferred_one(planner):
    """Real-run finding: a JD listing more than `max_technologies` skills, with required ones
    (e.g. PostgreSQL, Git) appearing *after* enough preferred ones (e.g. Docker, AWS) in JD
    order, silently dropped the required skills from the plan entirely - they never became a
    coverage target at all, so no amount of required-first prioritization at question-selection
    time (`app.services.target_selection`) could recover them; they were never in the pool.
    This is the analogous fix one layer earlier: the cap itself must never prefer a preferred
    skill over a required one, regardless of JD order."""
    job_spec = JobSpec(
        role_title="Backend Software Engineer",
        skills=[
            Skill(name="Docker", required=False),
            Skill(name="AWS", required=False),
            Skill(name="Async Python", required=False),
            Skill(name="CI/CD", required=False),
            Skill(name="Python", required=True),
            Skill(name="FastAPI", required=True),
            Skill(name="PostgreSQL", required=True),
            Skill(name="Git", required=True),
        ],
    )
    kb_planner = InterviewPlannerService(knowledge_base=planner.knowledge_base, max_technologies=4)
    plan = await kb_planner.plan("job-1", job_spec)

    names = {t.name for t in plan.technologies}
    assert names == {"Python", "FastAPI", "PostgreSQL", "Git"}  # every required skill survives
    assert "Docker" not in names and "AWS" not in names  # preferred ones lose the tiebreak

    # Display order is still the original JD order, restricted to the survivors - the plan
    # never silently reorders the JD, only which subset makes the cut changes.
    assert [t.name for t in plan.technologies] == ["Python", "FastAPI", "PostgreSQL", "Git"]


# --- Coverage policy: required technologies are prioritized ahead of preferred ones ----------
#
# Real-world finding: a Software Engineer JD listing 8 technologies (Python, Java, REST APIs,
# SQL/NoSQL, AWS/GCP, Git, CI/CD, Docker/Kubernetes) only produced questions for the first 4 in
# JD order - silently dropping later-listed required technologies in favor of earlier-listed
# preferred ones, with no prioritization at all. Priority is now baked into every coverage
# target so any interview-time selector can prioritize required targets without re-deriving
# required-ness itself - see `app.services.target_selection`.


async def test_required_technologies_get_a_lower_priority_than_preferred_ones(planner):
    job_spec = JobSpec(
        role_title="Backend Software Engineer",
        skills=[
            Skill(name="Excel", required=False),
            Skill(name="PowerPoint", required=False),
            Skill(name="Photoshop", required=False),
            Skill(name="Python", required=True),
            Skill(name="SQL", required=True),
        ],
    )
    plan = await planner.plan("job-1", job_spec)

    # The full plan still lists every technology, in JD order - the JD is never silently
    # trimmed just because there isn't capacity for a question about every item.
    assert [t.name for t in plan.technologies] == [
        "Excel",
        "PowerPoint",
        "Photoshop",
        "Python",
        "SQL",
    ]

    by_target = {
        t.target: t for t in plan.coverage_targets if t.category == QuestionCategory.TECHNOLOGY
    }
    assert by_target["Python"].requirement_level == RequirementLevel.REQUIRED
    assert by_target["SQL"].requirement_level == RequirementLevel.REQUIRED
    assert by_target["Excel"].requirement_level == RequirementLevel.PREFERRED

    # Required targets always sort before preferred ones within the category, regardless of
    # JD position.
    assert by_target["Python"].priority < by_target["Excel"].priority
    assert by_target["SQL"].priority < by_target["PowerPoint"].priority


async def test_priority_preserves_jd_order_within_each_requirement_tier(planner):
    """Ties (same required-ness) keep their original JD order."""
    job_spec = JobSpec(
        role_title="Backend Software Engineer",
        skills=[
            Skill(name="Docker", required=True),
            Skill(name="Kubernetes", required=True),
            Skill(name="Excel", required=False),
        ],
    )
    plan = await planner.plan("job-1", job_spec)
    by_target = {
        t.target: t for t in plan.coverage_targets if t.category == QuestionCategory.TECHNOLOGY
    }
    assert by_target["Docker"].priority < by_target["Kubernetes"].priority


async def test_competencies_and_tasks_are_always_required(planner, software_job_spec):
    """JobSpec has no required/preferred distinction for competencies/tasks - every one is
    REQUIRED, since a JD names a competency/responsibility because it matters."""
    plan = await planner.plan("job-1", software_job_spec)
    for t in plan.coverage_targets:
        if t.category in (QuestionCategory.COMPETENCY, QuestionCategory.TASK):
            assert t.requirement_level == RequirementLevel.REQUIRED


async def test_no_occupation_match_raises_when_kb_cannot_rank(
    planner, software_job_spec, monkeypatch
):
    monkeypatch.setattr(planner.knowledge_base, "match_jobspec", lambda job_spec, top_k=5: [])
    with pytest.raises(NoOccupationMatch):
        await planner.plan("job-1", software_job_spec)


# --- O*NET context for question generation (never a plan requirement) ----------------------


async def test_reliable_match_makes_onet_context_available(planner, software_job_spec):
    """A confident match still contributes *context* for question phrasing - the JD-only
    rule for plan.competencies/technologies/tasks must not make O*NET pointless. The context
    is persisted on the plan (not spent immediately), since phrasing now happens at interview
    time - see InterviewPlan.onet_context."""
    plan = await planner.plan("job-1", software_job_spec)
    assert plan.onet_grounding_used is True
    assert "Software Developers" in plan.onet_context
    assert "Git" in plan.onet_context  # occupation-specific, not JD-required - genuine signal

    context = planner._build_onet_context(software_job_spec, _occupation(planner), True, True)
    assert context == plan.onet_context


async def test_onet_context_never_repeats_an_existing_jobspec_item(planner, software_job_spec):
    """"Python" is already a JD requirement - it must not also show up as "new" O*NET context
    (that would look like O*NET independently corroborating a requirement it didn't source)."""
    context = planner._build_onet_context(software_job_spec, _occupation(planner), True, True)
    assert "- Python" not in context


async def test_weak_ambiguous_match_produces_no_onet_context(
    planner, software_job_spec, monkeypatch
):
    """Regression test for the reported bug: a job description that only weakly/ambiguously
    matches an O*NET occupation (here simulated with two near-tied low scores, mirroring the
    real "Senior Backend Software Engineer" -> "Forest Fire Inspectors" 0.1346 vs "Validation
    Engineers" 0.1309 case) must not surface that occupation's content as context, and - as
    always now - the plan itself is JD-only regardless.
    """
    monkeypatch.setattr(
        planner.knowledge_base,
        "match_jobspec",
        lambda job_spec, top_k=5: [
            OccupationMatch(onet_soc_code="15-1252.00", title="Software Developers", score=0.135),
            OccupationMatch(onet_soc_code="35-2014.00", title="Cooks, Restaurant", score=0.131),
        ],
    )

    plan = await planner.plan("job-1", software_job_spec)

    assert plan.onet_grounding_used is False
    assert plan.onet_context == ""
    assert {c.name for c in plan.competencies} == {"Critical Thinking"}
    assert {t.name for t in plan.technologies} == {"Python", "Docker"}
    assert all(c.source is not EvidenceSource.ONET for c in plan.competencies)
    assert all(t.source is not EvidenceSource.ONET for t in plan.technologies)
    # The match itself is still surfaced for transparency - just not used as a signal source.
    assert plan.occupation_match.onet_soc_code == "15-1252.00"


async def test_weak_match_with_no_alternates_only_needs_the_absolute_floor(
    planner, software_job_spec, monkeypatch
):
    """With nothing to compare against (e.g. a tiny KB), there is no ambiguity to detect - only
    the absolute-score floor applies."""
    monkeypatch.setattr(
        planner.knowledge_base,
        "match_jobspec",
        lambda job_spec, top_k=5: [
            OccupationMatch(onet_soc_code="15-1252.00", title="Software Developers", score=0.02),
        ],
    )
    plan = await planner.plan("job-1", software_job_spec)
    assert plan.onet_grounding_used is False  # below the absolute floor


async def test_borderline_reliable_match_offers_no_technology_context(
    planner, software_job_spec, monkeypatch
):
    """A match can clear the general reliability gate (so task context / BOTH-merges still
    happen) while still being too borderline to offer a brand-new technology as context -
    mirroring the real "Backend Software Engineer" -> "Health Informatics Specialists" case,
    where a 0.0201 gap/1.195 ratio was enough to pass the general gate but let through
    unrelated technologies (e.g. "Microsoft Power BI", "R") in the pre-this-pass design."""
    monkeypatch.setattr(
        planner.knowledge_base,
        "match_jobspec",
        lambda job_spec, top_k=5: [
            OccupationMatch(onet_soc_code="15-1252.00", title="Software Developers", score=0.15),
            OccupationMatch(onet_soc_code="35-2014.00", title="Cooks, Restaurant", score=0.14),
        ],
    )
    plan = await planner.plan("job-1", software_job_spec)
    assert plan.onet_grounding_used is True  # general gate: 0.01 gap / 1.071 ratio clears it
    # "Python" is already JD-required, so annotating it with O*NET metadata (-> BOTH) is not
    # "adding a new O*NET technology" and must still happen.
    by_name = {t.name: t for t in plan.technologies}
    assert by_name["Python"].source == EvidenceSource.BOTH
    # No O*NET-only technology reaches the plan either way (JD-only by construction) - and the
    # match isn't confident enough (0.01 gap / 1.071 ratio - well under the 0.03/1.3 bar) for
    # "Git" to be offered even as context.
    context = planner._build_onet_context(
        software_job_spec, _occupation(planner), True, confident_for_tech_context=False
    )
    assert "Git" not in context


async def test_rebuilding_the_same_plan_produces_stable_target_ids_and_priority_order(
    planner, software_job_spec
):
    first = await planner.plan("job-1", software_job_spec)
    second = await planner.plan("job-1", software_job_spec)

    first_ids = [t.id for t in first.coverage_targets]
    second_ids = [t.id for t in second.coverage_targets]
    assert first_ids == second_ids  # same order, not just the same set
    assert len(first_ids) == len(set(first_ids))  # every id in a plan is unique


async def test_different_job_ids_get_different_target_ids_for_the_same_target(
    planner, software_job_spec
):
    plan_a = await planner.plan("job-a", software_job_spec)
    plan_b = await planner.plan("job-b", software_job_spec)
    ids_a = {t.id for t in plan_a.coverage_targets}
    ids_b = {t.id for t in plan_b.coverage_targets}
    assert ids_a.isdisjoint(ids_b)


async def test_target_id_is_the_shared_deterministic_hash(planner, software_job_spec):
    plan = await planner.plan("job-1", software_job_spec)
    competency_target = next(
        t for t in plan.coverage_targets if t.category == QuestionCategory.COMPETENCY
    )
    assert competency_target.id == target_question_id(
        "job-1", competency_target.category, competency_target.target
    )


# --- ubiquity/relevance gates on O*NET *context* (enrich, never redefine the job) -----------
#
# These use a purpose-built, larger fixture KB (24 occupations) rather than the 2-occupation
# fixture above: the ubiquity gate needs enough occupations for a prevalence fraction to be
# statistically meaningful (see `_MIN_OCCUPATIONS_FOR_PREVALENCE_STAT`). "Generic Office Suite"
# stands in for real-world ubiquitous tools like Microsoft Excel/Office - the fixture proves the
# *mechanism* generalizes without hard-coding any specific product name.

UBIQUITY_FIXTURE_KB_PATH = FIXTURES / "onet_kb_ubiquity_fixture.jsonl"


@pytest.fixture
def ubiquity_planner():
    kb = OnetKnowledgeBase(path=UBIQUITY_FIXTURE_KB_PATH)
    return InterviewPlannerService(knowledge_base=kb)


@pytest.fixture
def backend_job_spec():
    return JobSpec(
        role_title="Backend Software Engineer",
        skills=[
            Skill(name="Python", required=True),
            Skill(name="Docker", required=False),
        ],
        competencies=[Competency(name="Critical Thinking")],
        summary="Builds backend software engineer services using Python.",
    )


def _occupation(planner: InterviewPlannerService, code: str = "15-1252.00"):
    return planner.knowledge_base.get_occupation(code)


async def test_ubiquitous_onet_technology_is_not_offered_as_context(
    ubiquity_planner, backend_job_spec
):
    """A technology present in almost every occupation in the KB (a stand-in for Microsoft
    Excel/Office) must not be offered as context just because the matched occupation lists
    it - it carries no real signal about *this* job. It was never eligible to reach
    plan.technologies at all under the new architecture (JD-only)."""
    plan = await ubiquity_planner.plan("job-1", backend_job_spec)
    assert "Generic Office Suite" not in {t.name for t in plan.technologies}
    assert "Generic Office Suite" not in plan.onet_context


async def test_occupation_specific_onet_technology_still_offered_as_context(
    ubiquity_planner, backend_job_spec
):
    """A technology that is *not* ubiquitous across the KB (present in only this occupation)
    is still offered as context - the ubiquity gate must not suppress genuinely specific
    signal, even though (per the new architecture) it never becomes a plan requirement."""
    plan = await ubiquity_planner.plan("job-1", backend_job_spec)
    assert "Git" in plan.onet_context
    assert "Git" not in {t.name for t in plan.technologies}  # never a plan requirement


async def test_onet_core_task_irrelevant_to_jobspec_is_filtered_from_context(
    ubiquity_planner, backend_job_spec
):
    """Regression test for the reported bug's root cause: an O*NET "core task" is only proof
    that the task matters *to the matched occupation*, never proof that it's relevant to this
    JobSpec. The fixture's matched occupation includes one task lifted from an unrelated
    domain (clinical/nursing) alongside two genuinely relevant ones - only the relevant ones
    may appear as context, and none of them ever reach plan.tasks (JD-only)."""
    plan = await ubiquity_planner.plan("job-1", backend_job_spec)
    assert "clinical" not in plan.onet_context.lower()
    assert "patients" not in plan.onet_context.lower()
    assert "software requirements" in plan.onet_context
    assert "testing or validation" in plan.onet_context
    assert plan.tasks == []  # backend_job_spec has no `responsibilities` - nothing to show


async def test_jd_required_technology_remains_a_target_regardless_of_onet(
    ubiquity_planner, backend_job_spec
):
    """The JD is authoritative: a JobSpec-required skill is a target no matter what O*NET
    says about the matched occupation."""
    plan = await ubiquity_planner.plan("job-1", backend_job_spec)
    by_name = {t.name: t for t in plan.technologies}
    assert by_name["Python"].source == EvidenceSource.BOTH  # required + also in O*NET
    assert by_name["Docker"].source == EvidenceSource.JOBSPEC  # required, O*NET-absent
    tech_targets = {
        t.target for t in plan.coverage_targets if t.category == QuestionCategory.TECHNOLOGY
    }
    assert "Python" in tech_targets
    assert "Docker" in tech_targets


async def test_jd_preferred_technology_keeps_preferred_provenance(ubiquity_planner):
    """A JD "preferred" (not required) skill must remain distinguishable as preferred, not
    silently collapse into "required" or disappear."""
    job_spec = JobSpec(
        role_title="Backend Software Engineer",
        skills=[
            Skill(name="Python", required=True),
            Skill(name="Kubernetes", required=False),
        ],
        summary="Builds backend software engineer services using Python.",
    )
    plan = await ubiquity_planner.plan("job-1", job_spec)
    by_name = {t.name: t for t in plan.technologies}
    assert by_name["Python"].required is True
    assert by_name["Kubernetes"].required is False
    assert set(by_name) == {"Python", "Kubernetes"}  # no O*NET-only technology present at all

    by_target = {t.target: t for t in plan.coverage_targets}
    assert by_target["Kubernetes"].requirement_level == RequirementLevel.PREFERRED


async def test_onet_cannot_redefine_the_job_even_with_unrelated_occupation_content(
    ubiquity_planner, backend_job_spec
):
    """Test E: an occupation record containing obviously unrelated technologies/tasks (this
    fixture's matched occupation includes a near-universal "Generic Office Suite" and a
    clinical/nursing task with no relation to backend engineering) must not change the plan's
    requirements at all - plan.competencies/technologies/tasks are exactly what the JobSpec
    itself states, full stop."""
    plan = await ubiquity_planner.plan("job-1", backend_job_spec)

    assert {c.name for c in plan.competencies} == {c.name for c in backend_job_spec.competencies}
    assert {t.name for t in plan.technologies} == {s.name for s in backend_job_spec.skills}
    assert {t.task for t in plan.tasks} == set(backend_job_spec.responsibilities)
    assert plan.tasks == []  # backend_job_spec states no responsibilities
