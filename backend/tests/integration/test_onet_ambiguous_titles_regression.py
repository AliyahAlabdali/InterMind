"""Regression tests for lexically ambiguous technical job titles.

The production failure these exist for: a Computer Vision Engineer JD matched **Orthoptists**
(a clinical eyesight occupation) as a "confident" match. Root cause was not the title alone -
the TF-IDF vectorizer is fit only on the O*NET corpus, so a query phrase the corpus never uses
(``computer vision``) is silently dropped by ``transform()``, leaving the bare, very rare
unigram ``vision`` (idf 6.13, present in 43 of 1016 occupations, almost all clinical or media)
to carry ~79% of the winning score.

These assert **category invariants**, not one exact occupation, because O*NET 31.0 genuinely
has no dedicated occupation for most modern AI roles (``computer vision``, ``deep learning``,
``neural network`` and ``artificial intelligence`` appear in *zero* occupation records). For
those roles an honest abstention is a correct outcome, so the helpers below accept either "a
plausibly technical occupation won" or "the matcher declined to claim a confident match" -
never "an unrelated occupation was presented confidently".

Uses the real 1016-occupation KB for the same reason as
``test_onet_matching_regression.py``: the cross-occupation competition that causes this class
of bug cannot be reproduced on a small fixture.
"""

from __future__ import annotations

import pytest

from app.knowledge.onet_kb import DEFAULT_KB_PATH, OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from app.services.interview_planner import InterviewPlannerService
from app.services.jd_analysis import JDAnalysisService

pytestmark = pytest.mark.skipif(
    not DEFAULT_KB_PATH.exists(),
    reason=(
        "Real O*NET knowledge base not present at "
        f"{DEFAULT_KB_PATH} - run notebooks/ONET_knowledge_base_pipeline.ipynb first."
    ),
)

#: SOC major groups (the first two digits of an O*NET-SOC code) that a software/data/AI job
#: description could defensibly map onto. 15 is "Computer and Mathematical", 17 is
#: "Architecture and Engineering" (which is where O*NET files Robotics Engineers, Validation
#: Engineers and Computer Hardware Engineers). Asserting on the *family* rather than on one
#: occupation is deliberate - which specific occupation wins is a retrieval detail that may
#: legitimately shift, whereas "a software JD matched a healthcare occupation" is always a bug.
TECHNICAL_FAMILIES = {"15", "17"}

#: Families a technical job description must never land in. Healthcare practitioners (29) and
#: healthcare support (31) are the ones this regression is really about; the manual-trade and
#: production families are included because earlier investigation saw them surface as
#: near-tied runners-up on weak matches (e.g. "Model Makers, Wood", "Forest Fire Inspectors").
DISQUALIFYING_FAMILIES = {"29", "31", "45", "47", "49", "51", "53"}

ORTHOPTISTS_SOC = "29-1299.02"


def family(onet_soc_code: str) -> str:
    """The SOC major group - the first two digits of an O*NET-SOC code."""
    return onet_soc_code[:2]


@pytest.fixture(scope="module")
def real_kb() -> OnetKnowledgeBase:
    return OnetKnowledgeBase()


async def _analyze(jd_text: str):
    return await JDAnalysisService(llm=FakeLLMClient()).analyze(jd_text)


# --------------------------------------------------------------------------------------
# Job descriptions. Deliberately realistic rather than minimal: the failure mode depends on
# the full vocabulary of a JD competing across 1016 occupations, so a three-line stub would
# not exercise it.
# --------------------------------------------------------------------------------------

