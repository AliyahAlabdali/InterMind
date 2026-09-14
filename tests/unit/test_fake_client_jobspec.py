"""Tests for FakeLLMClient's content-aware JobSpec extraction.

Milestone 6 investigation finding: a single fixed canned JobSpec for every job description
starves the O*NET TF-IDF matcher of real signal (any JD ends up producing nearly the same
query text). These tests demonstrate the fake client is now content-aware - it extracts
different, JD-specific signal - without hard-coding any particular occupation mapping.
"""

from __future__ import annotations

from app.domain.job import JobSpec
from app.llm.fake_client import FakeLLMClient
from app.services.jd_analysis import JDAnalysisService

AI_ENGINEER_JD = """AI Engineer

We are looking for an AI Engineer to design, develop, and deploy machine learning and
artificial intelligence solutions for real-world applications.

Responsibilities:

* Develop and optimize machine learning and deep learning models.
* Build AI-powered applications using Python and modern ML frameworks.
* Design and implement REST APIs for serving machine learning models.
* Work with large datasets to preprocess, analyze, and extract meaningful insights.
* Develop computer vision and natural language processing solutions when required.
* Evaluate model performance using appropriate metrics and continuously improve model accuracy.
* Deploy and optimize AI models for production environments.
* Collaborate with software engineers and product teams to integrate AI capabilities into
  production systems.

Requirements:

* Strong programming skills in Python.
* Experience with machine learning and deep learning.
* Experience with PyTorch or TensorFlow.
* Knowledge of computer vision and/or natural language processing.
* Experience building REST APIs, preferably with FastAPI.
* Familiarity with SQL and relational databases.
* Understanding of model deployment and optimization.
* Strong problem-solving and analytical skills.
* Experience with Git and collaborative software development.

Preferred:

* Experience with Transformers and large language models.
* Experience with Docker and cloud platforms.
* Experience optimizing models using ONNX or similar technologies.
"""

HEALTH_INFORMATICS_JD = """Health Informatics Specialist

We are looking for a Health Informatics Specialist to support healthcare organizations by
managing and analyzing health information systems and clinical data. The candidate should
have strong skills in electronic health records, healthcare data management, clinical
information systems, data analysis, and health information technology.

Responsibilities include analyzing healthcare data, maintaining electronic health records,
supporting clinical information systems, improving data quality, preparing reports, and
working with healthcare professionals to ensure accurate and secure health information.
"""


async def _analyze(jd_text: str) -> JobSpec:
    service = JDAnalysisService(llm=FakeLLMClient())
    return await service.analyze(jd_text)


async def test_different_jds_produce_different_jobspecs():
    """Test A: two clearly different JDs must not collapse to the same JobSpec."""
    ai_spec = await _analyze(AI_ENGINEER_JD)
    hi_spec = await _analyze(HEALTH_INFORMATICS_JD)

    assert ai_spec != hi_spec
    assert ai_spec.role_title != hi_spec.role_title
    assert ai_spec.summary != hi_spec.summary
    ai_skill_names = {s.name for s in ai_spec.skills}
    hi_skill_names = {s.name for s in hi_spec.skills}
    assert ai_skill_names != hi_skill_names
    # The two domains should share no extracted skill at all for these particular JDs.
    assert ai_skill_names.isdisjoint(hi_skill_names)


async def test_ai_engineer_skills_are_extracted():
    """Test B: AI/ML-relevant terms actually present in the JD show up as skills."""
    spec = await _analyze(AI_ENGINEER_JD)
    skill_names = {s.name for s in spec.skills}

    expected = {
        "Python",
        "Machine Learning",
        "Deep Learning",
        "PyTorch",
        "TensorFlow",
        "FastAPI",
        "SQL",
        "Computer Vision",
        "Natural Language Processing",
        "Transformers",
        "Docker",
        "ONNX",
    }
    assert expected <= skill_names

    # No healthcare-domain vocabulary should leak in for an unrelated JD.
    assert not {"Electronic Health Records", "Healthcare Data Management"} & skill_names


async def test_ai_engineer_preferred_skills_are_marked_not_required():
    """Skills listed under a "Preferred:" heading are extracted with required=False."""
    spec = await _analyze(AI_ENGINEER_JD)
    by_name = {s.name: s.required for s in spec.skills}

    assert by_name["Python"] is True
    assert by_name["FastAPI"] is True
    assert by_name["Transformers"] is False
    assert by_name["Docker"] is False
    assert by_name["ONNX"] is False


async def test_health_informatics_skills_are_different():
    """Test C: the HI JD extracts healthcare/informatics terms, not tech-stack terms."""
    spec = await _analyze(HEALTH_INFORMATICS_JD)
    skill_names = {s.name for s in spec.skills}

    expected = {
        "Electronic Health Records",
        "Healthcare Data Management",
        "Clinical Information Systems",
        "Health Information Technology",
        "Data Analysis",
    }
    assert expected <= skill_names

    # No AI/ML vocabulary should be invented for a JD that never mentions it - this is
    # generic keyword extraction from the actual text, not an occupation-specific mapping.
    assert not {"Python", "PyTorch", "TensorFlow", "Machine Learning"} & skill_names


async def test_role_title_reflects_actual_jd():
    ai_spec = await _analyze(AI_ENGINEER_JD)
    hi_spec = await _analyze(HEALTH_INFORMATICS_JD)
    assert ai_spec.role_title == "AI Engineer"
    assert hi_spec.role_title == "Health Informatics Specialist"
