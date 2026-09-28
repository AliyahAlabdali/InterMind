import pytest

from app.core.exceptions import QuestionGenerationError
from app.domain.interview_plan import GeneratedQuestionSet
from app.llm.fake_client import FakeLLMClient
from app.services.question_generation import QuestionGenerationService


async def test_generate_returns_one_question_per_target():
    service = QuestionGenerationService(llm=FakeLLMClient())
    result = await service.generate(
        role_title="Software Developer",
        targets=[
            ("competency", "Critical Thinking"),
            ("technology", "Python"),
            ("task", "Analyze user needs and software requirements."),
        ],
    )
    assert len(result.questions) == 3
    categories = [q.category for q in result.questions]
    assert categories == ["competency", "technology", "task"]
    assert result.questions[0].target == "Critical Thinking"
    assert "critical thinking" in result.questions[0].text.lower()
    assert "Python" in result.questions[1].text


async def test_generate_with_no_targets_returns_empty_set():
    service = QuestionGenerationService(llm=FakeLLMClient())
    result = await service.generate(role_title="Software Developer", targets=[])
    assert result == GeneratedQuestionSet(questions=[])


async def test_generated_questions_are_role_specific_not_identical_across_roles():
    """The same competency must not produce byte-identical question text for two different
    roles - phrasing should incorporate the role, not just the bare target name."""
    service = QuestionGenerationService(llm=FakeLLMClient())

    marketing = await service.generate(
        role_title="Digital Marketing Specialist",
        targets=[("competency", "Leadership")],
    )
    backend = await service.generate(
        role_title="Senior Backend Software Engineer",
        targets=[("competency", "Leadership")],
    )

    assert marketing.questions[0].text != backend.questions[0].text
    assert "Digital Marketing Specialist" in marketing.questions[0].text
    assert "Senior Backend Software Engineer" in backend.questions[0].text


async def test_generated_questions_do_not_just_repeat_the_competency_name_as_a_template():
    """The generic "tell me about a time you demonstrated {competency}" construction (a
    literal repeat of the competency name with no other content) must not appear."""
    service = QuestionGenerationService(llm=FakeLLMClient())
    result = await service.generate(
        role_title="Digital Marketing Specialist",
        targets=[("competency", "Leadership")],
    )
    text = result.questions[0].text.lower()
    assert "tell me about a time you demonstrated leadership." not in text


async def test_generate_uses_configured_fake_response():
    canned = GeneratedQuestionSet(
        questions=[{"category": "competency", "target": "Ownership", "text": "Canned question?"}]
    )
    service = QuestionGenerationService(llm=FakeLLMClient(response=canned))
    result = await service.generate(role_title="Anything", targets=[("competency", "Ownership")])
    assert result == canned


async def test_two_different_roles_produce_different_question_text():
    service = QuestionGenerationService(llm=FakeLLMClient())
    developer = await service.generate(
        role_title="Software Developer", targets=[("competency", "Critical Thinking")]
    )
    nurse = await service.generate(
        role_title="Registered Nurse", targets=[("competency", "Critical Thinking")]
    )
    assert developer.questions[0].text != nurse.questions[0].text
    assert "Software Developer" in developer.questions[0].text
    assert "Registered Nurse" in nurse.questions[0].text


async def test_missing_target_in_generated_response_raises():
    canned = GeneratedQuestionSet(
        questions=[{"category": "competency", "target": "Ownership", "text": "Q1?"}]
    )
    service = QuestionGenerationService(llm=FakeLLMClient(response=canned))
    with pytest.raises(QuestionGenerationError, match="missing"):
        await service.generate(
            role_title="Anything",
            targets=[("competency", "Ownership"), ("technology", "Python")],
        )


async def test_duplicate_target_in_generated_response_raises():
    canned = GeneratedQuestionSet(
        questions=[
            {"category": "competency", "target": "Ownership", "text": "Q1?"},
            {"category": "competency", "target": "Ownership", "text": "Q2?"},
        ]
    )
    service = QuestionGenerationService(llm=FakeLLMClient(response=canned))
    with pytest.raises(QuestionGenerationError, match="duplicate"):
        await service.generate(role_title="Anything", targets=[("competency", "Ownership")])


