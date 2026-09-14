"""Deterministic, offline implementation of :class:`app.llm.ports.LLMClient`.

Used by the test suite and for local development without an API key
(``LLM_PROVIDER=fake``).
"""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from app.core.exceptions import LLMOutputInvalid
from app.domain.evaluation import AnswerEvaluation, EvaluationDecision
from app.domain.interview_plan import GeneratedQuestion, GeneratedQuestionSet
from app.domain.job import Competency, JobSpec, Seniority, Skill
from app.domain.report import ReportNarrative

T = TypeVar("T", bound=BaseModel)

_QUESTION_TEMPLATES = {
    "competency": "As a {role}, tell me about a time you demonstrated {target}.",
    "technology": "As a {role}, walk me through a project where you used {target} to solve a "
    "real problem.",
    "task": "As a {role}, how would you approach the following responsibility: {target}",
}
_DEFAULT_ROLE = "professional"


# --- Deterministic, offline JD "analysis" ---------------------------------------------------
#
# A single fixed JobSpec for every job description starves any downstream consumer (notably
# the O*NET TF-IDF matcher - see the Milestone 6 occupation-matching investigation) of real
# signal: every JD ends up producing the same query text, so matching quality collapses to
# whichever occupation happens to share the most words with the one fixed canned response.
# This performs small, deterministic keyword/phrase extraction directly over the actual
# ``input_text`` instead - still offline and dependency-free, but content-aware. It is a
# generic skill/competency vocabulary, not a per-role or per-occupation mapping: it never
# reasons about what occupation a title implies, only what literal terms appear in the text.

_ROLE_TITLE_MAX_LEN = 120

_SENIORITY_PATTERNS: list[tuple[Seniority, re.Pattern[str]]] = [
    (Seniority.PRINCIPAL, re.compile(r"\bprincipal\b", re.IGNORECASE)),
    (Seniority.LEAD, re.compile(r"\blead\b", re.IGNORECASE)),
    (Seniority.SENIOR, re.compile(r"\bsenior\b|\bsr\.?\b", re.IGNORECASE)),
    (Seniority.JUNIOR, re.compile(r"\bjunior\b|\bjr\.?\b", re.IGNORECASE)),
    (Seniority.INTERN, re.compile(r"\bintern(?:ship)?\b", re.IGNORECASE)),
    (Seniority.MID, re.compile(r"\bmid[\s-]?level\b", re.IGNORECASE)),
]

# Canonical skill/technology name -> pattern to look for in the JD text. Deliberately small
# and generic (a general software/ML slice plus a healthcare-domain slice, so two unrelated
# JDs demonstrably extract different signal) rather than an exhaustive taxonomy.
_SKILL_VOCAB: list[tuple[str, re.Pattern[str]]] = [
    ("Python", re.compile(r"\bpython\b", re.IGNORECASE)),
    ("Machine Learning", re.compile(r"\bmachine learning\b", re.IGNORECASE)),
    ("Deep Learning", re.compile(r"\bdeep learning\b", re.IGNORECASE)),
    ("PyTorch", re.compile(r"\bpytorch\b", re.IGNORECASE)),
    ("TensorFlow", re.compile(r"\btensorflow\b", re.IGNORECASE)),
    ("Computer Vision", re.compile(r"\bcomputer vision\b", re.IGNORECASE)),
    (
        "Natural Language Processing",
        re.compile(r"\bnatural language processing\b|\bnlp\b", re.IGNORECASE),
    ),
    ("Transformers", re.compile(r"\btransformers?\b", re.IGNORECASE)),
    ("ONNX", re.compile(r"\bonnx\b", re.IGNORECASE)),
    ("FastAPI", re.compile(r"\bfastapi\b", re.IGNORECASE)),
    ("REST APIs", re.compile(r"\brest\s*apis?\b|\brestful\b", re.IGNORECASE)),
    ("SQL", re.compile(r"\bsql\b", re.IGNORECASE)),
    ("Git", re.compile(r"\bgit\b", re.IGNORECASE)),
    ("Docker", re.compile(r"\bdocker\b", re.IGNORECASE)),
    ("Kubernetes", re.compile(r"\bkubernetes\b", re.IGNORECASE)),
    ("AWS", re.compile(r"\baws\b|\bamazon web services\b", re.IGNORECASE)),
    ("Java", re.compile(r"\bjava\b", re.IGNORECASE)),
    ("JavaScript", re.compile(r"\bjavascript\b", re.IGNORECASE)),
    ("C++", re.compile(r"\bc\+\+", re.IGNORECASE)),
    (
        "Electronic Health Records",
        re.compile(r"\belectronic health records?\b|\behr\b", re.IGNORECASE),
    ),
    (
        "Healthcare Data Management",
        re.compile(r"\bhealthcare data management\b", re.IGNORECASE),
    ),
    (
        "Clinical Information Systems",
        re.compile(r"\bclinical information systems?\b", re.IGNORECASE),
    ),
    (
        "Health Information Technology",
        re.compile(r"\bhealth information technology\b", re.IGNORECASE),
    ),
    ("Data Analysis", re.compile(r"\bdata analysis\b", re.IGNORECASE)),
]

