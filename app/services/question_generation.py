"""Question-phrasing use case: role title + targets -> grounded question text.

Mirrors :class:`app.services.jd_analysis.JDAnalysisService`: the LLM only supplies question
*phrasing*, structured and validated through the same :class:`~app.llm.ports.LLMClient`
boundary. Deciding *what* to ask about (which competencies/technologies/tasks) happens
upstream in :class:`app.services.interview_planner.InterviewPlannerService` - this service
takes that selection as given.

**Production incident (bounded retry)**: a real OpenAI call generated questions for
``competency: collaboration`` and ``task: develop restful apis`` when the actually-requested
target (during runtime, single-target generation - see ``app.agents.interview_graph``) was a
single unrelated technology. Both wrong targets were lifted verbatim from the ``JD_CONTEXT``
block's own ``COMPETENCIES``/``RESPONSIBILITIES`` lists - a real LLM occasionally reads
background context formatted as a list (see ``app.agents.interview_graph._jd_context``) as a
second, competing set of targets, despite the prompt saying not to. ``_validate_generated``
correctly rejected this (it is not weakened here - see its own docstring), but the previous
behaviour then let a single such generation failure crash the whole interview turn. ``generate``
now retries **at most once**, for the identical requested target(s) and context, with an
appended correction block telling the model exactly what it did wrong - never a second,
different target, never a recursive/unbounded loop. If the retry also fails validation, the
original :class:`~app.core.exceptions.QuestionGenerationError` semantics are preserved
unchanged (still raised, still whatever the API layer already sanitizes to a 502 - see
``app.api.errors``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.exceptions import QuestionGenerationError
from app.domain.interview_plan import GeneratedQuestion, GeneratedQuestionSet
from app.llm.ports import LLMClient
from app.llm.prompts import load_prompt
from app.services.text_normalize import normalize_name

logger = logging.getLogger(__name__)

PROMPT_NAME = "interview_questions"
PROMPT_VERSION = "v1"

#: Total attempts allowed for one `generate()` call: the first, normal attempt plus exactly one
#: bounded retry - never recursive, never more than this. See the module docstring.
_MAX_ATTEMPTS = 2

#: Appended to the retry attempt's own input only - never sent on the first attempt, and never
#: exposed to the candidate (it lives entirely inside the LLM request/response, not the
#: question text itself). Explicitly names the failure so the model treats this as a direct
#: correction rather than an ordinary request - see interview_questions_v1.md's own handling
#: of this block.
_RETRY_CORRECTION_BLOCK = (
    "RETRY_CORRECTION:\n"
    "The previous generation violated the target constraint: it included a target that was "
    "not requested above. Generate exactly one question for the requested target listed above "
    "and nothing else. Do not assess, or make the subject of the question, any other "
    "competency, technology, or task - including anything named in JD_CONTEXT, ONET_CONTEXT, "
    "or INTERVIEW_HISTORY below. Those remain background/context only. Do not change the "
    "requested target."
)


@dataclass
class QuestionGenerationService:
    llm: LLMClient

    async def generate(
        self,
        *,
        role_title: str,
        targets: list[tuple[str, str]],
        jd_context: str = "",
        onet_context: str = "",
        history_context: str = "",
    ) -> GeneratedQuestionSet:
        """Return one phrased question per ``(category, target_name)`` pair in ``targets``.

        ``category`` must be one of ``"competency"``, ``"technology"``, ``"task"``.

        ``jd_context``, when non-empty, is a plain-text rendering of the job description's own
        requirements relevant to this call - seniority, required/preferred technologies,
        competencies, responsibilities, and the current target's own requirement level/grounding
        (see ``app.agents.interview_graph._jd_context``). This is the JD - the source of truth
        for what the interview evaluates (see ``app.services.interview_planner``'s module
        docstring) - grounding the question in more than just the bare target name, the same
        way ``onet_context`` grounds it in supplementary occupational detail. The two are not
        interchangeable: ``jd_context`` may inform *what the JD itself says*, ``onet_context``
        never may - see the rule below.

        ``onet_context``, when non-empty, is supplementary occupational context (matched
        occupation title plus a few relevance-filtered technologies/tasks - see
        ``InterviewPlannerService._build_onet_context``) appended for the LLM to draw on when
        *phrasing* questions. It is never itself a target: it must not change which or how
        many questions are generated, and a real LLM must not invent a new requirement from it
        - see ``interview_questions_v1.md``. O*NET is supporting context only; it never
        supersedes or contradicts ``jd_context``.

        ``history_context``, when non-empty, is a plain-text rendering of the interview so far
        (prior questions and the candidate's own answers - see
        ``app.agents.interview_graph``'s runtime question-generation call), so a question about
        a later target can be phrased with awareness of what's already been asked/said and
        avoid repeating it. Called with exactly one target and a growing ``history_context`` is
        the normal runtime shape (one target per main question, decided adaptively - see
        ``app.services.target_selection``); the batch (multiple targets, no history) shape this
        method also supports is what a plan's very first question uses, since there is no
        history yet.

        Raises:
            app.core.exceptions.QuestionGenerationError: the provider's response still does
                not contain exactly one question per requested target, in the requested order,
                after one bounded retry for the identical target(s) and context (see the
                module docstring) - whether from the fake client or a real LLM. Never silently
                dropped, and never retried more than once.
        """
        if not targets:
            return GeneratedQuestionSet(questions=[])

        base_lines = [f"ROLE: {role_title}"]
        base_lines += [f"{category.upper()}: {name}" for category, name in targets]
        prompt = load_prompt(PROMPT_NAME, PROMPT_VERSION)

        last_error: QuestionGenerationError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            lines = list(base_lines)
            if attempt > 0:
                # Same requested target(s), same jd/onet/history context as the first attempt
                # - only this correction block is added. The retry can never change *what* is
                # being asked about, only how forcefully the model is told to stick to it.
                lines += ["", _RETRY_CORRECTION_BLOCK]
            if jd_context:
                lines += ["", "JD_CONTEXT:", jd_context]
            if onet_context:
                lines += ["", "ONET_CONTEXT:", onet_context]
            if history_context:
                lines += ["", "INTERVIEW_HISTORY:", history_context]

            result = await self.llm.generate_structured(
                prompt=prompt,
                input_text="\n".join(lines),
                schema=GeneratedQuestionSet,
            )
            try:
                _validate_generated(targets, result.questions)
            except QuestionGenerationError as exc:
                last_error = exc
                logger.warning(
                    "Question generation returned an invalid target set on attempt %d/%d for "
                    "targets %s; %s.",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    targets,
                    "retrying once" if attempt + 1 < _MAX_ATTEMPTS else "giving up",
                )
                continue
            return result

        # Reachable only once every attempt has failed validation - the loop returns directly
        # on success, so `last_error` is always set by the time execution gets here.
        assert last_error is not None
        raise last_error


def _key(category: str, target: str) -> tuple[str, str]:
    return category.strip().lower(), normalize_name(target)


def _validate_generated(
    targets: list[tuple[str, str]], questions: list[GeneratedQuestion]
) -> None:
    """Check ``questions`` is exactly one response per requested target, in order.

    A mis-categorised response (right target text, wrong category, or vice versa) surfaces
    as that target simultaneously appearing "unexpected" (under the wrong key) and "missing"
    (under the right key) - no separate category check is needed to catch it.
    """
    requested = [_key(category, target) for category, target in targets]
    returned = [_key(q.category, q.target) for q in questions]

    seen: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    for key in returned:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        raise QuestionGenerationError(
            f"Generated questions contain duplicate target(s): {sorted(duplicates)}"
        )

    requested_set = set(requested)
    unexpected = [key for key in returned if key not in requested_set]
    if unexpected:
        raise QuestionGenerationError(
            f"Generated questions contain unrequested target(s): {unexpected}"
        )

    returned_set = set(returned)
    missing = [key for key in requested if key not in returned_set]
    if missing:
        raise QuestionGenerationError(
            f"Generated questions are missing requested target(s): {missing}"
        )

    # No duplicates, nothing unexpected, nothing missing: `returned` is some ordering of
    # exactly `requested`. It must match order-for-order, not just as a set.
    if returned != requested:
        raise QuestionGenerationError(
            "Generated questions are not in the requested target order: "
            f"expected {requested}, got {returned}"
        )