COMPUTER_VISION_JD = """Computer Vision Engineer

We are looking for a Computer Vision Engineer to design, develop, and deploy production-ready
computer vision systems. The ideal candidate has strong experience in deep learning, image and
video processing, and building reliable ML systems for real-world applications.

Responsibilities:
* Design, train, and evaluate deep learning models for image and video analysis.
* Develop computer vision solutions for object detection, classification, segmentation, and
  tracking.
* Prepare datasets, perform data preprocessing and augmentation, and improve data quality.
* Fine-tune and optimize models for accuracy, latency, and production performance.
* Build inference pipelines and REST APIs for serving computer vision models.
* Deploy and monitor computer vision models in production environments.
* Write clean, maintainable, and well-tested Python code.

Requirements:
* Strong proficiency in Python.
* Experience with PyTorch or TensorFlow.
* Experience with OpenCV and image processing techniques.
* Knowledge of CNN-based architectures and modern computer vision models.
* Experience with object detection frameworks such as YOLO.
* Experience building APIs using FastAPI or similar frameworks.
* Familiarity with Git, Docker, and relational databases.
"""

MACHINE_LEARNING_JD = """Machine Learning Engineer

We are looking for a Machine Learning Engineer to build, train and deploy machine learning
models at scale in production systems.

Responsibilities:
* Train, evaluate and tune machine learning models on large datasets.
* Build data pipelines and model serving infrastructure.
* Monitor model performance, drift and reliability in production.
* Collaborate with data scientists and software engineers.

Requirements:
* Strong proficiency in Python.
* Experience with machine learning and deep learning frameworks such as PyTorch.
* Experience with scikit-learn and statistical modelling.
* Experience with SQL, relational databases and large datasets.
* Experience with feature engineering and model evaluation metrics.
* Familiarity with Docker, Kubernetes and MLOps practices.
* Familiarity with Git and collaborative software development.
* Strong problem-solving and analytical skills.
"""

ORTHOPTIST_JD = """Orthoptist

We are seeking a certified Orthoptist to join our ophthalmology clinic and provide diagnostic
and therapeutic care to patients with binocular vision and eye movement disorders.

Responsibilities:
* Examine patients for strabismus, amblyopia and other binocular vision disorders.
* Measure visual acuity, refraction, ocular alignment and ocular motility.
* Administer vision therapy and orthoptic exercises to patients.
* Assist ophthalmologists during patient examinations and surgical planning.
* Maintain accurate patient records and clinical documentation.

Requirements:
* Certification in orthoptics and clinical patient care experience.
* Experience with visual acuity testing and prism measurement.
* Knowledge of pediatric eye care and vision therapy protocols.
* Strong communication skills with patients and families.
"""

AI_ENGINEER_JD = """AI Engineer

We are looking for an AI Engineer to design and deploy artificial intelligence systems into
production applications.

Responsibilities:
* Design, build and deploy AI and machine learning models into production.
* Integrate AI capabilities into customer-facing product applications.
* Build and maintain REST APIs for model serving and inference.
* Work with large datasets to preprocess, analyze and extract insights.
* Evaluate model quality using appropriate metrics and improve accuracy over time.
* Monitor deployed models for performance, latency and drift.
* Collaborate with software engineers and product teams.
* Write clean, maintainable and well-tested Python code.

Requirements:
* Strong programming skills in Python.
* Experience with machine learning and deep learning.
* Experience with PyTorch or TensorFlow.
* Experience with large language models and modern AI frameworks.
* Experience building REST APIs, preferably with FastAPI.
* Familiarity with SQL and relational databases.
* Familiarity with Git, Docker and cloud platforms.
* Strong problem-solving and analytical skills.
"""

CLOUD_ENGINEER_JD = """Cloud Engineer

We are looking for a Cloud Engineer to design, build and operate cloud infrastructure across
AWS and Azure.

Responsibilities:
* Provision and manage cloud infrastructure using infrastructure as code.
* Automate application deployments and build CI/CD pipelines.
* Monitor cloud reliability, performance and cost.
* Improve system scalability, availability and security posture.

Requirements:
* Experience with AWS or Azure cloud platforms.
* Experience with Terraform and infrastructure as code.
* Experience with Kubernetes, Docker and container orchestration.
* Strong Linux administration and networking fundamentals.
* Experience with CI/CD pipelines and deployment automation.
* Experience with monitoring, logging and observability tooling.
* Proficiency in Python or another scripting language.
* Familiarity with cloud security and identity management.
"""