async def test_unexpected_target_in_generated_response_raises():
    canned = GeneratedQuestionSet(
        questions=[{"category": "competency", "target": "Something Else", "text": "Q1?"}]
    )
    service = QuestionGenerationService(llm=FakeLLMClient(response=canned))
    with pytest.raises(QuestionGenerationError, match="unrequested"):
        await service.generate(role_title="Anything", targets=[("competency", "Ownership")])


async def test_wrong_category_in_generated_response_raises():
    # Right target text, wrong category: surfaces as both "unexpected" and "missing".
    canned = GeneratedQuestionSet(
        questions=[{"category": "technology", "target": "Ownership", "text": "Q1?"}]
    )
    service = QuestionGenerationService(llm=FakeLLMClient(response=canned))
    with pytest.raises(QuestionGenerationError):
        await service.generate(role_title="Anything", targets=[("competency", "Ownership")])


class _SpyLLMClient:
    """Records the exact prompt/input_text it was called with, then delegates to FakeLLMClient."""

    def __init__(self):
        self.calls: list[dict] = []
        self._fake = FakeLLMClient()

    async def generate_structured(self, *, prompt, input_text, schema):
        self.calls.append({"prompt": prompt, "input_text": input_text, "schema": schema})
        return await self._fake.generate_structured(
            prompt=prompt, input_text=input_text, schema=schema
        )


async def test_onet_context_is_appended_to_the_prompt_input_but_is_not_a_target():
    """Test D: O*NET context must actually reach the LLM call (proving it's not dead/unused
    plumbing), but it must never change which questions are generated - it's a supplementary
    block after the targets, never itself parsed as a target."""
    spy = _SpyLLMClient()
    service = QuestionGenerationService(llm=spy)
    context = (
        "Matched occupation: Data Scientists\n"
        "Relevant technologies for this occupation:\n"
        "- R\n"
        "Relevant tasks for this occupation:\n"
        "- Analyze, manipulate, or process large sets of data using statistical software."
    )
    result = await service.generate(
        role_title="AI Engineer",
        targets=[("technology", "Python"), ("competency", "Collaboration")],
        onet_context=context,
    )

    assert len(spy.calls) == 1
    sent = spy.calls[0]["input_text"]
    assert "ONET_CONTEXT:" in sent
    assert "Data Scientists" in sent
    assert "R" in sent

    # The context did not become, or displace, a target.
    assert len(result.questions) == 2
    targets = {q.target for q in result.questions}
    assert targets == {"Python", "Collaboration"}
    assert not any(q.target == "R" for q in result.questions)
    assert not any(q.category == "task" for q in result.questions)


async def test_no_onet_context_means_no_context_block_in_the_prompt():
    spy = _SpyLLMClient()
    service = QuestionGenerationService(llm=spy)
    await service.generate(role_title="AI Engineer", targets=[("technology", "Python")])
    assert "ONET_CONTEXT" not in spy.calls[0]["input_text"]


async def test_jd_context_is_appended_to_the_prompt_input_but_is_not_a_target():
    """Copilot review, MUST FIX 2: runtime question generation must receive JD grounding
    (seniority, required/preferred technologies, competencies, responsibilities), not just the
    bare target/role/O*NET context/history. Mirrors the onet_context test above: it must
    actually reach the LLM call, but never become, or displace, a requested target."""
    spy = _SpyLLMClient()
    service = QuestionGenerationService(llm=spy)
    context = (
        "ROLE_TITLE: Backend Engineer\n"
        "SENIORITY: senior\n"
        "REQUIRED_TECHNOLOGIES: Python, SQL\n"
        "COMPETENCIES: Collaboration\n"
        "RESPONSIBILITIES:\n"
        "- Ship backend features.\n"
        "CURRENT_TARGET_REQUIREMENT_LEVEL: required\n"
    )
    result = await service.generate(
        role_title="Backend Engineer",
        targets=[("technology", "Python")],
        jd_context=context,
    )

    assert len(spy.calls) == 1
    sent = spy.calls[0]["input_text"]
    assert "JD_CONTEXT:" in sent
    assert "SENIORITY: senior" in sent
    assert "REQUIRED_TECHNOLOGIES: Python, SQL" in sent

    # JD context did not become, or displace, a target.
    assert len(result.questions) == 1
    assert result.questions[0].target == "Python"
    assert not any(q.target == "SQL" for q in result.questions)
    assert not any(q.target == "Collaboration" for q in result.questions)


