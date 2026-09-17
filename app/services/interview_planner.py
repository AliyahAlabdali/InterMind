"""Interview planning use case: JobSpec -> O*NET occupation match -> structured InterviewPlan.

Core principle: **the Job Description defines what the candidate is evaluated on; O*NET
enriches how InterMind understands and asks about those requirements.**

::

    Job Description -> OpenAI/FakeLLM -> JobSpec
                                            |
                                  Interview Planner
                                  |    |     |
                          Competencies Technologies Responsibilities   <- JobSpec only
                                  |    |     |
                                  +----+-----+
                                       |
                                O*NET matching -> relevant O*NET context (persisted, not spent)
                                       |
                                Coverage Targets (WHAT to assess)
                                       |
                          (interview time) adaptive selection + runtime question generation

``InterviewPlan.competencies``/``technologies``/``tasks`` are always built from the JobSpec
alone (``EvidenceSource.JOBSPEC``, or ``BOTH`` when the matched occupation happens to rate the
same name too - see each model's docstring in ``app.domain.interview_plan``). O*NET is never
the source of a *new* competency/technology/task: it cannot silently add a candidate
requirement the job description never stated. What O*NET *can* do is supply relevant
occupational context - the matched occupation's title/description plus a handful of its own
technologies/tasks that are actually relevant to this JobSpec - to runtime question phrasing,
so questions can be phrased with more depth/realism. See ``_build_onet_context``.

**This service no longer generates any question text.** It used to call an LLM once, upfront,
to phrase every question for the whole interview - producing a fixed script the candidate would
always be asked in the same order, regardless of their answers. That is the architectural issue
this module was rewritten to fix: it now only decides *what* the interview should be able to
assess (``coverage_targets``, see ``_build_coverage_targets``) and persists the O*NET context
that phrasing will eventually use (``InterviewPlan.onet_context``). *What to ask next* and
*the actual question text* are decided at interview time by ``app.services.target_selection``
and ``app.agents.interview_graph`` - see those modules for the adaptive loop.

Two independent relevance gates decide what, if anything, ends up in the O*NET context, reusing
the same signals this module already computed for the (retired) "inject into the plan" design:
``_match_is_reliable`` decides whether the matched *occupation* is trusted at all; corpus-wide
technology prevalence (``OnetKnowledgeBase.technology_prevalence``) and per-task relevance to
the JobSpec (``OnetKnowledgeBase.relevance_to_jobspec``) decide, per candidate item, whether
that specific piece of O*NET content is worth mentioning as context. Nothing here is hard-coded
to a technology, task, or occupation name - the gates are purely statistical/relevance-based.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import NoOccupationMatch
from app.domain.interview_plan import (
    CompetencyCoverage,
    CoverageTarget,
    EvidenceSource,
    InterviewPlan,
    QuestionCategory,
    RequirementLevel,
    SelectedTask,
    SelectedTechnology,
)
from app.domain.job import JobSpec
from app.domain.occupation import OccupationRecord
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.target_identity import target_question_id as _question_id
from app.services.text_normalize import normalize_name as _normalize

#: Minimum absolute TF-IDF cosine score for a top match to be trusted at all. Calibrated
#: against this baseline's real score range (see the Milestone O*NET-matching investigations
#: in project memory): even *good* matches on the real 1016-occupation KB typically score
#: 0.13-0.20, so this floor only screens out near-zero, essentially-no-overlap matches.
_MIN_RELIABLE_SCORE = 0.08

#: Minimum absolute gap (top score minus runner-up score) OR minimum ratio (top / runner-up)
#: for the top match to be considered a confident pick rather than a coin flip among
#: near-tied, similarly-weak candidates. Calibrated against real examples on the full O*NET
#: 31.0 KB: a clearly-wrong top match (a "Senior Backend Software Engineer" JD top-matching
#: "Forest Fire Inspectors and Prevention Specialists" at 0.1346 with "Validation Engineers" a
#: near-tied second at 0.1309) sits at a 0.0037 gap / 1.03 ratio, while a correct match against
#: two *adjacent, both-plausible* occupations (a "Health Informatics Specialist" JD
#: top-matching "Health Informatics Specialists" 0.1820 over the closely-related "Health
#: Information Technologists and Medical Registrars" 0.1676) still sits as low as a 0.0144 gap
#: / 1.086 ratio - two genuinely-relevant occupations for the same JD naturally score close
#: together. These thresholds sit just below that second case and well above the first, so this
#: gate stays a coarse plausibility check on the *occupation pick*.
_MIN_RELIABLE_MARGIN = 0.01
_MIN_RELIABLE_MARGIN_RATIO = 1.05

#: A "reliable" occupation match (above) is a coarse, all-or-nothing gate on the *occupation
#: pick* - it says nothing about whether any individual piece of that occupation's O*NET
#: content is actually relevant to this specific job description. Every candidate context item
#: gets a second, item-level check before it can be offered to question generation.
#:
#: Technologies: filtered by corpus-wide prevalence (`OnetKnowledgeBase.technology_prevalence`)
#: rather than a name blocklist - deliberately not hard-coded to "Excel" or any other product,
#: since the same "generic office tool" problem recurs for any occupation. Skipped entirely on
#: small KBs (e.g. test fixtures) where a prevalence fraction is statistically meaningless.
_MAX_UBIQUITOUS_TECH_PREVALENCE = 0.3
_MIN_OCCUPATIONS_FOR_PREVALENCE_STAT = 20

#: Tasks: filtered by TF-IDF relevance to the JobSpec itself (`OnetKnowledgeBase.
#: relevance_to_jobspec`), not merely "importance to the matched occupation" (an O*NET Core
#: Task is important *to that occupation* - it says nothing about whether it's relevant to
#: *this* JD). Calibrated against real examples on the full O*NET 31.0 KB: an unrelated
#: occupation's tasks (Health Informatics Specialists' nursing/patient tasks, checked against a
#: Backend Software Engineer JobSpec) score 0.0-0.033, while a genuinely relevant occupation's
#: tasks score comfortably higher (0.04-0.4+ on the real KB; much higher still on small
#: fixtures, where shared vocabulary is proportionally rarer). Engineering heuristic, not a
#: validated probability - see the module docstring's core principle.
_MIN_TASK_RELEVANCE = 0.05

#: Technologies get a *second*, stricter macro check before being offered as context at all:
#: named tools read as concrete, specific signals in a way generic competencies don't, so the
#: bar for offering one from O*NET rather than the JD is higher. These are the same
#: "genuinely confident match" reference numbers already used to characterize a *good* match
#: elsewhere in this module (e.g. "Digital Marketing Specialist" -> "Market Research Analysts
#: and Marketing Specialists", 0.03+ gap / 1.3+ ratio) - deliberately stricter than
#: `_MIN_RELIABLE_MARGIN`/`_MIN_RELIABLE_MARGIN_RATIO`. A borderline match (e.g. "Backend
#: Software Engineer" -> "Health Informatics Specialists", 0.0201 gap / 1.195 ratio) clears the
#: general gate but not this one, so no O*NET technology context is offered at all - not
#: because any single technology name is blocklisted, but because the occupation pick itself
#: isn't confident enough to treat as a source of technology signal. Tasks are not given this
#: second gate because they already have a robust per-item relevance check
#: (`_MIN_TASK_RELEVANCE`) that short single technology names can't reliably support (see
#: `relevance_to_jobspec`'s docstring).
_MIN_CONFIDENT_TECH_CONTEXT_MARGIN = 0.03
_MIN_CONFIDENT_TECH_CONTEXT_MARGIN_RATIO = 1.3

#: Cap on how many relevant O*NET technologies/tasks are offered as context, so the prompt
#: stays a short, curated list rather than a wholesale dump of the occupation record.
_MAX_CONTEXT_TECHNOLOGIES = 3
_MAX_CONTEXT_TASKS = 3


def _match_is_reliable(
    top_score: float,
    alternates: list,
    *,
    min_margin: float = _MIN_RELIABLE_MARGIN,
    min_margin_ratio: float = _MIN_RELIABLE_MARGIN_RATIO,
) -> bool:
    """Whether an occupation match is confident enough to use as supplementary context.

    Not a per-occupation rule - purely a function of the score distribution returned for
    *this* JobSpec, so it never hard-codes which occupations are "good" or "bad" matches.
    With no alternates to compare against (e.g. a tiny test-fixture KB), only the absolute
    floor applies, since there is nothing to be ambiguous *against*. ``min_margin``/
    ``min_margin_ratio`` let a caller ask a stricter version of the same question (see
    `_MIN_CONFIDENT_TECH_CONTEXT_MARGIN`) without duplicating the floor/no-alternates logic.
    """
    if top_score < _MIN_RELIABLE_SCORE:
        return False
    if not alternates:
        return True
    second_score = alternates[0].score
    gap = top_score - second_score
    ratio = (top_score / second_score) if second_score > 0 else float("inf")
    return gap >= min_margin or ratio >= min_margin_ratio


@dataclass
class InterviewPlannerService:
    """Builds an :class:`InterviewPlan` from a :class:`JobSpec`.

    Occupation matching uses :class:`OnetKnowledgeBase` (deterministic TF-IDF baseline - a
    retrieval proof-of-concept, not a validated classifier; see Milestone 2). This service is
    purely deterministic and makes no LLM calls of its own - see the module docstring for why
    question phrasing moved to interview time.

    The job description is the *only* source of plan competencies/technologies/tasks (see the
    module docstring). The matched O*NET occupation contributes, at most, a short relevance
    -filtered context block, persisted on the plan for the interview graph to use when phrasing
    questions - never a new plan entry.

    **Coverage, not a question count**: ``max_competencies``/``max_technologies``/``max_tasks``
    still bound how much content is even eligible to be assessed (so an unusually long JD
    doesn't produce an unbounded coverage list), but this service no longer decides how many of
    those actually become questions, or in what order - that is an interview-time decision (see
    ``app.services.target_selection.TargetSelectionPolicy``), made adaptively against the
    candidate's actual answers. ``coverage_targets`` carries a ``requirement_level``
    (``Skill.required`` for technologies; competencies/tasks have no such distinction in
    ``JobSpec`` and are always ``required``) and a ``priority`` (required-before-preferred,
    then JD order) so that policy has what it needs to prioritize required targets without this
    service pre-committing to which ones "win" a question slot.
    """

    knowledge_base: OnetKnowledgeBase
    top_k_matches: int = 5
    max_competencies: int = 8
    max_technologies: int = 8
    max_tasks: int = 5

    async def plan(self, job_id: str, job_spec: JobSpec) -> InterviewPlan:
        matches = self.knowledge_base.match_jobspec(job_spec, top_k=self.top_k_matches)
        if not matches:
            raise NoOccupationMatch(job_spec.role_title)
        top_match, *alternates = matches
        occupation = self.knowledge_base.get_occupation(top_match.onet_soc_code)
        reliable = _match_is_reliable(top_match.score, alternates)
        confident_for_tech_context = reliable and _match_is_reliable(
            top_match.score,
            alternates,
            min_margin=_MIN_CONFIDENT_TECH_CONTEXT_MARGIN,
            min_margin_ratio=_MIN_CONFIDENT_TECH_CONTEXT_MARGIN_RATIO,
        )

        competencies = self._build_competencies(job_spec, occupation, reliable)
        technologies = self._build_technologies(job_spec, occupation, reliable)
        tasks = self._build_tasks(job_spec, occupation, reliable)
        onet_context = self._build_onet_context(
            job_spec, occupation, reliable, confident_for_tech_context
        )
        coverage_targets = _build_coverage_targets(
            job_id, competencies=competencies, technologies=technologies, tasks=tasks
        )

        return InterviewPlan(
            job_id=job_id,
            role_title=job_spec.role_title,
            seniority=job_spec.seniority,
            occupation_match=top_match,
            alternate_matches=alternates,
            onet_grounding_used=bool(onet_context),
            onet_context=onet_context,
            competencies=competencies,
            technologies=technologies,
            tasks=tasks,
            coverage_targets=coverage_targets,
        )

    def _build_competencies(
        self, job_spec: JobSpec, occupation: OccupationRecord, reliable: bool
    ) -> list[CompetencyCoverage]:
        """JD competencies only. O*NET may annotate (-> BOTH) an existing one, never add one."""
        selected: dict[str, CompetencyCoverage] = {
            _normalize(c.name): CompetencyCoverage(name=c.name, source=EvidenceSource.JOBSPEC)
            for c in job_spec.competencies
        }
        if reliable:
            for oc in occupation.competencies:
                key = _normalize(oc.skill)
                if key in selected:
                    selected[key] = selected[key].model_copy(
                        update={
                            "source": EvidenceSource.BOTH,
                            "onet_importance": oc.importance,
                            "onet_level": oc.level,
                        }
                    )
        return list(selected.values())[: self.max_competencies]

    def _build_technologies(
        self, job_spec: JobSpec, occupation: OccupationRecord, reliable: bool
    ) -> list[SelectedTechnology]:
        """JD technologies only. O*NET may annotate (-> BOTH) an existing one, never add one.

        Real-run finding: with more than ``max_technologies`` skills in the JD, capping in raw
        JD order could silently drop a *required* skill (e.g. PostgreSQL, Git) listed after
        enough earlier, merely-preferred ones (e.g. Docker, AWS) to fill the cap - the required
        skill would then never even become a coverage target, let alone get asked about,
        regardless of how well ``app.services.target_selection`` prioritizes required targets
        afterward, since it was never in the pool to begin with. Sorting required-before-
        preferred (stable - JD order preserved within each tier) before applying the cap is the
        same "required must never lose to preferred merely because of list position" principle
        already applied one layer later, at question-selection time - applied here too, at
        plan-build time, so a required skill is never excluded from the plan in the first place.
        """
        selected: dict[str, SelectedTechnology] = {
            _normalize(s.name): SelectedTechnology(
                name=s.name, source=EvidenceSource.JOBSPEC, required=s.required
            )
            for s in job_spec.skills
        }
        if reliable:
            for ot in occupation.technologies:
                key = _normalize(ot.technology)
                if key in selected:
                    selected[key] = selected[key].model_copy(
                        update={
                            "source": EvidenceSource.BOTH,
                            "hot": ot.hot,
                            "in_demand": ot.in_demand,
                        }
                    )
        # Decide which technologies *survive* the cap using required-first priority, but keep
        # the returned list in JD order (recruiter-facing display, and the existing "the plan
        # never reorders the JD" contract - see interview_planner tests) - only *which* subset
        # makes it past `max_technologies`, not the order they're shown in, changes.
        prioritized = sorted(selected.values(), key=lambda t: 0 if t.required else 1)
        surviving = {_normalize(t.name) for t in prioritized[: self.max_technologies]}
        return [t for t in selected.values() if _normalize(t.name) in surviving]

    def _build_tasks(
        self, job_spec: JobSpec, occupation: OccupationRecord, reliable: bool
    ) -> list[SelectedTask]:
        """JD responsibilities only. O*NET may annotate (-> BOTH) an exact-text match only."""
        onet_task_keys = {_normalize(t) for t in occupation.core_tasks} if reliable else set()
        seen: set[str] = set()
        tasks: list[SelectedTask] = []
        for responsibility in job_spec.responsibilities:
            key = _normalize(responsibility)
            if key in seen:
                continue
            seen.add(key)
            source = EvidenceSource.BOTH if key in onet_task_keys else EvidenceSource.JOBSPEC
            tasks.append(SelectedTask(task=responsibility, source=source))
            if len(tasks) >= self.max_tasks:
                break
        return tasks

    def _build_onet_context(
        self,
        job_spec: JobSpec,
        occupation: OccupationRecord,
        reliable: bool,
        confident_for_tech_context: bool,
    ) -> str:
        """A short, relevance-filtered block of O*NET context for question phrasing only.

        Never returns a JD requirement - only supplementary material a question-phrasing LLM
        may use to add depth/realism. Returns ``""`` when the occupation match isn't reliable,
        or when nothing about it clears the relevance gates below: mentioning an occupation
        with nothing relevant to say about it risks nudging phrasing toward that occupation's
        domain for no reason, which is exactly what this function exists to prevent.
        """
        if not reliable:
            return ""

        existing_tech_keys = {_normalize(s.name) for s in job_spec.skills}
        relevant_technologies: list[str] = []
        if confident_for_tech_context:
            check_ubiquity = len(self.knowledge_base) >= _MIN_OCCUPATIONS_FOR_PREVALENCE_STAT
            for ot in occupation.technologies:
                if _normalize(ot.technology) in existing_tech_keys:
                    continue  # already a JD requirement - not new context
                if check_ubiquity and (
                    self.knowledge_base.technology_prevalence(ot.technology)
                    > _MAX_UBIQUITOUS_TECH_PREVALENCE
                ):
                    continue  # generic, near-universal tool - no real signal about this job
                relevant_technologies.append(ot.technology)
                if len(relevant_technologies) >= _MAX_CONTEXT_TECHNOLOGIES:
                    break

        existing_task_keys = {_normalize(r) for r in job_spec.responsibilities}
        relevant_tasks: list[str] = []
        for task in occupation.core_tasks:
            if _normalize(task) in existing_task_keys:
                continue  # already a JD responsibility - not new context
            if self.knowledge_base.relevance_to_jobspec(job_spec, task) < _MIN_TASK_RELEVANCE:
                continue  # a Core Task for the occupation, but not relevant to this JD
            relevant_tasks.append(task)
            if len(relevant_tasks) >= _MAX_CONTEXT_TASKS:
                break

        if not relevant_technologies and not relevant_tasks:
            return ""

        lines = [f"Matched occupation: {occupation.title}"]
        if relevant_technologies:
            lines.append("Relevant technologies for this occupation:")
            lines.extend(f"- {t}" for t in relevant_technologies)
        if relevant_tasks:
            lines.append("Relevant tasks for this occupation:")
            lines.extend(f"- {t}" for t in relevant_tasks)
        return "\n".join(lines)


#: Priority offset added to every preferred-tier target so it always sorts after every
#: required-tier one within the same category, regardless of how many required targets that
#: category has - see ``_build_coverage_targets``.
_PREFERRED_PRIORITY_OFFSET = 1000


def _build_coverage_targets(
    job_id: str,
    *,
    competencies: list[CompetencyCoverage],
    technologies: list[SelectedTechnology],
    tasks: list[SelectedTask],
) -> list[CoverageTarget]:
    """Flatten competencies/technologies/tasks into the interview graph's working list.

    Each target's ``priority`` alone is enough to prioritize required targets ahead of
    preferred ones within its own category (required: JD index; preferred: JD index +
    ``_PREFERRED_PRIORITY_OFFSET``) while preserving JD order within each tier - the exact
    "required before preferred, JD order otherwise" rule the old ``_prioritize_required`` used
    to apply only at question-generation time, now available to any interview-time selector
    without it needing to know about ``Skill.required`` at all, just ``priority``. Competencies
    and tasks have no required/preferred distinction in ``JobSpec`` - see ``RequirementLevel``'s
    docstring - so every one is ``REQUIRED`` with a plain JD-index priority.
    """
    targets: list[CoverageTarget] = []
    for index, c in enumerate(competencies):
        targets.append(
            CoverageTarget(
                id=_question_id(job_id, QuestionCategory.COMPETENCY, c.name),
                target=c.name,
                category=QuestionCategory.COMPETENCY,
                requirement_level=RequirementLevel.REQUIRED,
                source=c.source,
                priority=index,
                grounding=_competency_grounding(c),
            )
        )
    for index, t in enumerate(technologies):
        # `None` (no JD origin - shouldn't happen for technologies) counts as required.
        required = t.required is not False
        targets.append(
            CoverageTarget(
                id=_question_id(job_id, QuestionCategory.TECHNOLOGY, t.name),
                target=t.name,
                category=QuestionCategory.TECHNOLOGY,
                requirement_level=(
                    RequirementLevel.REQUIRED if required else RequirementLevel.PREFERRED
                ),
                source=t.source,
                priority=index if required else index + _PREFERRED_PRIORITY_OFFSET,
                grounding=_technology_grounding(t),
            )
        )
    for index, t in enumerate(tasks):
        targets.append(
            CoverageTarget(
                id=_question_id(job_id, QuestionCategory.TASK, t.task),
                target=t.task,
                category=QuestionCategory.TASK,
                requirement_level=RequirementLevel.REQUIRED,
                source=t.source,
                priority=index,
                grounding=_task_grounding(t),
            )
        )
    return targets


def _competency_grounding(competency: CompetencyCoverage) -> str:
    if competency.source is EvidenceSource.BOTH:
        return (
            f"Job description competency (also rated by the matched O*NET occupation, "
            f"importance {competency.onet_importance:.2f})"
        )
    return "Job description competency"


def _technology_grounding(technology: SelectedTechnology) -> str:
    if technology.source is EvidenceSource.BOTH:
        flag_pairs = (("hot", technology.hot), ("in_demand", technology.in_demand))
        flags = ", ".join(flag for flag, present in flag_pairs if present)
        flag_part = f" [{flags}]" if flags else ""
        return (
            "Job description technology (also listed by the matched O*NET occupation"
            f"{flag_part})"
        )
    return "Job description technology"


def _task_grounding(task: SelectedTask) -> str:
    if task.source is EvidenceSource.BOTH:
        return "Job description responsibility (also a core task for the matched O*NET occupation)"
    return "Job description responsibility"
