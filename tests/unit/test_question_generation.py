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
    assert "Critical Thinking" in result.questions[0].text
    assert "Python" in result.questions[1].text


async def test_generate_with_no_targets_returns_empty_set():
    service = QuestionGenerationService(llm=FakeLLMClient())
    result = await service.generate(role_title="Software Developer", targets=[])
    assert result == GeneratedQuestionSet(questions=[])


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
