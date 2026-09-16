"""Tests for FakeLLMClient's content-aware JobSpec extraction.

Milestone 6 investigation finding: a single fixed canned JobSpec for every job description
starves the O*NET TF-IDF matcher of real signal (any JD ends up producing nearly the same
query text). These tests demonstrate the fake client is now content-aware - it extracts
different, JD-specific signal - without hard-coding any particular occupation mapping.
"""

from __future__ import annotations

import pytest

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


async def test_role_title_strips_a_job_title_label_prefix():
    """Regression test: many pasted JDs open with a labelled header line ("Job Title: X",
    "Position: X", "Role: X") rather than the bare title. Previously the label was kept
    verbatim as the extracted role_title and then leaked into every generated question (e.g.
    "As a Job Title: Digital Marketing Specialist, tell me about a time you demonstrated
    Leadership."). Only the title itself should be extracted.
    """
    for label in ("Job Title:", "Job Title -", "Title:", "Position:", "Role:"):
        spec = await _analyze(f"{label} Digital Marketing Specialist\n\nSome JD body text.")
        assert spec.role_title == "Digital Marketing Specialist", label


# --- role-title extraction: a JD that opens with a sentence, not a title line ---------------
#
# Regression test for the reported bug: "We are looking for AI Engineer, she must have
# pre-knowledge of deep learning models and transformers, computer vision and NLP. With strong
# skill in communication and team work" - all on one line, with no standalone title line at
# all - previously produced a role_title containing the entire paragraph. The extractor must
# recognize generic hiring-intro phrasing, not any specific role name.

SHORT_AI_ENGINEER_JD = (
    "We are looking for AI Engineer, she must have pre-knowledge of deep learning models "
    "and transformers, computer vision and NLP. With strong skill in communication and team "
    "work"
)


@pytest.mark.parametrize(
    ("jd_text", "expected_title"),
    [
        (SHORT_AI_ENGINEER_JD, "AI Engineer"),
        (
            "We are looking for an AI Engineer to design, develop, and deploy ML systems.",
            "AI Engineer",
        ),
        (
            "We are looking for AI Engineer to design, develop, and deploy ML systems.",
            "AI Engineer",
        ),
        (
            "We are seeking a Senior Backend Software Engineer to join our platform team.",
            "Senior Backend Software Engineer",
        ),
        ("We need a Data Analyst who can manage reports.", "Data Analyst"),
        ("Position: AI Engineer\n\nSome JD body text.", "AI Engineer"),
        ("Role: AI Engineer\n\nSome JD body text.", "AI Engineer"),
        ("Job Title: AI Engineer\n\nSome JD body text.", "AI Engineer"),
        (
            "Senior Backend Software Engineer\n\nResponsibilities:\n* Ship things.",
            "Senior Backend Software Engineer",
        ),
    ],
)
async def test_role_title_recognizes_generic_patterns(jd_text, expected_title):
    spec = await _analyze(jd_text)
    assert spec.role_title == expected_title


async def test_role_title_never_becomes_the_entire_jd_paragraph():
    spec = await _analyze(SHORT_AI_ENGINEER_JD)
    assert spec.role_title != SHORT_AI_ENGINEER_JD
    assert len(spec.role_title) < len(SHORT_AI_ENGINEER_JD)
    assert "pre-knowledge" not in spec.role_title


# --- Test A: short, single-line AI Engineer JD (see the module docstring's bug report) ------


async def test_short_ai_engineer_jd_extracts_a_correct_jobspec():
    spec = await _analyze(SHORT_AI_ENGINEER_JD)

    assert spec.role_title == "AI Engineer"

    skill_names = {s.name for s in spec.skills}
    assert {"Deep Learning", "Transformers", "Computer Vision", "Natural Language Processing"} <= (
        skill_names
    )

    competency_names = {c.name for c in spec.competencies}
    assert "Communication" in competency_names
    assert "Collaboration" in competency_names  # "team work" normalizes to this domain concept


# --- responsibilities extraction --------------------------------------------------------


async def test_responsibilities_are_extracted_from_a_responsibilities_section():
    spec = await _analyze(AI_ENGINEER_JD)
    assert spec.responsibilities
    assert any("machine learning" in r.lower() for r in spec.responsibilities)
    # No healthcare-domain responsibility should be invented for an unrelated JD.
    assert not any("patient" in r.lower() for r in spec.responsibilities)


async def test_no_responsibilities_section_means_empty_list():
    """A short, unstructured JD with no "Responsibilities:" heading yields no invented tasks."""
    spec = await _analyze(SHORT_AI_ENGINEER_JD)
    assert spec.responsibilities == []
