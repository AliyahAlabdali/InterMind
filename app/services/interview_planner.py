"""Interview planning use case: JobSpec -> O*NET occupation match -> structured InterviewPlan.

Pipeline: ``JobSpec -> match_jobspec (O*NET occupation) -> select competencies /
technologies / tasks -> generate grounded, role-specific questions -> InterviewPlan``.

Selection merges two evidence sources and keeps track of which:

- the JobSpec itself (what the job description said), and
- the matched O*NET occupation's signal (what O*NET says is typical for that occupation).

A name present in both is tagged ``EvidenceSource.BOTH`` and carries the O*NET rating
alongside; a name from only one source keeps that single provenance. Every selected
technology/task/competency traces back to a concrete piece of evidence (JobSpec text or a
specific O*NET occupation field) - nothing here is invented.
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


@dataclass
class InterviewPlannerService:
    """Builds an :class:`InterviewPlan` from a :class:`JobSpec`.

    Occupation matching uses :class:`OnetKnowledgeBase` (deterministic TF-IDF baseline - a
    retrieval proof-of-concept, not a validated classifier; see Milestone 2). Question text
    generation goes through :class:`QuestionGenerationService`, which uses the same
    provider-agnostic ``LLMClient`` boundary as JD analysis, so the fake provider needs no
    API credits and OpenAI/Azure OpenAI stay strictly optional.
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

        competencies = self._select_competencies(job_spec, occupation)
        technologies = self._select_technologies(job_spec, occupation)
        tasks = self._select_tasks(occupation)
        questions = await self._generate_questions(
            job_id=job_id,
            job_spec=job_spec,
            occupation=occupation,
            competencies=competencies,
            technologies=technologies,
            tasks=tasks,
        )

        return InterviewPlan(
            job_id=job_id,
            occupation_match=top_match,
            alternate_matches=alternates,
            competencies=competencies,
            technologies=technologies,
            tasks=tasks,
            questions=questions,
        )

    def _select_competencies(
        self, job_spec: JobSpec, occupation: OccupationRecord
    ) -> list[CompetencyCoverage]:
        selected: dict[str, CompetencyCoverage] = {}
        for c in job_spec.competencies:
            selected[_normalize(c.name)] = CompetencyCoverage(
                name=c.name, source=EvidenceSource.JOBSPEC
            )

        # O*NET competencies already arrive importance-ranked (see the Milestone 2 notebook);
        # preserve that order when filling remaining capacity.
        for oc in occupation.competencies:
            key = _normalize(oc.skill)
            if key in selected:
                existing = selected[key]
                selected[key] = existing.model_copy(
                    update={
                        "source": EvidenceSource.BOTH,
                        "onet_importance": oc.importance,
                        "onet_level": oc.level,
                    }
                )
            elif len(selected) < self.max_competencies:
                selected[key] = CompetencyCoverage(
                    name=oc.skill,
                    source=EvidenceSource.ONET,
                    onet_importance=oc.importance,
                    onet_level=oc.level,
                )
        return list(selected.values())[: self.max_competencies]

    def _select_technologies(
        self, job_spec: JobSpec, occupation: OccupationRecord
    ) -> list[SelectedTechnology]:
        selected: dict[str, SelectedTechnology] = {}
        for s in job_spec.skills:
            selected[_normalize(s.name)] = SelectedTechnology(
                name=s.name, source=EvidenceSource.JOBSPEC
            )

        # O*NET technologies already arrive ranked by the InterMind hot/in_demand heuristic
        # (see the Milestone 2 notebook, Section 5.2); preserve that order.
        for ot in occupation.technologies:
            key = _normalize(ot.technology)
            if key in selected:
                existing = selected[key]
                selected[key] = existing.model_copy(
                    update={
                        "source": EvidenceSource.BOTH,
                        "hot": ot.hot,
                        "in_demand": ot.in_demand,
                    }
                )
            elif len(selected) < self.max_technologies:
                selected[key] = SelectedTechnology(
                    name=ot.technology,
                    source=EvidenceSource.ONET,
                    hot=ot.hot,
                    in_demand=ot.in_demand,
                )
        return list(selected.values())[: self.max_technologies]

    def _select_tasks(self, occupation: OccupationRecord) -> list[SelectedTask]:
        seen: set[str] = set()
        tasks: list[SelectedTask] = []
        for t in occupation.core_tasks:
            key = _normalize(t)
            if key in seen:
                continue
            seen.add(key)
            tasks.append(SelectedTask(task=t, source=EvidenceSource.ONET))
            if len(tasks) >= self.max_tasks:
                break
        return tasks

    async def _generate_questions(
        self,
        *,
        job_id: str,
        job_spec: JobSpec,
        occupation: OccupationRecord,
        competencies: list[CompetencyCoverage],
        technologies: list[SelectedTechnology],
        tasks: list[SelectedTask],
    ) -> list[InterviewQuestion]:
        # (category, target name, grounding reference) for every question we want phrased.
        items: list[tuple[QuestionCategory, str, str]] = []
        for c in competencies[: self.competency_questions]:
            grounding = _competency_grounding(c, occupation)
            items.append((QuestionCategory.COMPETENCY, c.name, grounding))
        for t in technologies[: self.technology_questions]:
            grounding = _technology_grounding(t, occupation)
            items.append((QuestionCategory.TECHNOLOGY, t.name, grounding))
        for t in tasks[: self.task_questions]:
            grounding = f"O*NET {occupation.onet_soc_code}: core task"
            items.append((QuestionCategory.TASK, t.task, grounding))

        generated = await self.question_service.generate(
            role_title=job_spec.role_title,
            targets=[(category.value, name) for category, name, _ in items],
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


def _competency_grounding(competency: CompetencyCoverage, occupation: OccupationRecord) -> str:
    if competency.source is EvidenceSource.JOBSPEC:
        return "Job description competency (not in the matched O*NET occupation's skill list)"
    level_part = f", level {competency.onet_level:.2f}" if competency.onet_level is not None else ""
    return (
        f"O*NET {occupation.onet_soc_code} ({occupation.title}): skill "
        f"'{competency.name}' (importance {competency.onet_importance:.2f}{level_part})"
    )


def _technology_grounding(technology: SelectedTechnology, occupation: OccupationRecord) -> str:
    if technology.source is EvidenceSource.JOBSPEC:
        return "Job description skill (not in the matched O*NET occupation's technology list)"
    flag_pairs = (("hot", technology.hot), ("in_demand", technology.in_demand))
    flags = ", ".join(flag for flag, present in flag_pairs if present)
    flag_part = f" [{flags}]" if flags else ""
    return (
        f"O*NET {occupation.onet_soc_code} ({occupation.title}): "
        f"technology '{technology.name}'{flag_part}"
    )
