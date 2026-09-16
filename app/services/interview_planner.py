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
                                O*NET matching -> relevant O*NET context
                                       |
                                Question Generation
                                       |
                                Interview Questions

``InterviewPlan.competencies``/``technologies``/``tasks`` are always built from the JobSpec
alone (``EvidenceSource.JOBSPEC``, or ``BOTH`` when the matched occupation happens to rate the
same name too - see each model's docstring in ``app.domain.interview_plan``). O*NET is never
the source of a *new* competency/technology/task: it cannot silently add a candidate
requirement the job description never stated. What O*NET *can* do is supply relevant
occupational context - the matched occupation's title/description plus a handful of its own
technologies/tasks that are actually relevant to this JobSpec - to the question-generation
step, so questions can be phrased with more depth/realism. See ``_build_onet_context``.

Two independent relevance gates decide what, if anything, ends up in that context, reusing the
same signals this module already computed for the (now-retired) "inject into the plan" design:
``_match_is_reliable`` decides whether the matched *occupation* is trusted at all; corpus-wide
technology prevalence (``OnetKnowledgeBase.technology_prevalence``) and per-task relevance to
the JobSpec (``OnetKnowledgeBase.relevance_to_jobspec``) decide, per candidate item, whether
that specific piece of O*NET content is worth mentioning as context. Nothing here is hard-coded
to a technology, task, or occupation name - the gates are purely statistical/relevance-based.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.core.exceptions import NoOccupationMatch
from app.domain.interview_plan import (
    CompetencyCoverage,
    EvidenceSource,
    InterviewPlan,
    InterviewQuestion,
    QuestionCategory,
    SelectedTask,
    SelectedTechnology,
)
from app.domain.job import JobSpec
from app.domain.occupation import OccupationRecord
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.services.question_generation import QuestionGenerationService
from app.services.text_normalize import normalize_name as _normalize


def _question_id(job_id: str, category: QuestionCategory, target: str) -> str:
    """Stable id for a (job, category, target) slot.

    Deterministic (not a fresh ``uuid4()``) so rebuilding the same plan from the same JobSpec
    and the same knowledge-base signals always produces the same question ids in the same
    order - the identity a later stateful interview loop (Milestone 4) would reference stays
    valid even if the plan is recomputed, and is independent of the phrased question text
    itself (which may legitimately vary between LLM providers/calls).
    """
    key = f"{job_id}|{category.value}|{_normalize(target)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


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
    retrieval proof-of-concept, not a validated classifier; see Milestone 2). Question text
    generation goes through :class:`QuestionGenerationService`, which uses the same
    provider-agnostic ``LLMClient`` boundary as JD analysis, so the fake provider needs no
    API credits and OpenAI/Azure OpenAI stay strictly optional.

    The job description is the *only* source of plan competencies/technologies/tasks (see the
    module docstring). The matched O*NET occupation contributes, at most, a short relevance
    -filtered context block passed to question generation - never a new plan entry.
    """

    knowledge_base: OnetKnowledgeBase
    question_service: QuestionGenerationService
    top_k_matches: int = 5
    max_competencies: int = 8
    max_technologies: int = 8
    max_tasks: int = 5
    competency_questions: int = 4
    technology_questions: int = 4
    task_questions: int = 2

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
        questions = await self._generate_questions(
            job_id=job_id,
            job_spec=job_spec,
            competencies=competencies,
            technologies=technologies,
            tasks=tasks,
            onet_context=onet_context,
        )

        return InterviewPlan(
            job_id=job_id,
            occupation_match=top_match,
            alternate_matches=alternates,
            onet_grounding_used=bool(onet_context),
            competencies=competencies,
            technologies=technologies,
            tasks=tasks,
            questions=questions,
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
        """JD technologies only. O*NET may annotate (-> BOTH) an existing one, never add one."""
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
        return list(selected.values())[: self.max_technologies]

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

    async def _generate_questions(
        self,
        *,
        job_id: str,
        job_spec: JobSpec,
        competencies: list[CompetencyCoverage],
        technologies: list[SelectedTechnology],
        tasks: list[SelectedTask],
        onet_context: str,
    ) -> list[InterviewQuestion]:
        # (category, target name, grounding reference) for every question we want phrased.
        # Every target here comes from the JobSpec - O*NET context (below) enriches phrasing
        # only, and is never itself a target a question must be generated for.
        items: list[tuple[QuestionCategory, str, str]] = []
        for c in competencies[: self.competency_questions]:
            items.append((QuestionCategory.COMPETENCY, c.name, _competency_grounding(c)))
        for t in technologies[: self.technology_questions]:
            items.append((QuestionCategory.TECHNOLOGY, t.name, _technology_grounding(t)))
        for t in tasks[: self.task_questions]:
            items.append((QuestionCategory.TASK, t.task, _task_grounding(t)))

        generated = await self.question_service.generate(
            role_title=job_spec.role_title,
            targets=[(category.value, name) for category, name, _ in items],
            onet_context=onet_context,
        )
        text_by_target = {
            (g.category.strip().lower(), _normalize(g.target)): g.text.strip()
            for g in generated.questions
        }

        questions: list[InterviewQuestion] = []
        seen_text: set[str] = set()
        for category, name, grounding in items:
            text = text_by_target.get((category.value, _normalize(name)))
            if not text:
                continue
            norm_text = _normalize(text)
            if norm_text in seen_text:
                continue  # avoid duplicate/redundant questions
            seen_text.add(norm_text)
            questions.append(
                InterviewQuestion(
                    id=_question_id(job_id, category, name),
                    category=category,
                    text=text,
                    target=name,
                    grounding=grounding,
                )
            )
        return questions


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