# Canonical competency name -> pattern. Behavioural/soft-skill phrasing, kept separate from
# the skill vocabulary above since these map to JobSpec.competencies, not JobSpec.skills.
_COMPETENCY_VOCAB: list[tuple[str, re.Pattern[str]]] = [
    ("Problem Solving", re.compile(r"\bproblem[\s-]solving\b", re.IGNORECASE)),
    ("Analytical Thinking", re.compile(r"\banalytical\b", re.IGNORECASE)),
    ("Collaboration", re.compile(r"\bcollaborat\w*\b", re.IGNORECASE)),
    ("Communication", re.compile(r"\bcommunicat\w*\b", re.IGNORECASE)),
    ("Mentoring", re.compile(r"\bmentor\w*\b", re.IGNORECASE)),
    ("Leadership", re.compile(r"\bleadership\b", re.IGNORECASE)),
]

# A "Preferred"/"Nice to have"-style heading marks everything after it as not-required,
# mirroring the real jd_analysis prompt's own required/preferred rule.
_PREFERRED_SECTION = re.compile(r"(?im)^\s*preferred\b")


def _detect_seniority(text: str) -> Seniority:
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(text):
            return level
    return Seniority.UNKNOWN


def _extract_skills(text: str) -> list[Skill]:
    """Find known skill/technology names present in ``text``, in vocabulary order.

    Vocabulary order (not order-of-appearance) keeps this fully deterministic regardless of
    how a JD happens to be phrased.
    """
    preferred_match = _PREFERRED_SECTION.search(text)
    preferred_offset = preferred_match.start() if preferred_match else len(text)
    skills = []
    for name, pattern in _SKILL_VOCAB:
        match = pattern.search(text)
        if match is None:
            continue
        skills.append(Skill(name=name, required=match.start() < preferred_offset))
    return skills


def _extract_competencies(text: str) -> list[Competency]:
    return [Competency(name=name) for name, pattern in _COMPETENCY_VOCAB if pattern.search(text)]


def _fake_summary(role_title: str, seniority: Seniority, skills: list[Skill]) -> str:
    detail = f" covering {', '.join(s.name for s in skills[:6])}" if skills else ""
    level = f"{seniority.value} " if seniority != Seniority.UNKNOWN else ""
    return f"Deterministic fake analysis of a {level}{role_title} role{detail}."


def _fake_analyze_job(input_text: str) -> JobSpec:
    """Deterministic, offline stand-in for a real JD-analysis LLM call.

    Extracts the role title (first non-blank line - unchanged from before), seniority, and
    known skill/competency vocabulary directly from ``input_text``, so different job
    descriptions deterministically produce different ``JobSpec``s instead of one fixed canned
    response.
    """
    role_title = next(
        (line.strip() for line in input_text.splitlines() if line.strip()),
        "Unknown Role",
    )[:_ROLE_TITLE_MAX_LEN]
    seniority = _detect_seniority(input_text)
    skills = _extract_skills(input_text)
    competencies = _extract_competencies(input_text)
    return JobSpec(
        role_title=role_title,
        seniority=seniority,
        skills=skills,
        competencies=competencies,
        summary=_fake_summary(role_title, seniority, skills),
    )


def _fake_generate_questions(input_text: str) -> GeneratedQuestionSet:
    """Deterministically template one question per ``CATEGORY: target`` line.

    Expects the format produced by :class:`app.services.question_generation.
    QuestionGenerationService`: a ``ROLE:`` line followed by one ``COMPETENCY:``/
    ``TECHNOLOGY:``/``TASK:`` line per target. The role title is folded into every question's
    text (so two different roles deterministically produce different question text for the
    same target), not just parsed and discarded. Unrecognised lines are skipped rather than
    raising, so this stays robust to minor prompt/format drift.
    """
    role = _DEFAULT_ROLE
    questions = []
    for line in input_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("ROLE:"):
            _, _, role_value = line.partition(":")
            role_value = role_value.strip()
            if role_value:
                role = role_value
            continue
        category, _, name = line.partition(":")
        category = category.strip().lower()
        name = name.strip()
        template = _QUESTION_TEMPLATES.get(category)
        if not name or template is None:
            continue
        text = template.format(role=role, target=name)
        questions.append(GeneratedQuestion(category=category, target=name, text=text))
    return GeneratedQuestionSet(questions=questions)