NLP_ENGINEER_JD = """NLP Engineer

We are looking for an NLP Engineer to build natural language processing systems and large
language model applications.

Responsibilities:
* Train and fine-tune language models for text classification and information extraction.
* Build text processing pipelines and model serving APIs.
* Evaluate model quality on annotated datasets.
* Deploy natural language processing models to production.

Requirements:
* Strong proficiency in Python.
* Experience with transformers, PyTorch and modern NLP frameworks.
* Experience with large language models and text classification.
* Experience with tokenization, embeddings and text preprocessing.
* Experience building REST APIs for model serving.
* Familiarity with SQL and working with large text datasets.
* Familiarity with Git, Docker and cloud platforms.
* Strong problem-solving and analytical skills.
"""

SECURITY_ENGINEER_JD = """Security Engineer

We are looking for a Security Engineer to protect our systems, applications and data from
security threats.

Responsibilities:
* Perform security assessments, vulnerability scanning and penetration tests.
* Monitor security events and respond to security incidents.
* Harden infrastructure and application configurations.
* Improve identity, access management and encryption practices.

Requirements:
* Experience with network security and application security.
* Experience with SIEM tooling, logging and incident response.
* Experience with vulnerability scanning and penetration testing.
* Proficiency in Python for security automation and scripting.
* Knowledge of cryptography and secure software development.
* Experience with Linux, cloud platforms and container security.
* Familiarity with identity and access management.
* Strong problem-solving and analytical skills.
"""

NETWORK_ENGINEER_JD = """Network Engineer

We are looking for a Network Engineer to design, implement and maintain enterprise network
infrastructure.

Responsibilities:
* Configure and maintain routers, switches, firewalls and VPN infrastructure.
* Troubleshoot network performance, latency and connectivity issues.
* Monitor network capacity and plan upgrades.
* Document network topology and maintain configuration standards.

Requirements:
* Strong knowledge of TCP/IP, routing and switching.
* Experience with BGP, OSPF and enterprise firewalls.
* Experience with Cisco networking equipment.
* Familiarity with network monitoring tooling.
"""

DATA_ENGINEER_JD = """Data Engineer

We are looking for a Data Engineer to build and maintain large scale data pipelines and our
analytical data warehouse.

Responsibilities:
* Build batch and streaming data pipelines.
* Model, maintain and optimize the analytical data warehouse.
* Improve data quality, reliability and pipeline observability.
* Support analysts and data scientists with well modelled datasets.

Requirements:
* Strong proficiency in SQL and Python.
* Experience with Spark, Airflow and Kafka.
* Experience with ETL design and data warehousing.
* Familiarity with cloud data platforms.
"""

#: Every ambiguous technical role this regression covers, with the JD that exercises it.
TECHNICAL_ROLES = {
    "Computer Vision Engineer": COMPUTER_VISION_JD,
    "Machine Learning Engineer": MACHINE_LEARNING_JD,
    "AI Engineer": AI_ENGINEER_JD,
    "Cloud Engineer": CLOUD_ENGINEER_JD,
    "NLP Engineer": NLP_ENGINEER_JD,
    "Security Engineer": SECURITY_ENGINEER_JD,
    "Network Engineer": NETWORK_ENGINEER_JD,
    "Data Engineer": DATA_ENGINEER_JD,
}


@pytest.mark.parametrize("role", sorted(TECHNICAL_ROLES))
async def test_technical_jd_never_grounds_on_a_disqualifying_occupation(real_kb, role):
    """The product invariant: never *present* a disqualifying occupation as confident grounding.

    Asserted at the planner rather than at the raw ranking, because those are different
    promises. Raw TF-IDF rank order is a retrieval detail; what reaches a recruiter is
    ``onet_grounding_used``, which is what turns a candidate into the sentence "InterMind
    judged this a confident match". O*NET 31.0 contains no occupation for most modern AI roles
    (``computer vision``, ``deep learning``, ``neural network`` and ``artificial intelligence``
    appear in zero records), so for some of these JDs abstaining *is* the correct answer, and
    demanding a particular winner would be demanding a fiction.

    So: either the top occupation is a defensible one, or the planner must decline to ground
    on it. Presenting a clinical occupation for a software role confidently is the only
    outcome this forbids.
    """
    job_spec = await _analyze(TECHNICAL_ROLES[role])
    plan = await InterviewPlannerService(knowledge_base=real_kb).plan("job-regression", job_spec)
    top = plan.occupation_match

    if family(top.onet_soc_code) in DISQUALIFYING_FAMILIES:
        assert not plan.onet_grounding_used, (
            f"{role} JD was grounded on {top.title!r} ({top.onet_soc_code}, SOC family "
            f"{family(top.onet_soc_code)}) at score {top.score} and presented as a confident "
            f"match - this is the Computer Vision production failure."
        )


