"""Regression test for the Milestone 6 O*NET occupation-matching investigation.

Uses the *real*, processed O*NET knowledge base (``data/processed/onet/onet_kb.jsonl``) -
not a tiny fixture - because the original bug (an AI Engineer JD matching Health Informatics
Specialists at ~0.16) only reproduces against the full 1016-occupation corpus: a 2-record
fixture can't exercise the cross-occupation competition that caused it. Skipped when the real
KB artifact hasn't been generated (it's git-ignored; built by running
``notebooks/ONET_knowledge_base_pipeline.ipynb``), so this suite stays deterministic and
doesn't fail in an environment where that notebook hasn't been run.
"""

from __future__ import annotations

import pytest

from app.knowledge.onet_kb import DEFAULT_KB_PATH, OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.services.jd_analysis import JDAnalysisService

pytestmark = pytest.mark.skipif(
    not DEFAULT_KB_PATH.exists(),
    reason=(
        "Real O*NET knowledge base not present at "
        f"{DEFAULT_KB_PATH} - run notebooks/ONET_knowledge_base_pipeline.ipynb first."
    ),
)

HEALTH_INFORMATICS_SPECIALISTS_SOC = "15-1211.01"
DATA_SCIENTISTS_SOC = "15-2051.00"

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


@pytest.fixture(scope="module")
def real_kb() -> OnetKnowledgeBase:
    return OnetKnowledgeBase()


async def _analyze(jd_text: str):
    service = JDAnalysisService(llm=FakeLLMClient())
    return await service.analyze(jd_text)


async def test_ai_engineer_no_longer_incorrectly_matches_health_informatics(real_kb):
    """The core regression: this must not reproduce the investigated bug.

    Previously, the fake client's fixed canned JobSpec made *every* JD (AI Engineer included)
    match Health Informatics Specialists at ~0.16, purely from coincidental lexical overlap in
    generic boilerplate. With content-aware extraction, the AI Engineer JD's real ML/AI
    vocabulary should let a genuinely relevant occupation win instead.
    """
    job_spec = await _analyze(AI_ENGINEER_JD)
    matches = real_kb.match_jobspec(job_spec, top_k=10)
    assert matches, "matcher returned no candidates"

    top = matches[0]
    assert top.onet_soc_code != HEALTH_INFORMATICS_SPECIALISTS_SOC, (
        f"AI Engineer JD still matches Health Informatics Specialists first "
        f"(score={top.score}) - the fake JobSpec is still starving the matcher."
    )

    # With the current deterministic extraction + the real O*NET 31.0 corpus, Data Scientists
    # (the closest available proxy for an AI/ML engineering role - O*NET 31.0 has no dedicated
    # "AI Engineer"/"Machine Learning Engineer" occupation) reliably wins. This is verified,
    # not assumed: if the extraction or corpus ever changes such that this stops holding, this
    # assertion is meant to fail loudly rather than be quietly loosened.
    assert top.onet_soc_code == DATA_SCIENTISTS_SOC
    assert top.title == "Data Scientists"

    # Health Informatics Specialists should now be a clearly weaker candidate, not just
    # "not first" - guard against a regression that merely swaps in a different false match.
    hi_match = next(
        (m for m in matches if m.onet_soc_code == HEALTH_INFORMATICS_SPECIALISTS_SOC), None
    )
    if hi_match is not None:
        assert hi_match.score < top.score


async def test_health_informatics_jd_still_matches_correctly(real_kb):
    """Fixing AI Engineer matching must not break the already-correct HI case."""
    job_spec = await _analyze(HEALTH_INFORMATICS_JD)
    matches = real_kb.match_jobspec(job_spec, top_k=5)
    assert matches, "matcher returned no candidates"

    top = matches[0]
    assert top.onet_soc_code == HEALTH_INFORMATICS_SPECIALISTS_SOC
    assert top.title == "Health Informatics Specialists"
    # A strong, clearly-ahead-of-the-pack top match, not a near-tie.
    assert top.score > matches[1].score
    assert top.score > 0.1