async def test_no_jd_context_means_no_context_block_in_the_prompt():
    spy = _SpyLLMClient()
    service = QuestionGenerationService(llm=spy)
    await service.generate(role_title="AI Engineer", targets=[("technology", "Python")])
    assert "JD_CONTEXT" not in spy.calls[0]["input_text"]


async def test_jd_context_and_onet_context_can_both_be_present_and_stay_distinct():
    spy = _SpyLLMClient()
    service = QuestionGenerationService(llm=spy)
    await service.generate(
        role_title="AI Engineer",
        targets=[("technology", "Python")],
        jd_context="REQUIRED_TECHNOLOGIES: Python, SQL",
        onet_context="Matched occupation: Data Scientists",
    )
    sent = spy.calls[0]["input_text"]
    assert "JD_CONTEXT:" in sent
    assert "ONET_CONTEXT:" in sent
    # JD context appears before O*NET context - the JD is the source of truth, O*NET is
    # supplementary (see the module docstring).
    assert sent.index("JD_CONTEXT:") < sent.index("ONET_CONTEXT:")


async def test_out_of_order_generated_response_raises():
    canned = GeneratedQuestionSet(
        questions=[
            {"category": "technology", "target": "Python", "text": "Q-python?"},
            {"category": "competency", "target": "Ownership", "text": "Q-ownership?"},
        ]
    )
    service = QuestionGenerationService(llm=FakeLLMClient(response=canned))
    with pytest.raises(QuestionGenerationError, match="order"):
        await service.generate(
            role_title="Anything",
            targets=[("competency", "Ownership"), ("technology", "Python")],
        )


# --- Production incident: a real LLM occasionally generates questions for an unrequested
# --- target (e.g. lifted from JD_CONTEXT's own COMPETENCIES/RESPONSIBILITIES lists). Rather
# --- than crash the interview turn on the first bad generation, `generate()` retries exactly
# --- once, for the identical requested target(s) and context, with a correction block - see
# --- the module docstring. `_validate_generated` itself is untouched and still strict (see the
# --- tests above, which are unaffected: `FakeLLMClient(response=canned)` returns the same
# --- invalid `canned` response on every call, so those still end up raising after exhausting
# --- the retry, just via two calls to the LLM instead of one).


class _ScriptedLLMClient:
    """Returns pre-built `GeneratedQuestionSet` responses in order, one per call - lets a test
    script a first bad generation followed by a corrected retry, deterministically."""

    def __init__(self, responses: list[GeneratedQuestionSet]):
        self._responses = iter(responses)
        self.calls: list[dict] = []

    async def generate_structured(self, *, prompt, input_text, schema):
        assert schema is GeneratedQuestionSet, f"unexpected schema requested: {schema}"
        self.calls.append({"prompt": prompt, "input_text": input_text})
        return next(self._responses)


def _question_set(category: str, target: str, text: str = "Q?") -> GeneratedQuestionSet:
    return GeneratedQuestionSet(questions=[{"category": category, "target": target, "text": text}])


async def test_A_first_generation_valid_requires_no_retry():
    good = _question_set("technology", "Python")
    client = _ScriptedLLMClient([good])
    service = QuestionGenerationService(llm=client)

    result = await service.generate(role_title="Anything", targets=[("technology", "Python")])

    assert result == good
    assert len(client.calls) == 1


