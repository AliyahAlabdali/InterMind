"""Deterministic, offline implementation of :class:`app.llm.ports.LLMClient`.

Used by the test suite and for local development without an API key
(``LLM_PROVIDER=fake``).
"""

from __future__ import annotations

import hashlib
import re
from typing import TypeVar

from pydantic import BaseModel

from app.core.exceptions import LLMOutputInvalid
from app.domain.evaluation import (
    AnswerEvaluation,
    AnswerEvidenceType,
    CrossTargetEvidence,
    EvaluationDecision,
)
from app.domain.interview_plan import GeneratedQuestion, GeneratedQuestionSet
from app.domain.job import Competency, JobSpec, Seniority, Skill
from app.domain.report import ReportNarrative

T = TypeVar("T", bound=BaseModel)

# Deliberately not a single rigid "As a {role}, tell me about a time you demonstrated
# {target}." template: that literal construction (and the raw competency-name-drop) reads as
# an obvious fill-in-the-blank to a candidate. Several natural-language variants per category,
# chosen deterministically per (category, target) via `_variant_index` below, so the same
# request always phrases the same way (test determinism) while different targets in the same
# plan don't all read identically. Still a generic, offline, no-LLM approximation - it cannot
# infer true domain-specific verbs (e.g. "marketing campaign" vs "backend service") the way a
# real LLM does with the `interview_questions_v1.md` prompt; it only weaves in the role title
# text itself, which for most JDs already carries the domain word.
_COMPETENCY_QUESTION_TEMPLATES = [
    "Tell me about a specific time {target_lower} mattered in your work as a {role}. What was "
    "the situation, and what did you do?",
    "Describe a project or moment from your experience as a {role} where {target_lower} made a "
    "real difference. What was the outcome?",
    "Walk me through a situation where you had to rely on {target_lower} as a {role}. What "
    "approach did you take, and how did it turn out?",
]
_TECHNOLOGY_QUESTION_TEMPLATES = [
    "Tell me about a project where you used {target} as a {role}. What problem were you "
    "solving, and what tradeoffs did you make?",
    "Walk me through how you've applied {target} in your work as a {role}. What challenges "
    "came up, and how did you handle them?",
    "Describe a time {target} was central to something you built or maintained as a {role}. "
    "What was the result?",
]
_TASK_QUESTION_TEMPLATES = [
    'One of the responsibilities for this role is: "{target}" How would you approach this as '
    "a {role}, and what would you prioritize first?",
    'This role involves the following: "{target}" Walk me through how you would handle that '
    "as a {role}.",
]
_DEFAULT_ROLE = "professional"