def _fake_evaluate_answer(input_text: str) -> AnswerEvaluation:
    """Deterministically score by answer length: >=8 words advances, otherwise follow-up.

    Mirrors the word-count heuristic that used to live directly in
    :mod:`app.agents.interview_graph`, so replacing it with the real LLM evaluator does not
    change fake-client-backed test behaviour. Expects the ``QUESTION:``/``CATEGORY:``/
    ``TARGET:``/``GROUNDING:``/``ANSWER:`` format produced by
    :class:`app.services.answer_evaluation.AnswerEvaluationService`.
    """
    target = "the target"
    answer = ""
    for line in input_text.splitlines():
        line = line.strip()
        if line.upper().startswith("TARGET:"):
            _, _, value = line.partition(":")
            target = value.strip() or target
        elif line.upper().startswith("ANSWER:"):
            _, _, value = line.partition(":")
            answer = value.strip()

    if len(answer.split()) >= 8:
        return AnswerEvaluation(
            score=0.8,
            decision=EvaluationDecision.ADVANCE,
            strengths=[f"Answer gives concrete detail about {target}."],
            weaknesses=[],
            evidence=[answer[:200]],
            follow_up_needed=False,
        )

    return AnswerEvaluation(
        score=0.3,
        decision=EvaluationDecision.FOLLOW_UP,
        strengths=[],
        weaknesses=[f"Answer lacks detail or a concrete example for {target}."],
        evidence=[answer[:200]] if answer else [],
        follow_up_needed=True,
        follow_up_question=f"Can you give a specific example related to {target}?",
    )


def _fake_generate_report_narrative(input_text: str) -> ReportNarrative:
    """Deterministically echo back only the strengths/weaknesses already given.

    Never invents a claim: every string in the returned lists came verbatim from a
    ``STRENGTHS:``/``WEAKNESSES:`` line in ``input_text`` (built by
    :class:`app.services.report_narrative.ReportNarrativeService` from already-computed,
    evidence-based :class:`~app.domain.report.CompetencyAssessment` data). The summary is a
    templated sentence over the given ``OVERALL_SCORE:``/``RECOMMENDATION:`` and how many
    ``COMPETENCY:`` blocks were given - not a fabricated assessment.
    """
    overall_score = "0.00"
    recommendation = "consider"
    competency_count = 0
    strengths: list[str] = []
    weaknesses: list[str] = []

    for line in input_text.splitlines():
        line = line.strip()
        if line.upper().startswith("OVERALL_SCORE:"):
            overall_score = line.partition(":")[2].strip()
        elif line.upper().startswith("RECOMMENDATION:"):
            recommendation = line.partition(":")[2].strip()
        elif line.upper().startswith("COMPETENCY:"):
            competency_count += 1
        elif line.upper().startswith("STRENGTHS:"):
            value = line.partition(":")[2].strip()
            if value and value != "(none)":
                strengths.extend(item.strip() for item in value.split(";") if item.strip())
        elif line.upper().startswith("WEAKNESSES:"):
            value = line.partition(":")[2].strip()
            if value and value != "(none)":
                weaknesses.extend(item.strip() for item in value.split(";") if item.strip())

    plural = "y" if competency_count == 1 else "ies"
    summary = (
        f"Deterministic evaluation across {competency_count} competenc{plural} yielded an "
        f"overall score of {overall_score} ({recommendation})."
    )
    return ReportNarrative(
        summary=summary,
        strengths=_dedupe(strengths),
        weaknesses=_dedupe(weaknesses),
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class FakeLLMClient:
    """Returns a fixed response, either a caller-supplied one or a canned default."""

    def __init__(self, response: BaseModel | None = None) -> None:
        self._response = response

    async def generate_structured(
        self,
        *,
        prompt: str,
        input_text: str,
        schema: type[T],
    ) -> T:
        if self._response is not None:
            if not isinstance(self._response, schema):
                raise LLMOutputInvalid(
                    f"Configured fake response is {type(self._response).__name__}, "
                    f"expected {schema.__name__}"
                )
            return self._response

        if schema is JobSpec:
            return schema.model_validate(_fake_analyze_job(input_text))

        if schema is GeneratedQuestionSet:
            return _fake_generate_questions(input_text)

        if schema is AnswerEvaluation:
            return _fake_evaluate_answer(input_text)

        if schema is ReportNarrative:
            return _fake_generate_report_narrative(input_text)

        raise LLMOutputInvalid(
            f"FakeLLMClient has no canned response for schema {schema.__name__}"
        )