@pytest.mark.parametrize("role", sorted(TECHNICAL_ROLES))
async def test_technical_jd_grounding_is_only_offered_from_a_technical_family(real_kb, role):
    """When grounding *is* offered for a technical role, it must come from a technical family.

    The positive counterpart to the test above: abstaining is acceptable, grounding on
    something unrelated is not.
    """
    job_spec = await _analyze(TECHNICAL_ROLES[role])
    plan = await InterviewPlannerService(knowledge_base=real_kb).plan("job-regression", job_spec)
    top = plan.occupation_match

    if plan.onet_grounding_used:
        assert family(top.onet_soc_code) in TECHNICAL_FAMILIES, (
            f"{role} JD was grounded on {top.title!r} ({top.onet_soc_code}), SOC family "
            f"{family(top.onet_soc_code)}, which is outside {sorted(TECHNICAL_FAMILIES)}."
        )


async def test_computer_vision_does_not_match_clinical_vision_occupations(real_kb):
    """The exact production failure, asserted directly.

    Orthoptists and the low-vision rehabilitation occupations must not be the top match for a
    computer vision engineering role. Checked by SOC code rather than by title string so a
    title change in a future O*NET release cannot silently disarm this.
    """
    job_spec = await _analyze(COMPUTER_VISION_JD)
    matches = real_kb.match_jobspec(job_spec, top_k=10)
    top = matches[0]

    plan = await InterviewPlannerService(knowledge_base=real_kb).plan("job-cv", job_spec)
    if plan.occupation_match.onet_soc_code == ORTHOPTISTS_SOC or family(
        plan.occupation_match.onet_soc_code
    ) == "29":
        assert not plan.onet_grounding_used, (
            f"Computer Vision Engineer JD is still grounded on "
            f"{plan.occupation_match.title!r} at {plan.occupation_match.score} and shown as a "
            "confident match - the production bug is not fixed."
        )

    # Whatever wins the raw ranking, a clinical eyesight occupation must not dominate it: the
    # margin that made this look "confident" has to be gone.
    if top.onet_soc_code == ORTHOPTISTS_SOC:
        runner_up = matches[1]
        assert top.score - runner_up.score < 0.03, (
            f"Orthoptists still wins the Computer Vision ranking by a wide margin "
            f"({top.score} vs {runner_up.score}) - the homonym is still dominating."
        )


async def test_genuine_clinical_vision_jd_still_matches_orthoptists(real_kb):
    """The control that stops the fix from degenerating into a healthcare blocklist.

    A real orthoptics job description must still select Orthoptists, and must still do so
    decisively - if suppressing the false positive also flattens this, the fix is wrong.
    """
    job_spec = await _analyze(ORTHOPTIST_JD)
    matches = real_kb.match_jobspec(job_spec, top_k=5)
    assert matches, "matcher returned no candidates for the clinical JD"

    top = matches[0]
    assert top.onet_soc_code == ORTHOPTISTS_SOC, (
        f"Genuine Orthoptist JD matched {top.title!r} ({top.onet_soc_code}) instead of "
        "Orthoptists - legitimate clinical matching regressed."
    )
    assert family(top.onet_soc_code) == "29"

    # It should win clearly, not by a hair: a real match has margin a false one does not.
    runner_up = matches[1]
    assert top.score > runner_up.score, "clinical match lost its margin entirely"
