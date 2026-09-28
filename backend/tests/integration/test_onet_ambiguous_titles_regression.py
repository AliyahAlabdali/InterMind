"""Regression tests for O*NET grounding on lexically ambiguous job titles.

The production failure these exist for: a Computer Vision Engineer job description was
presented to a recruiter as *"O*NET's Orthoptists occupation profile, which it judged a
confident match"*. Orthoptists is clinical eye care. It won because the query encoded one
concept three times - ``computer vision`` + ``vision`` + ``computer`` - and almost no
occupation record contains the adjacent phrase, so the rare unigram ``vision`` (present in 43
of 1016 occupations, nearly all clinical) supplied 85% of the score on its own.

**These assert product behaviour, not ranking.** What reaches a recruiter is
``onet_grounding_used`` - the flag that turns a candidate into the sentence claiming a
confident match. Raw rank order is an internal retrieval detail that may legitimately shift,
and O*NET 31.0 genuinely has no occupation for several modern roles, so for those an honest
abstention is the correct answer. Requiring a particular winner would be requiring a fiction.

**Variants, not single samples.** Each role is asserted across a spread of realistic JobSpec
shapes. The bug that shipped before was verified against exactly one sampled JobSpec whose
confidence ratio happened to land 0.0014 below a threshold; across realistic variation the
same role failed most of the time. Proportions over a variant set are the only assertion that
catches that, so that is what these tests use.

JobSpecs are built directly rather than analysed from JD text: production uses a real model
whose output is richer than ``FakeLLMClient``'s fixed extraction vocabulary (which returns
zero skills for several of these roles), and it is production's shape that matters here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import pytest

from app.domain.job import Competency, JobSpec, Seniority, Skill
from app.knowledge.onet_kb import DEFAULT_KB_PATH, OnetKnowledgeBase
from app.services.interview_planner import InterviewPlannerService

pytestmark = pytest.mark.skipif(
    not DEFAULT_KB_PATH.exists(),
    reason=(
        "Real O*NET knowledge base not present at "
        f"{DEFAULT_KB_PATH} - run notebooks/ONET_knowledge_base_pipeline.ipynb first."
    ),
)

#: SOC major groups (first two digits of an O*NET-SOC code) a role may defensibly ground to.
#: Asserting on the family rather than one occupation keeps these tests honest about the fact
#: that several occupations can be reasonable for the same job description.
COMPUTER = "15"
ENGINEERING = "17"

#: O*NET's Robotics Engineers. Singled out because exactly one task in the whole 1016-occupation
#: corpus names computer vision - *"Design robotic systems, such as automatic vehicle control,
#: autonomous vehicles, advanced displays, advanced sensing, robotic platforms, computer vision,
#: or telematics systems."* - which is enough to make it the top match for any computer-vision
#: job description, robotics or not. Whether that is a *defensible* match depends entirely on
#: whether the job description mentions robots.
ROBOTICS_ENGINEERS = "17-2199.08"
BUSINESS = "13"
MANAGEMENT = "11"
SCIENCE = "19"
HEALTHCARE = "29"
HEALTHCARE_SUPPORT = "31"

_COMPETENCIES = [
    Competency(name="Problem-Solving", description="Strong analytical problem solving"),
    Competency(name="Communication", description="Clear written and verbal communication"),
]


def job_spec(
    title: str,
    summary: str,
    required: list[str],
    responsibilities: list[str],
    preferred: list[str] | None = None,
    seniority: Seniority = Seniority.MID,
) -> JobSpec:
    """A production-shaped JobSpec: prose summary, required + preferred skills, duties."""
    return JobSpec(
        role_title=title,
        seniority=seniority,
        summary=summary,
        skills=[Skill(name=n, required=True) for n in required]
        + [Skill(name=n, required=False) for n in (preferred or [])],
        competencies=list(_COMPETENCIES),
        responsibilities=responsibilities,
    )


def variants(spec: JobSpec) -> list[JobSpec]:
    """Eight deterministic perturbations of one JobSpec.

    Models the variation a real extraction model produces for the same job description:
    different summary phrasing, a shorter skill list, fewer captured duties, a different
    stated seniority. Deterministic, so any failure is reproducible.
    """
    shorter = spec.skills[: max(4, len(spec.skills) - 3)]
    trimmed = spec.responsibilities[: max(2, len(spec.responsibilities) - 1)]
    first_sentence = (spec.summary or "").split(".")[0] + "."

    shapes: list[dict] = [
        {},
        {"summary": first_sentence},
        {"skills": shorter},
        {"responsibilities": trimmed},
        {"summary": first_sentence, "skills": shorter},
        {"skills": shorter, "responsibilities": trimmed},
        {"seniority": Seniority.SENIOR},
        {"seniority": Seniority.UNKNOWN, "responsibilities": trimmed},
    ]
    built = []
    for shape in shapes:
        variant = copy.deepcopy(spec)
        for field, value in shape.items():
            setattr(variant, field, value)
        built.append(variant)
    return built


@dataclass(frozen=True)
class Role:
    """One role under test, with the behaviour its job description must produce."""

    spec: JobSpec
    allowed_families: frozenset[str]
    #: Minimum fraction of variants that must be grounded. ``0.0`` means abstention is
    #: acceptable; a positive value is an over-abstention guard.
    min_grounded: float
    #: Occupations this particular job description must never be grounded on, even though
    #: their SOC family is otherwise allowed.
    #:
    #: A SOC major group is a coarse instrument. Family 17 ("Architecture and Engineering")
    #: legitimately covers Robotics Engineers for a robotics job description and is equally
    #: legitimate for Computer Hardware Engineers - so the family alone cannot say whether a
    #: given occupation suits a *given* job description. Production showed why that matters: a
    #: pure computer-vision role was grounded on Robotics Engineers, and the family check
    #: passed it silently.
    #:
    #: Kept per-Role rather than global, because the same occupation is right for one JD and
    #: wrong for another - compare ``COMPUTER_VISION`` with ``COMPUTER_VISION_ROBOTICS`` below.
    #: This is an expectation about a job description, not a ban on an occupation.
    forbidden_codes: frozenset[str] = frozenset()


def _role(
    spec: JobSpec,
    families: set[str],
    min_grounded: float,
    forbidden: set[str] | None = None,
) -> Role:
    return Role(spec, frozenset(families), min_grounded, frozenset(forbidden or ()))


# --------------------------------------------------------------------------------------
# Adversarial: roles whose title shares a word with an unrelated occupational domain.
# --------------------------------------------------------------------------------------
COMPUTER_VISION = _role(
    job_spec(
        "Computer Vision Engineer",
        "The Computer Vision Engineer will design and develop production-ready computer vision "
        "systems, focusing on deep learning and image processing. This role involves building "
        "and optimizing models, developing APIs, and collaborating with teams.",
        ["Python", "Deep Learning", "Image Processing", "Video Processing", "PyTorch",
         "TensorFlow", "OpenCV", "YOLO", "FastAPI", "Git", "Docker", "Relational Databases"],
        ["Design, train, and evaluate deep learning models for image and video analysis.",
         "Develop computer vision solutions for object detection and segmentation.",
         "Build inference pipelines and REST APIs for serving computer vision models.",
         "Deploy and monitor computer vision models in production environments."],
        preferred=["ONNX", "Azure", "AWS"],
    ),
    {COMPUTER, ENGINEERING},
    0.0,  # O*NET 31.0 has no computer-vision occupation; abstention is the honest answer
    forbidden={ROBOTICS_ENGINEERS},
)

#: The counterpart control. Same discipline, but the job description is explicitly about robots
#: - so grounding on Robotics Engineers here is correct, and `forbidden` is deliberately empty.
#: Without this, `forbidden` above would only be tested in the suppressing direction and could
#: quietly harden into "computer vision may never touch robotics".
COMPUTER_VISION_ROBOTICS = _role(
    job_spec(
        "Computer Vision Engineer",
        "The Computer Vision Engineer will build perception systems for autonomous mobile "
        "robots, covering navigation, obstacle avoidance and multi-sensor fusion.",
        ["Python", "Deep Learning", "OpenCV", "PyTorch", "ROS", "Sensor Fusion", "SLAM",
         "Point Clouds", "LiDAR", "Camera Calibration", "Robot Perception", "Navigation"],
        ["Build perception pipelines for autonomous mobile robots.",
         "Implement SLAM, navigation and obstacle avoidance from camera and LiDAR data.",
         "Calibrate cameras and fuse sensor data for robot localization.",
         "Integrate perception modules with robot control systems."],
        preferred=["C++", "Embedded Systems"],
    ),
    {COMPUTER, ENGINEERING},
    0.75,
)

CLOUD_ARCHITECT = _role(
    job_spec(
        "Cloud Architect",
        "The Cloud Architect will design secure, scalable cloud infrastructure and migration "
        "strategies across AWS and Azure, defining landing zones and reference architectures.",
        ["AWS", "Azure", "Terraform", "Kubernetes", "Networking", "Cloud Security",
         "Infrastructure as Code", "Linux", "CI/CD"],
        ["Design cloud reference architectures and landing zones.",
         "Lead cloud migration and modernization efforts.",
         "Define cloud security, networking and cost standards."],
        preferred=["Python", "Cost Optimization"],
    ),
    {COMPUTER, ENGINEERING},
    0.0,
)

# --------------------------------------------------------------------------------------
# Positive technical controls: must keep grounding, or the fix has over-corrected.
# --------------------------------------------------------------------------------------
NETWORK_ENGINEER = _role(
    job_spec(
        "Network Engineer",
        "The Network Engineer will design, implement and maintain enterprise network "
        "infrastructure including routing, switching, firewalls and VPN connectivity.",
        ["TCP/IP", "Routing", "Switching", "BGP", "OSPF", "Cisco", "Firewalls", "VPN",
         "Network Monitoring", "DNS"],
        ["Configure and maintain routers, switches, firewalls and VPN infrastructure.",
         "Troubleshoot network performance, latency and connectivity issues.",
         "Monitor network capacity and plan upgrades."],
        preferred=["Python", "Automation"],
    ),
    {COMPUTER, ENGINEERING},
    0.75,
)

CYBERSECURITY = _role(
    job_spec(
        "Cybersecurity Engineer",
        "The Cybersecurity Engineer will defend systems and data through network and "
        "application security, threat detection, incident response and vulnerability "
        "assessment.",
        ["Network Security", "Application Security", "Threat Detection", "Incident Response",
         "Vulnerability Assessment", "Python", "Linux", "Cloud Security", "SIEM", "Encryption",
         "Identity Management", "TCP/IP", "DNS", "Penetration Testing", "Docker"],
        ["Monitor security events and respond to security incidents.",
         "Perform vulnerability assessments and penetration testing.",
         "Implement authentication, authorization and encryption controls."],
        preferred=["DevSecOps"],
    ),
    {COMPUTER, BUSINESS, MANAGEMENT},
    0.75,
)

DATA_ARCHITECT = _role(
    job_spec(
        "Data Architect",
        "The Data Architect will design and govern relational and non-relational data "
        "platforms, data models, ETL and ELT pipelines and distributed processing on cloud.",
        ["Relational Databases", "Non-Relational Databases", "SQL", "Data Modeling", "ETL",
         "ELT", "Distributed Data Processing", "Cloud Data Platforms", "Python",
         "Data Governance", "Data Quality", "Metadata Management"],
        ["Design relational and non-relational data models.",
         "Build and govern ETL and ELT pipelines.",
         "Define data governance, data quality and metadata standards."],
        preferred=["Snowflake", "Spark"],
    ),
    {COMPUTER},
    0.75,
)

MACHINE_LEARNING = _role(
    job_spec(
        "Machine Learning Engineer",
        "The Machine Learning Engineer will build, train and deploy machine learning models "
        "at scale, owning feature pipelines, model serving and production monitoring.",
        ["Python", "Machine Learning", "Deep Learning", "PyTorch", "scikit-learn", "SQL",
         "Feature Engineering", "Docker", "Kubernetes"],
        ["Train, evaluate and tune machine learning models on large datasets.",
         "Build feature pipelines and model serving infrastructure.",
         "Monitor model performance and drift in production."],
        preferred=["MLOps", "Airflow", "AWS"],
    ),
    {COMPUTER, ENGINEERING},
    0.75,
)

ROBOTICS = _role(
    job_spec(
        "Robotics Engineer",
        "The Robotics Engineer will design and program robotic systems, integrating sensors, "
        "actuators, control loops and motion planning for automated hardware.",
        ["ROS", "C++", "Python", "Control Systems", "Sensors", "Motion Planning", "Kinematics"],
        ["Design and program robotic control systems.",
         "Integrate sensors and actuators into robotic platforms.",
         "Test and calibrate robot motion and perception."],
        preferred=["Computer Vision", "Embedded Systems"],
    ),
    {ENGINEERING, COMPUTER},
    0.75,
)

# --------------------------------------------------------------------------------------
# Clinical controls: the fix must not become a healthcare blocklist.
# --------------------------------------------------------------------------------------
ORTHOPTIST = _role(
    job_spec(
        "Orthoptist",
        "The Orthoptist will diagnose and treat binocular vision and eye movement disorders, "
        "working alongside ophthalmologists to deliver patient care.",
        ["Visual Acuity Testing", "Binocular Vision Testing", "Strabismus", "Amblyopia",
         "Ocular Motility", "Prism Measurement", "Vision Therapy", "Patient Assessment"],
        ["Examine patients for strabismus, amblyopia and binocular vision disorders.",
         "Measure visual acuity, refraction and ocular alignment.",
         "Administer vision therapy and orthoptic exercises to patients.",
         "Assist ophthalmologists during patient examinations."],
        preferred=["Pediatric Eye Care"],
    ),
    {HEALTHCARE, HEALTHCARE_SUPPORT},
    1.0,
)

OPTOMETRIST = _role(
    job_spec(
        "Optometrist",
        "The Optometrist will examine patients' eyes, diagnose vision conditions, prescribe "
        "corrective lenses and manage ocular disease in a clinical practice.",
        ["Eye Examination", "Refraction", "Contact Lenses", "Ocular Disease", "Visual Acuity",
         "Prescribing", "Patient Care"],
        ["Examine patients' eyes and diagnose vision conditions.",
         "Prescribe and fit eyeglasses and contact lenses.",
         "Detect and manage ocular disease and refer to specialists."],
        preferred=["Glaucoma Management"],
    ),
    {HEALTHCARE},
    1.0,
)

# --------------------------------------------------------------------------------------
# Cross-family controls. These forbid any "technical roles may only match SOC 15/17" rule
# from creeping back in: Clinical Data Manager is a healthcare-domain job that correctly
# grounds to a *computer* occupation, and building Architect is a non-software "Architect".
# --------------------------------------------------------------------------------------
CLINICAL_DATA_MANAGER = _role(
    job_spec(
        "Clinical Data Manager",
        "The Clinical Data Manager will oversee clinical trial data collection, validation and "
        "cleaning, ensuring regulatory compliance and data integrity across studies.",
        ["Clinical Trials", "Data Management", "CDISC", "Data Validation", "EDC Systems",
         "SQL", "Regulatory Compliance", "Query Resolution"],
        ["Design clinical trial databases and data collection forms.",
         "Validate and clean clinical trial data.",
         "Ensure compliance with regulatory and data integrity standards."],
        preferred=["SAS", "Medical Coding"],
    ),
    {COMPUTER, SCIENCE, HEALTHCARE},
    0.75,
)

BUILDING_ARCHITECT = _role(
    job_spec(
        "Architect",
        "The Architect will design residential and commercial buildings, produce drawings and "
        "specifications, and coordinate with engineers and contractors through construction.",
        ["Architectural Design", "AutoCAD", "Revit", "Building Codes", "Construction Documents",
         "Site Planning", "Structural Coordination"],
        ["Design building layouts and produce construction drawings.",
         "Ensure designs comply with building codes and regulations.",
         "Coordinate with structural engineers and contractors on site."],
        preferred=["BIM", "Sustainable Design"],
    ),
    {ENGINEERING},
    0.75,
)

#: Data Scientist abstains under the grounding rule, and that is intended: its matched
#: occupation's O*NET duties ("analyze data", "apply statistical techniques") are too generic
#: to corroborate any particular data job, scoring 0.063-0.066 against the 0.10 floor.
#: Recorded as an explicit expectation so nobody "fixes" it by lowering the threshold.
DATA_SCIENTIST = _role(
    job_spec(
        "Data Scientist",
        "The Data Scientist will analyze large datasets, build statistical and machine "
        "learning models, and communicate insights that drive product decisions.",
        ["Python", "Statistics", "Machine Learning", "SQL", "Data Analysis", "Visualization",
         "Experimentation"],
        ["Analyze large datasets to extract actionable insights.",
         "Build and validate statistical and machine learning models.",
         "Design experiments and communicate findings to stakeholders."],
        preferred=["R", "PyTorch"],
    ),
    {COMPUTER, SCIENCE},
    0.0,
)

ROLES: dict[str, Role] = {
    "Computer Vision Engineer": COMPUTER_VISION,
    "Computer Vision Engineer (robotics)": COMPUTER_VISION_ROBOTICS,
    "Cloud Architect": CLOUD_ARCHITECT,
    "Network Engineer": NETWORK_ENGINEER,
    "Cybersecurity Engineer": CYBERSECURITY,
    "Data Architect": DATA_ARCHITECT,
    "Machine Learning Engineer": MACHINE_LEARNING,
    "Robotics Engineer": ROBOTICS,
    "Orthoptist": ORTHOPTIST,
    "Optometrist": OPTOMETRIST,
    "Clinical Data Manager": CLINICAL_DATA_MANAGER,
    "Architect (building)": BUILDING_ARCHITECT,
    "Data Scientist": DATA_SCIENTIST,
}


@pytest.fixture(scope="module")
def planner() -> InterviewPlannerService:
    """One KB load for the whole module: building it vectorizes 1016 occupations."""
    return InterviewPlannerService(knowledge_base=OnetKnowledgeBase())


async def _ground(planner: InterviewPlannerService, spec: JobSpec) -> tuple[bool, str, str]:
    """``(grounding_used, soc_code, title)`` for one JobSpec, through the real plan path."""
    plan = await planner.plan("job-regression", spec)
    match = plan.occupation_match
    return plan.onet_grounding_used, match.onet_soc_code, match.title


@pytest.mark.parametrize("role_name", sorted(ROLES))
async def test_grounding_never_claims_an_out_of_domain_occupation(planner, role_name):
    """The invariant the production failure violated.

    Abstaining is always allowed. Claiming a *confident match* to an occupation outside the
    role's defensible families never is - that is the sentence a recruiter reads.
    """
    role = ROLES[role_name]
    wrong_family = set()
    forbidden = set()
    for spec in variants(role.spec):
        grounded, code, title = await _ground(planner, spec)
        if not grounded:
            continue
        if code[:2] not in role.allowed_families:
            wrong_family.add(f"{title} ({code})")
        if code in role.forbidden_codes:
            forbidden.add(f"{title} ({code})")

    assert not wrong_family, (
        f"{role_name} was grounded on out-of-domain occupation(s) {sorted(wrong_family)} and "
        f"presented as a confident match; allowed SOC families are "
        f"{sorted(role.allowed_families)}."
    )
    assert not forbidden, (
        f"{role_name} was grounded on {sorted(forbidden)} and presented as a confident match. "
        "That occupation's SOC family is allowed in general, but this job description does not "
        "support it - see this Role's forbidden_codes for why."
    )


@pytest.mark.parametrize("role_name", sorted(ROLES))
async def test_grounding_is_retained_where_the_match_is_genuine(planner, role_name):
    """The over-abstention guard: suppressing false positives must not silence real ones."""
    role = ROLES[role_name]
    specs = variants(role.spec)
    grounded = 0
    for spec in specs:
        used, _, _ = await _ground(planner, spec)
        grounded += int(used)

    fraction = grounded / len(specs)
    assert fraction >= role.min_grounded, (
        f"{role_name} grounded on only {grounded}/{len(specs)} variants ({fraction:.0%}), "
        f"below the {role.min_grounded:.0%} floor - the confidence rule is over-abstaining "
        "on a role whose match is genuine."
    )


async def test_computer_vision_never_grounds_on_clinical_eye_care(planner):
    """The exact production failure, stated in its own terms.

    Orthoptists may still appear in raw retrieval - that is a retrieval detail. What must never
    happen again is presenting it to a recruiter as a confident match for a software role.
    """
    for spec in variants(COMPUTER_VISION.spec):
        grounded, code, title = await _ground(planner, spec)
        assert not (grounded and code[:2] in {HEALTHCARE, HEALTHCARE_SUPPORT}), (
            f"Computer Vision Engineer was grounded on {title} ({code}) and shown as a "
            "confident match - the production failure has returned."
        )


async def test_clinical_vision_role_still_grounds_decisively(planner):
    """The control that stops the fix from degenerating into a healthcare blocklist.

    A genuine orthoptics job description must still reach Orthoptists on every variant. If
    suppressing the false positive also silences this, the fix is wrong.
    """
    for spec in variants(ORTHOPTIST.spec):
        grounded, code, title = await _ground(planner, spec)
        assert grounded, "genuine Orthoptist JD lost its O*NET grounding"
        assert code[:2] == HEALTHCARE, f"clinical JD grounded on {title} ({code})"