async def test_B_first_generation_invalid_retry_valid_succeeds():
    bad = _question_set("technology", "Java")
    good = _question_set("technology", "Python")
    client = _ScriptedLLMClient([bad, good])
    service = QuestionGenerationService(llm=client)

    result = await service.generate(role_title="Anything", targets=[("technology", "Python")])

    assert result == good
    assert len(client.calls) == 2


async def test_C_both_generations_invalid_raises_after_exactly_two_calls():
    first_bad = _question_set("technology", "Java")
    second_bad = _question_set("technology", "REST APIs")
    client = _ScriptedLLMClient([first_bad, second_bad])
    service = QuestionGenerationService(llm=client)

    with pytest.raises(QuestionGenerationError, match="unrequested"):
        await service.generate(role_title="Anything", targets=[("technology", "Python")])

    assert len(client.calls) == 2  # bounded - never a third attempt, never a retry loop


async def test_D_retry_cannot_change_the_requested_target():
    bad = _question_set("technology", "Java")
    good = _question_set("technology", "Python")
    client = _ScriptedLLMClient([bad, good])
    service = QuestionGenerationService(llm=client)

    await service.generate(role_title="Anything", targets=[("technology", "Python")])

    assert len(client.calls) == 2
    first_input, retry_input = client.calls[0]["input_text"], client.calls[1]["input_text"]
    # Same requested target line on both attempts - the retry only ever re-asks for the SAME
    # target, it never substitutes a different one.
    assert "TECHNOLOGY: Python" in first_input
    assert "TECHNOLOGY: Python" in retry_input
    # Only the retry carries the correction block, and it names no other target to switch to.
    assert "RETRY_CORRECTION" not in first_input
    assert "RETRY_CORRECTION" in retry_input


async def test_E_history_mentioning_other_targets_does_not_change_the_validation_target():
    """A real LLM's mistake was plausibly triggered by rich context (JD_CONTEXT/history)
    mentioning other technologies/competencies - this proves that regardless of what history
    says, the SAME originally-requested target is what both attempts are validated against."""
    history = (
        "PREVIOUS_Q: Tell me about Docker.\n"
        "PREVIOUS_A: I used Docker and FastAPI extensively, and led the migration project.\n"
        "PREVIOUS_Q: Tell me about a time you demonstrated leadership.\n"
        "PREVIOUS_A: I led a cross-functional initiative."
    )
    bad = _question_set("competency", "Leadership")  # lifted from history, not the real target
    good = _question_set("technology", "PostgreSQL")
    client = _ScriptedLLMClient([bad, good])
    service = QuestionGenerationService(llm=client)

    result = await service.generate(
        role_title="Backend Engineer",
        targets=[("technology", "PostgreSQL")],
        history_context=history,
    )

    assert result == good
    assert len(client.calls) == 2
    for call in client.calls:
        assert "TECHNOLOGY: PostgreSQL" in call["input_text"]
        assert history in call["input_text"]


async def test_F_retry_preserves_target_metadata_jd_and_onet_context_unchanged():
    """The retry must receive exactly the same target identity/category/requirement context
    and jd_context/onet_context as the first attempt - nothing about *what* is being asked
    changes, only the added correction instruction."""
    jd_context = (
        "REQUIRED_TECHNOLOGIES: PostgreSQL, Python\n"
        "CURRENT_TARGET_REQUIREMENT_LEVEL: required\n"
        "CURRENT_TARGET_GROUNDING: Job description technology"
    )
    onet_context = (
        "Matched occupation: Software Developers\n"
        "Relevant technologies for this occupation:\n"
        "- SQL"
    )
    bad = _question_set("technology", "Docker")
    good = _question_set("technology", "PostgreSQL")
    client = _ScriptedLLMClient([bad, good])
    service = QuestionGenerationService(llm=client)

    await service.generate(
        role_title="Backend Engineer",
        targets=[("technology", "PostgreSQL")],
        jd_context=jd_context,
        onet_context=onet_context,
    )

    assert len(client.calls) == 2
    for call in client.calls:
        assert "TECHNOLOGY: PostgreSQL" in call["input_text"]
        assert jd_context in call["input_text"]
        assert onet_context in call["input_text"]
