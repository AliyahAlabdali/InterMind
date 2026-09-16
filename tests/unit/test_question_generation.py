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