def _variant_index(key: str, count: int) -> int:
    """Deterministic 0..count-1 index for ``key`` (stable across processes/runs)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % count


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
    ("Critical Thinking", re.compile(r"\bcritical\s*thinking\b", re.IGNORECASE)),
    ("Analytical Thinking", re.compile(r"\banalytical\b", re.IGNORECASE)),
    ("Collaboration", re.compile(r"\bcollaborat\w*\b|\bteam\s*work\b", re.IGNORECASE)),
    ("Communication", re.compile(r"\bcommunicat\w*\b", re.IGNORECASE)),
    ("Mentoring", re.compile(r"\bmentor\w*\b", re.IGNORECASE)),
    ("Leadership", re.compile(r"\bleadership\b", re.IGNORECASE)),
]

# A "Preferred"/"Nice to have"-style heading marks everything after it as not-required,
# mirroring the real jd_analysis prompt's own required/preferred rule.
_PREFERRED_SECTION = re.compile(r"(?im)^\s*preferred\b")

# A JD's "Responsibilities"/"Duties" section header, and the headers of sections that follow
# it (which mark where the responsibilities list ends). Generic section-heading vocabulary,
# not tied to any specific role.
_RESPONSIBILITY_SECTION_HEADER = re.compile(
    r"(?im)^\s*(?:key\s+)?(?:responsibilities|duties|what\s+you.?ll\s+do)\s*:?\s*$"
)
_NEXT_SECTION_HEADER = re.compile(
    r"(?im)^\s*(?:requirements?|preferred|qualifications?|nice\s+to\s+have|"
    r"(?:required|desired)\s+skills?|about\s+you|benefits?)\s*:?\s*$"
)
_BULLET_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(\S.*)$")

# Many pasted JDs open with a labelled header line ("Job Title: X", "Position: X", "Role: X")
# rather than the bare title itself. Strip the label so the extracted role_title is just "X" -
# otherwise it leaks verbatim into every downstream question (e.g. "As a Job Title: Digital
# Marketing Specialist, ...").
_ROLE_TITLE_LABEL = re.compile(
    r"^\s*(?:job\s*title|job|title|position|role)\s*[:\-]\s*", re.IGNORECASE
)

# A JD sometimes opens directly with a full sentence instead of a standalone title line (e.g.
# "We are looking for AI Engineer, she must have ..." all on one line) - without this, "first
# non-blank line" swallows the entire paragraph as the role title. Generic hiring-intro phrases,
# not tied to any specific role name.
_ROLE_INTRO_PHRASE = re.compile(
    r"\bwe(?:'re| are)\s+(?:currently\s+)?(?:looking\s+for|seeking|hiring(?:\s+for)?)\s+|"
    r"\bwe\s+(?:currently\s+)?need\s+|"
    r"\bwe(?:'re| are)\s+in\s+need\s+of\s+",
    re.IGNORECASE,
)
_LEADING_ARTICLE = re.compile(r"^(?:an?|the)\s+", re.IGNORECASE)

# Where a role title extracted from a sentence (rather than a standalone line) should end: the
# first clause boundary - punctuation, or a relative/continuation clause ("who will...", "to
# design...", "she must...", "and will..."). Whichever comes first wins.
_TITLE_CLAUSE_END = re.compile(
    r"[,.;:]|\b(?:who|that|which|to|and)\b|\b(?:she|he|they|it|you)\s+\w+", re.IGNORECASE
)

_MAX_STANDALONE_TITLE_WORDS = 7
_MAX_STANDALONE_TITLE_CHARS = 80


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


def _looks_like_standalone_title(line: str) -> bool:
    """Whether ``line`` is short and clause-free enough to trust as a title verbatim.

    A bare title line ("AI Engineer", "Senior Backend Software Engineer") has no internal
    clause breaks; a sentence ("We are looking for AI Engineer, she must have...") does, and/or
    runs long - either is a sign this line is prose, not a title, and needs the phrase/clause
    extraction in `_extract_role_title` instead of being used as-is.
    """
    if not line or len(line) > _MAX_STANDALONE_TITLE_CHARS:
        return False
    if len(line.split()) > _MAX_STANDALONE_TITLE_WORDS:
        return False
    return _TITLE_CLAUSE_END.search(line) is None


def _extract_role_title(input_text: str) -> str:
    """Extract a concise role title, never an entire sentence/paragraph.

    Tries, in order: (1) an explicit label ("Job Title:"/"Position:"/"Role:"), (2) the first
    line as-is if it already looks like a standalone title, (3) a generic hiring-intro phrase
    ("We are looking for ...", "We are seeking ...", "We need a/an ...") which may appear
    anywhere in a JD that opens directly with a sentence rather than a title line, cut at the
    first clause boundary, and (4) as a last resort, the first clause of the first line rather
    than the whole thing. Generic throughout - no role name is hard-coded.
    """
    first_line = next((line.strip() for line in input_text.splitlines() if line.strip()), "")
    if not first_line:
        return "Unknown Role"

    labeled = _ROLE_TITLE_LABEL.sub("", first_line).strip()
    if labeled != first_line:
        return (labeled or "Unknown Role")[:_ROLE_TITLE_MAX_LEN]

    if _looks_like_standalone_title(first_line):
        return first_line[:_ROLE_TITLE_MAX_LEN]

    intro_match = _ROLE_INTRO_PHRASE.search(first_line)
    if intro_match:
        remainder = _LEADING_ARTICLE.sub("", first_line[intro_match.end() :])
        end_match = _TITLE_CLAUSE_END.search(remainder)
        candidate = (remainder[: end_match.start()] if end_match else remainder).strip(" .,;:-")
        if candidate:
            return candidate[:_ROLE_TITLE_MAX_LEN]

    end_match = _TITLE_CLAUSE_END.search(first_line)
    fallback = (first_line[: end_match.start()] if end_match else first_line).strip(" .,;:-")
    return (fallback or "Unknown Role")[:_ROLE_TITLE_MAX_LEN]


def _extract_responsibilities(text: str) -> list[str]:
    """Pull the bullet list under a "Responsibilities"/"Duties" section header, if any.

    Generic section-header/bullet detection, not tied to any specific JD's wording. A bullet
    that wraps onto an indented continuation line (no marker of its own) is joined back onto
    the previous item rather than dropped. Returns `[]` when the JD has no such section (e.g.
    a short, unstructured JD) - responsibilities are only ever what the JD actually states.
    """
    lines = text.splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if _RESPONSIBILITY_SECTION_HEADER.match(line)), None
    )
    if header_idx is None:
        return []

    items: list[str] = []
    for line in lines[header_idx + 1 :]:
        if _NEXT_SECTION_HEADER.match(line):
            break
        if not line.strip():
            continue
        bullet = _BULLET_LINE.match(line)
        if bullet:
            items.append(bullet.group(1).strip())
        elif items and line[:1].isspace():
            items[-1] = f"{items[-1]} {line.strip()}".strip()
        else:
            break
    return items


def _fake_summary(role_title: str, seniority: Seniority, skills: list[Skill]) -> str:
    detail = f" covering {', '.join(s.name for s in skills[:6])}" if skills else ""
    level = f"{seniority.value} " if seniority != Seniority.UNKNOWN else ""
    return f"Deterministic fake analysis of a {level}{role_title} role{detail}."


def _fake_analyze_job(input_text: str) -> JobSpec:
    """Deterministic, offline stand-in for a real JD-analysis LLM call.

    Extracts the role title, seniority, and known skill/competency vocabulary, plus any stated
    responsibilities, directly from ``input_text``, so different job descriptions
    deterministically produce different ``JobSpec``s instead of one fixed canned response.
    """
    role_title = _extract_role_title(input_text)
    seniority = _detect_seniority(input_text)
    skills = _extract_skills(input_text)
    competencies = _extract_competencies(input_text)
    responsibilities = _extract_responsibilities(input_text)
    return JobSpec(
        role_title=role_title,
        seniority=seniority,
        skills=skills,
        competencies=competencies,
        responsibilities=responsibilities,
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
        if not name or category not in ("competency", "technology", "task"):
            continue

        templates = {
            "competency": _COMPETENCY_QUESTION_TEMPLATES,
            "technology": _TECHNOLOGY_QUESTION_TEMPLATES,
            "task": _TASK_QUESTION_TEMPLATES,
        }[category]
        template = templates[_variant_index(f"{category}|{name}", len(templates))]
        # Competency names are generic behavioural nouns ("Leadership", "Critical Thinking")
        # that read naturally fully lowercased mid-sentence. Technology names are proper
        # nouns/product names ("FastAPI", "AWS") and must keep their given casing - their
        # templates use `{target}`, not `{target_lower}`, so this value is unused for them.
        target_lower = name.lower() if category == "competency" else name
        text = template.format(role=role, target=name, target_lower=target_lower)
        questions.append(GeneratedQuestion(category=category, target=name, text=text))
    return GeneratedQuestionSet(questions=questions)


def _clean_target_phrase(target: str, *, category: str) -> str:
    """Trailing-punctuation-stripped form of ``target`` for embedding mid-sentence.

    A task's ``target`` is a full O*NET task sentence that already ends in ``.`` -
    interpolating it as-is directly before a template's own closing period produced a visible
    ".." (see the Milestone report-quality review); stripping trailing punctuation fixes that
    for every category, not just tasks. Casing then depends on what kind of name it is:
    competency names are generic behavioural nouns ("Leadership") that read naturally fully
    lowercased, while technology names are proper nouns/product names ("FastAPI", "AWS") whose
    casing must be preserved exactly.
    """
    text = target.strip().rstrip(".")
    if not text:
        return text
    return text.lower() if category == "competency" else text


# --- Deterministic, offline answer classification -------------------------------------------
#
# Milestone review finding: a pure word-count heuristic ("<8 words = follow_up, >=8 = advance")
# treats "I don't know anything about Python, is that a snake?" (10 words) as strong evidence,
# because it never looks at what the words actually say - only how many there are. The target
# name is context for what to assess, never evidence that the candidate demonstrated it. This
# classifies the answer's actual content into one of `AnswerEvidenceType`'s buckets before
# scoring anything - a non-substantive answer (explicit lack, confused/off-topic, claimed but
# unverified, or contradictory) short-circuits with its own type-specific weakness text, rather
# than falling through to the same generic word-count/action-verb scoring every other answer
# gets (see `_classify_evidence`, checked first in `_fake_evaluate_answer`).

# Evidence-type classification cues, deliberately generic (never keyed to a specific
# technology/competency name - see AnswerEvidenceType's docstring for why these buckets must
# not collapse into one another). Checked in priority order in `_classify_evidence` below:
# contradiction first (most specific - a naive explicit-lack/action-verb scan would otherwise
# misfile it), then explicit denial, then confusion/off-topic, then claimed-but-unverified.

# The candidate asserts having the experience, then denies it in the same answer - internally
# inconsistent, checked first so it isn't swallowed by the (also-matching) explicit-lack cues.
_CONTRADICTION_PATTERN = re.compile(
    r"\b(?:i\s+have|i'?ve|i\s+possess|i\s+know)\b.{0,80}\b(?:but|however|although|yet)\b"
    r".{0,80}\b(?:never|haven'?t|have not|don'?t|do not|dont|no)\b",
    re.IGNORECASE,
)

# The candidate explicitly states they lack the experience, have never used it, or names only a
# different technology/skill in a way that implies they lack the asked-about one.
_EXPLICIT_LACK_PATTERNS = [
    re.compile(r"\bnever\s+(?:used|worked with|done|touched|written)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:haven'?t|have not)\s+(?:used|worked with|done|touched|written)\b", re.IGNORECASE
    ),
    re.compile(r"\bno\s+experience\b", re.IGNORECASE),
    re.compile(r"\bnot\s+familiar\b", re.IGNORECASE),
    re.compile(r"\b(?:don'?t|do not|dont)\s+have\s+experience\b", re.IGNORECASE),
    re.compile(
        r"\b(?:don'?t|do not|dont)\s+have\s+(?:any\s+)?(?:\w+\s+){0,3}projects?\b", re.IGNORECASE
    ),
    re.compile(r"\bonly\s+(?:used|use|have used|worked with|know|known)\b", re.IGNORECASE),
]

# Off-topic/confused/vague-denial cues - the candidate answered, but not in a way that asserts
# (or denies) real experience one way or the other.
_CONFUSION_PATTERNS = [
    re.compile(r"\bi\s+(?:don'?t|do not|dont)\s+know\b", re.IGNORECASE),
    re.compile(r"\bknows?\s+nothing\b", re.IGNORECASE),
    re.compile(r"\bno\s+idea\b", re.IGNORECASE),
    re.compile(r"\bis\s+\w+\s+a\s+\w+", re.IGNORECASE),  # "is Python a snake?"
    re.compile(r"\bwhat\s+is\s+\w+.*\?", re.IGNORECASE),  # "what is Python?"
]

# The candidate claims/attempts to answer but can't recall or verify enough to substantiate it -
# e.g. "I don't remember the frameworks, but I remember my projects used MATLAB and C++" (asked
# about Java): never the same claim as explicit lack (the candidate never denied the
# experience, only failed to substantiate it) - see AnswerEvidenceType's docstring.
_CLAIMED_UNVERIFIED_PATTERNS = [
    re.compile(
        r"\bi\s+(?:don'?t|do not|dont|can'?t|cannot)\s+(?:remember|recall)\b", re.IGNORECASE
    ),
    re.compile(r"\bdon'?t\s+recall\b", re.IGNORECASE),
    re.compile(r"\bnot\s+sure\s+(?:of|about)\s+the\s+(?:details|specifics|exact)\b", re.IGNORECASE),
    re.compile(r"\bforget\s+the\s+(?:details|specifics|exact)\b", re.IGNORECASE),
    re.compile(r"\bit'?s\s+been\s+a\s+while\b", re.IGNORECASE),
]

# Backward-compatible alias: some call sites/tests may still refer to "no evidence" generically
# meaning "explicit lack or confusion" - both bundled together for the short-circuit check.
_NO_EVIDENCE_PATTERNS = _EXPLICIT_LACK_PATTERNS + _CONFUSION_PATTERNS

# Action verbs (a few common inflections each) whose presence signals a *described activity*
# rather than a bare claim - "I have ten years of experience" has none of these; "I built a
# service and fixed a bug" has two.
_ACTION_VERBS = [
    "built", "build", "building",
    "implemented", "implement", "implementing",
    "designed", "design", "designing",
    "created", "create", "creating",
    "led", "leading",
    "wrote", "write", "writing",
    "fixed", "fix", "fixing",
    "debugged", "debug", "debugging",
    "diagnosed", "diagnose", "diagnosing",
    "tested", "testing",
    "verified", "verify", "verifying",
    "deployed", "deploy", "deploying",
    "migrated", "migrate", "migrating",
    "refactored", "refactor", "refactoring",
    "automated", "automate", "automating",
    "developed", "develop", "developing",
    "managed", "manage", "managing",
    "coordinated", "coordinate", "coordinating",
    "mentored", "mentor", "mentoring",
    "launched", "launch", "launching",
    "architected", "architect",
    "integrated", "integrate", "integrating",
    "configured", "configure", "configuring",
    "resolved", "resolve", "resolving",
    "investigated", "investigate", "investigating",
    "analyzed", "analyze", "analyzing",
    "owned", "own", "owning",
    "shipped", "ship", "shipping",
    "optimized", "optimize", "optimizing",
    "noticed", "notice", "noticing",
    "found", "find", "finding",
    "discovered", "discover", "discovering",
    "identified", "identify", "identifying",
    "tracked", "track", "tracking",
    "traced", "trace", "tracing",
    "added", "add", "adding",
    "removed", "remove", "removing",
    "updated", "update", "updating",
    "reviewed", "review", "reviewing",
    "reported", "report", "reporting",
    "measured", "measure", "measuring",
    "monitored", "monitor", "monitoring",
    "reproduced", "reproduce", "reproducing",
    "solved", "solve", "solving",
    "handled", "handle", "handling",
    "reduced", "reduce", "reducing",
    "increased", "increase", "increasing",
]
_ACTION_VERB_PATTERN = re.compile(
    r"\b(?:" + "|".join(_ACTION_VERBS) + r")\b", re.IGNORECASE
)

# Content patterns used only to pick a *follow-up angle* grounded in what the candidate
# actually described - never the target/competency name itself.
_PERFORMANCE_PATTERN = re.compile(
    r"\b(reduced|decreased|improved|optimi[sz]ed|increased|sped up|faster|latency|"
    r"performance|response time|bottleneck)\b",
    re.IGNORECASE,
)
_BUILD_PATTERN = re.compile(
    r"\b(built|build|designed|design|implemented|implement|architected|created|create)\b",
    re.IGNORECASE,
)
_LEADERSHIP_PATTERN = re.compile(
    r"\b(led|lead|coordinated|coordinate|mentored|mentor|managed|manage)\b", re.IGNORECASE
)

_MIN_SUBSTANTIVE_WORDS = 12
_MIN_THOROUGH_WORDS = 20
_MIN_THOROUGH_VERBS = 3


def _is_no_evidence(answer: str) -> bool:
    return any(pattern.search(answer) for pattern in _NO_EVIDENCE_PATTERNS)


def _classify_evidence(answer: str) -> AnswerEvidenceType | None:
    """Classify ``answer`` into one of the non-substantive :class:`AnswerEvidenceType` buckets,
    or ``None`` if it doesn't match any of them (the caller then falls back to the word-count/
    action-verb bands for ``partial``/``demonstrated``/``insufficient``-by-brevity).

    Checked in priority order: contradiction is checked first because its own cue phrases (an
    affirmative claim followed by a negation) would otherwise also trip the explicit-lack
    patterns below on their negation half alone, misfiling a genuinely contradictory answer as a
    clean denial.
    """
    if _CONTRADICTION_PATTERN.search(answer):
        return AnswerEvidenceType.CONTRADICTORY
    if any(pattern.search(answer) for pattern in _EXPLICIT_LACK_PATTERNS):
        return AnswerEvidenceType.EXPLICIT_LACK
    if any(pattern.search(answer) for pattern in _CONFUSION_PATTERNS):
        return AnswerEvidenceType.INSUFFICIENT
    if any(pattern.search(answer) for pattern in _CLAIMED_UNVERIFIED_PATTERNS):
        return AnswerEvidenceType.CLAIMED_UNVERIFIED
    return None


def _content_aware_follow_up(answer: str) -> str:
    """A probing question grounded in *what the answer described* - never the target name.

    Checked in a fixed priority order so the same answer always produces the same follow-up
    (test determinism), falling back to a generic probe when no specific angle is detected.
    """
    if _PERFORMANCE_PATTERN.search(answer):
        return (
            "What led you to identify that as the issue, and how did you verify the "
            "improvement afterward?"
        )
    if _LEADERSHIP_PATTERN.search(answer):
        return "How did you handle any disagreement or pushback from others during that?"
    if _BUILD_PATTERN.search(answer):
        return (
            "What tradeoffs did you consider when you approached it that way, and what "
            "would you do differently now?"
        )
    return "What was the most difficult part of that, and how did you work through it?"


_WHITESPACE_PATTERN = re.compile(r"\s")


def _evidence_excerpt(answer: str, limit: int = 200) -> str:
    """A short excerpt of ``answer`` for the ``evidence`` field, never cutting a word in half.

    Regression fix: a raw ``answer[:200]`` slice chopped through the middle of whatever word
    happened to sit at the 200th character (e.g. "independently lead production deploy|ments"),
    which is unreadable and misrepresents what the candidate actually wrote. This truncates at
    the last whitespace before ``limit`` instead, so the excerpt always ends on a whole word,
    and marks it with a single ellipsis so it's clear more was said. The excerpt is only ever
    used for the report's evidence quote - the full, untouched answer is stored separately
    (see ``interview_graph.py``'s history entries) and is never affected by this.

    Boundary detection is whitespace-aware (``\\s`` - spaces, tabs, newlines, etc.), not just
    literal ``" "``: a Copilot review caught that the original space-only version left tabs and
    newlines unrecognised as boundaries (e.g. ``_evidence_excerpt("one\\ntwo three", 5)`` could
    still cut through "two").

    If there is no whitespace boundary before ``limit`` at all (``limit`` smaller than the
    first word, or one unbroken token longer than ``limit`` with no whitespace anywhere before
    it), the "never cut a word in half" guarantee takes priority over strictly respecting
    ``limit``: the excerpt extends to the end of that first whole word instead of chopping
    through it. In the extreme case of a single token with no whitespace anywhere in the whole
    answer, that "first word" *is* the entire answer, so it is returned unchanged with no
    ellipsis - there is nothing left out to mark.
    """
    if len(answer) <= limit:
        return answer

    truncated = answer[:limit]
    boundary = -1
    for match in _WHITESPACE_PATTERN.finditer(truncated):
        boundary = match.start()
    if boundary > 0:
        return truncated[:boundary].rstrip() + "…"

    first_whitespace = _WHITESPACE_PATTERN.search(answer)
    if first_whitespace is None:
        return answer  # one unbroken token, longer than `limit` - nothing safe to cut at all.
    first_word = answer[: first_whitespace.start()]
    return first_word + "…"


def _parse_evaluation_input(input_text: str) -> tuple[str, str, str]:
    """Extract ``(target, category, answer)`` from the ``QUESTION:``/``CATEGORY:``/``TARGET:``/
    ``GROUNDING:``/``OTHER_TARGETS:``/``ANSWER:`` format produced by
    :class:`app.services.answer_evaluation.AnswerEvaluationService` (``ANSWER:`` is always the
    last field, so everything from that line onward - not just its first physical line - is
    taken as the answer, in case it spans multiple lines). Shared by
    :func:`_fake_evaluate_answer_primary` and the cross-target-evidence pass in
    :func:`_fake_evaluate_answer`, so both agree on exactly what "the answer" is.
    """
    target = "the target"
    category = ""
    answer = ""
    lines = input_text.splitlines()
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.upper().startswith("CATEGORY:"):
            _, _, value = line.partition(":")
            category = value.strip().lower()
        elif line.upper().startswith("TARGET:"):
            _, _, value = line.partition(":")
            target = value.strip() or target
        elif line.upper().startswith("ANSWER:"):
            _, _, value = line.partition(":")
            answer = "\n".join([value.strip(), *lines[i + 1 :]]).strip()
            break
    return target, category, answer


def _parse_other_targets(input_text: str) -> list[tuple[str, str]]:
    """Extract the ``(category, name)`` pairs from an ``OTHER_TARGETS:`` block, if present -
    see :meth:`app.services.answer_evaluation.AnswerEvaluationService.evaluate`'s
    ``other_targets`` param. Returns ``[]`` when the block is absent."""
    targets: list[tuple[str, str]] = []
    in_block = False
    for raw_line in input_text.splitlines():
        line = raw_line.strip()
        if line.upper().startswith("OTHER_TARGETS:"):
            in_block = True
            continue
        if line.upper().startswith("ANSWER:"):
            break
        if in_block and line.startswith("-"):
            category, _, name = line[1:].partition(":")
            name = name.strip()
            if name:
                targets.append((category.strip().lower(), name))
    return targets


def _cross_target_mention_window(answer: str, target_name: str) -> str | None:
    """The sentence of ``answer`` containing ``target_name``'s first mention, or ``None`` if
    it isn't mentioned at all.

    Scoped to a single sentence (bounded by ``.``), not a fixed character radius: an earlier,
    unrelated regression used a plain character window, which let an action verb describing
    the *primary* target's own answer (a different sentence entirely) bleed into a later
    sentence's incidental namedrop of another target, misclassifying a casual mention as
    strong evidence. A real answer volunteering genuine evidence about another target says so
    in the same breath as naming it - splitting on sentence boundaries is what actually
    isolates "what was said about this specific mention".
    """
    match = re.search(rf"\b{re.escape(target_name)}\b", answer, re.IGNORECASE)
    if match is None:
        return None
    sentence_start = answer.rfind(".", 0, match.start())
    sentence_start = sentence_start + 1 if sentence_start != -1 else 0
    next_period = answer.find(".", match.end())
    sentence_end = next_period + 1 if next_period != -1 else len(answer)
    return answer[sentence_start:sentence_end].strip()


def _classify_cross_target_mention(window: str) -> AnswerEvidenceType:
    """Classify one other target's incidental mention, given the local window around it (see
    :func:`_cross_target_mention_window`).

    Deliberately coarser than the primary per-question classification (only three possible
    outcomes): this is scoped to a local window around a single namedrop, not a full answer
    written in response to a question about that target, so it can only distinguish "explicitly
    denied nearby", "described with real, verb-backed detail nearby" (-> ``demonstrated`` -
    strong enough to resolve the target outright, see
    :mod:`app.services.cross_target_evidence`), or "just named, nothing more" (->
    ``claimed_unverified`` - a casual mention, never enough alone to close the target).
    """
    if any(p.search(window) for p in _EXPLICIT_LACK_PATTERNS):
        return AnswerEvidenceType.EXPLICIT_LACK
    if _ACTION_VERB_PATTERN.search(window) and len(window.split()) >= 8:
        return AnswerEvidenceType.DEMONSTRATED
    return AnswerEvidenceType.CLAIMED_UNVERIFIED


def _find_cross_target_evidence(
    answer: str, other_targets: list[tuple[str, str]]
) -> list[CrossTargetEvidence]:
    evidence: list[CrossTargetEvidence] = []
    for _category, name in other_targets:
        window = _cross_target_mention_window(answer, name)
        if window is None:
            continue
        evidence.append(
            CrossTargetEvidence(
                target=name,
                evidence_type=_classify_cross_target_mention(window),
                note=_evidence_excerpt(window.strip()),
            )
        )
    return evidence


def _fake_evaluate_answer(input_text: str) -> AnswerEvaluation:
    """Classify the answer's actual content, then score/decide from that classification -
    and separately check whether it also volunteers evidence about any *other* coverage target
    (see ``OTHER_TARGETS:`` / :class:`~app.domain.evaluation.CrossTargetEvidence`)."""
    result = _fake_evaluate_answer_primary(input_text)
    _, _, answer = _parse_evaluation_input(input_text)
    other_targets = _parse_other_targets(input_text)
    if answer.strip() and other_targets:
        cross_evidence = _find_cross_target_evidence(answer, other_targets)
        if cross_evidence:
            result = result.model_copy(update={"cross_target_evidence": cross_evidence})
    return result


def _fake_evaluate_answer_primary(input_text: str) -> AnswerEvaluation:
    """Classify the answer's actual content, then score/decide from that classification.

    Never treats the target name, the question, or the interview stage as evidence - only the
    candidate's own words.
    """
    target, category, answer = _parse_evaluation_input(input_text)

    phrase = _clean_target_phrase(target, category=category)

    if answer is None or not answer.strip():
        return AnswerEvaluation(
            score=0.0,
            evidence_type=AnswerEvidenceType.INSUFFICIENT,
            decision=EvaluationDecision.FOLLOW_UP,
            strengths=[],
            weaknesses=[f"No answer was given for {phrase}."],
            evidence=[],
            follow_up_needed=True,
            follow_up_question="Could you share an answer to the question?",
        )

    evidence_type = _classify_evidence(answer)

    if evidence_type is AnswerEvidenceType.EXPLICIT_LACK:
        # The candidate explicitly said they lack this experience. Asking them for "a specific
        # example" of something they just said they don't have is exactly the non-adaptive
        # behaviour this classification exists to avoid - advance to another question instead
        # of following up on a dead end.
        return AnswerEvaluation(
            score=0.05,
            evidence_type=evidence_type,
            decision=EvaluationDecision.ADVANCE,
            strengths=[],
            weaknesses=[f"The candidate stated they do not have experience with {phrase}."],
            evidence=[],
            follow_up_needed=False,
        )

    if evidence_type is AnswerEvidenceType.INSUFFICIENT:
        # Confused/off-topic - the candidate answered, but not in a way that asserts or denies
        # real experience. Same anti-gaming rule as explicit lack: nothing concrete to probe.
        return AnswerEvaluation(
            score=0.05,
            evidence_type=evidence_type,
            decision=EvaluationDecision.ADVANCE,
            strengths=[],
            weaknesses=[f"The candidate's answer did not address {phrase} with any evidence."],
            evidence=[],
            follow_up_needed=False,
        )

    if evidence_type is AnswerEvidenceType.CONTRADICTORY:
        return AnswerEvaluation(
            score=0.2,
            evidence_type=evidence_type,
            decision=EvaluationDecision.FOLLOW_UP,
            strengths=[],
            weaknesses=[
                f"The candidate's answer contained inconsistent statements about {phrase}."
            ],
            evidence=[_evidence_excerpt(answer)],
            follow_up_needed=True,
            follow_up_question=(
                f"You mentioned conflicting things about {phrase} - can you clarify your "
                "actual experience?"
            ),
        )

    if evidence_type is AnswerEvidenceType.CLAIMED_UNVERIFIED:
        # The candidate attempted an answer but gave nothing verifiable - never the same claim
        # as an explicit denial (see AnswerEvidenceType's docstring for the real Java/MATLAB
        # example this classification exists to fix).
        return AnswerEvaluation(
            score=0.15,
            evidence_type=evidence_type,
            decision=EvaluationDecision.FOLLOW_UP,
            strengths=[],
            weaknesses=[
                f"The candidate claimed experience related to {phrase} but could not provide "
                "verifiable detail."
            ],
            evidence=[_evidence_excerpt(answer)],
            follow_up_needed=True,
            follow_up_question=(
                f"Can you share a specific detail (e.g. a framework, tool, or project) that "
                f"demonstrates your experience with {phrase}?"
            ),
        )

    word_count = len(answer.split())
    verb_matches = len(_ACTION_VERB_PATTERN.findall(answer))

    if word_count < _MIN_SUBSTANTIVE_WORDS:
        # A real claim ("ten years of experience") or a throwaway one ("I did that once.") -
        # either way, too little detail to judge; ask for a concrete example, once.
        return AnswerEvaluation(
            score=0.3,
            evidence_type=AnswerEvidenceType.INSUFFICIENT,
            decision=EvaluationDecision.FOLLOW_UP,
            strengths=[],
            weaknesses=[
                f"The answer was too brief to assess {phrase} - no concrete example was given."
            ],
            evidence=[_evidence_excerpt(answer)],
            follow_up_needed=True,
            follow_up_question=f"Can you give a specific example related to {phrase}?",
        )

    if word_count >= _MIN_THOROUGH_WORDS and verb_matches >= _MIN_THOROUGH_VERBS:
        return AnswerEvaluation(
            score=0.8,
            evidence_type=AnswerEvidenceType.DEMONSTRATED,
            decision=EvaluationDecision.ADVANCE,
            strengths=[f"Gave a concrete, specific example related to {phrase}."],
            weaknesses=[],
            evidence=[_evidence_excerpt(answer)],
            follow_up_needed=False,
        )

    # Substantive enough to engage with, but there's a specific angle worth exploring further -
    # the follow-up below is generated from the answer's own content, not the target name.
    return AnswerEvaluation(
        score=0.6,
        evidence_type=AnswerEvidenceType.PARTIAL,
        decision=EvaluationDecision.FOLLOW_UP,
        strengths=[f"Described a specific example related to {phrase}."],
        weaknesses=[],
        evidence=[_evidence_excerpt(answer)],
        follow_up_needed=True,
        follow_up_question=_content_aware_follow_up(answer),
    )


#: Mirrors app.services.report_scoring._EVIDENCE_STRENGTH_THRESHOLDS' bands in plain English.
#: Duplicated here (not imported) because app.llm sits below app.services in the dependency
#: layering - see the module docstring pattern already used for the answer-length heuristic.
_OVERALL_SUMMARY_PHRASES: list[tuple[float, str]] = [
    (0.8, "demonstrated strong, well-evidenced performance across the areas assessed"),
    (0.6, "demonstrated solid performance, with some areas worth exploring further"),
    (0.35, "showed limited evidence across the areas assessed"),
]
_DEFAULT_OVERALL_SUMMARY_PHRASE = (
    "did not provide enough concrete evidence across the areas assessed to draw firm "
    "conclusions"
)


_NAMED_GAP_EVIDENCE_STRENGTHS = {"insufficient", "not_assessed"}
_MAX_NAMED_GAPS = 6
_MAX_NAMED_UNASSESSED = 6


def _fake_generate_report_narrative(input_text: str) -> ReportNarrative:
    """Deterministically echo back only the strengths/weaknesses already given.

    Never invents a claim: every string in the returned lists came verbatim from a
    ``STRENGTHS:``/``WEAKNESSES:`` line in ``input_text`` (built by
    :class:`app.services.report_narrative.ReportNarrativeService` from already-computed,
    evidence-based :class:`~app.domain.report.CompetencyAssessment` data). The summary
    describes the candidate's performance in plain language (never the scoring mechanism -
    no "deterministic", no raw percentage) over the given ``OVERALL_SCORE:``/
    ``RECOMMENDATION:`` - see the Milestone report-quality review. It also names which specific
    competencies lack sufficient evidence (mirroring
    ``app.services.report_generation._evidence_gap_sentence``) rather than a vaguer overall
    phrase alone, so the fake-client path (used without a real LLM key) still demonstrates the
    evidence-grounded-language fix: never a conclusion about capability the evidence doesn't
    support (e.g. "raises concerns about their ability to do the job"), only which requirements
    weren't evidenced. It likewise echoes ``UNASSESSED_REQUIRED_TARGETS:`` (mirroring
    ``app.services.report_generation._unassessed_targets_sentence``) so the fake-client path
    also demonstrates that an adaptive interview ending early is reported honestly rather than
    silently implying full role coverage.
    """
    overall_score = 0.0
    recommendation = "consider"
    strengths: list[str] = []
    weaknesses: list[str] = []
    current_competency: str | None = None
    named_gaps: list[str] = []
    unassessed_required_targets: list[str] = []

    for line in input_text.splitlines():
        line = line.strip()
        if line.upper().startswith("OVERALL_SCORE:"):
            try:
                overall_score = float(line.partition(":")[2].strip())
            except ValueError:
                overall_score = 0.0
        elif line.upper().startswith("RECOMMENDATION:"):
            recommendation = line.partition(":")[2].strip() or recommendation
        elif line.upper().startswith("UNASSESSED_REQUIRED_TARGETS:"):
            value = line.partition(":")[2].strip()
            if value and value != "(none)":
                unassessed_required_targets.extend(
                    item.strip() for item in value.split(",") if item.strip()
                )
        elif line.upper().startswith("COMPETENCY:"):
            current_competency = line.partition(":")[2].strip() or None
        elif line.upper().startswith("EVIDENCE_STRENGTH:"):
            value = line.partition(":")[2].strip().lower()
            if current_competency and value in _NAMED_GAP_EVIDENCE_STRENGTHS:
                named_gaps.append(current_competency)
        elif line.upper().startswith("STRENGTHS:"):
            value = line.partition(":")[2].strip()
            if value and value != "(none)":
                strengths.extend(item.strip() for item in value.split(";") if item.strip())
        elif line.upper().startswith("WEAKNESSES:"):
            value = line.partition(":")[2].strip()
            if value and value != "(none)":
                weaknesses.extend(item.strip() for item in value.split(";") if item.strip())

    phrase = _DEFAULT_OVERALL_SUMMARY_PHRASE
    for threshold, candidate_phrase in _OVERALL_SUMMARY_PHRASES:
        if overall_score >= threshold:
            phrase = candidate_phrase
            break

    summary = (
        f"Across the interview, the candidate {phrase}. This supports a recommendation of "
        f"{recommendation.replace('_', ' ')}."
    )
    if named_gaps:
        named_gaps = named_gaps[:_MAX_NAMED_GAPS]
        listed = named_gaps[0] if len(named_gaps) == 1 else (
            ", ".join(named_gaps[:-1]) + f", and {named_gaps[-1]}"
        )
        qualifier = "one requirement" if len(named_gaps) == 1 else "several requirements"
        summary += (
            f" The interview did not provide sufficient evidence that the candidate meets "
            f"{qualifier}, particularly {listed}."
        )

    if unassessed_required_targets:
        unassessed_named = unassessed_required_targets[:_MAX_NAMED_UNASSESSED]
        listed = unassessed_named[0] if len(unassessed_named) == 1 else (
            ", ".join(unassessed_named[:-1]) + f", and {unassessed_named[-1]}"
        )
        qualifier = "requirement" if len(unassessed_named) == 1 else "requirements"
        summary += (
            f" The interview ended before assessing the following required {qualifier}: "
            f"{listed}. This reflects the adaptive interview's length, not a judgment on the "
            "candidate."
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
