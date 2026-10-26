"""Labelled JobSpec -> O*NET occupation set, for measuring `OnetKnowledgeBase.match_jobspec`.

**What this measures and what it does not.** The production path is
``JD text -> (LLM) -> JobSpec -> (TF-IDF) -> occupation``. This dataset supplies the
``JobSpec`` directly, so it isolates the *retrieval* stage: results here are unaffected by
model choice, temperature, or prompt version, and the whole harness runs offline with no API
key. It therefore says nothing about how faithfully the LLM extracts a JobSpec from raw prose,
which remains unmeasured.

**How the labels were built.** Each case was written as a realistic posting - the role title,
summary, skills, competencies and responsibilities a recruiter would plausibly write - in the
author's own words, deliberately *not* by paraphrasing the target occupation's O*NET
description or task list. The corpus side matches against title + description + technologies +
core tasks (see ``_occupation_matching_text``), so reusing that text as the query would measure
string identity rather than retrieval. The ground truth is the occupation whose O*NET
definition covers the role, taken from O*NET 31.0 SOC codes present in this KB.

**Why ``acceptable`` is a set, not one code.** O*NET draws boundaries that real postings
straddle: a "Computer Vision Engineer" is defensibly Computer and Information Research
Scientists *or* Software Developers, and an ML platform role spans Software Developers and
Data Scientists. Scoring such a case against a single arbitrary code would measure the
author's tie-breaking, not the retriever. So each case lists every occupation a domain reader
would accept, with the most defensible first; a hit means the returned code is in that set.

Two rules keep that set from becoming a way to manufacture a better score, and both are applied
to every case up front rather than to whichever cases happened to fail:

* **Same-family variants are acceptable.** O*NET nests detailed occupations under a 6-digit SOC
  base (``13-1081.00`` Logisticians, ``.01`` Logistics Engineers, ``.02`` Logistics Analysts;
  ``17-2112.00`` Industrial Engineers and ``.03`` Manufacturing Engineers). Where a posting does
  not distinguish between siblings, all siblings count.
* **Credential-level variants are not acceptable.** Technologist, technician, assistant and aide
  occupations are excluded even when they are the nearest neighbour - Physical Therapist
  Assistants is not a hit for a Physical Therapist posting, and Industrial Engineering
  Technologists is not a hit for an Industrial Engineer posting. Collapsing those would hide the
  exact confusion a hiring tool must not make.

This is an author-constructed set, which is its main limitation: 30 cases, labelled by one
person, with no inter-annotator agreement. It is sized to detect large regressions and to
compare retriever variants against each other, not to certify an absolute accuracy figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.job import Competency, JobSpec, Seniority, Skill


@dataclass(frozen=True)
class RetrievalCase:
    """One labelled job description and the occupations that count as a correct match."""

    case_id: str
    job_spec: JobSpec
    acceptable: tuple[str, ...]
    #: True when more than one O*NET occupation defensibly covers this role.
    ambiguous: bool = False
    #: Free-text note on why the label is what it is, for cases that need one.
    note: str = ""
    tags: tuple[str, ...] = field(default=())


def _spec(
    role_title: str,
    seniority: Seniority,
    summary: str,
    required: list[str],
    preferred: list[str],
    competencies: list[tuple[str, str]],
    responsibilities: list[str],
) -> JobSpec:
    return JobSpec(
        role_title=role_title,
        seniority=seniority,
        summary=summary,
        skills=[Skill(name=n, required=True) for n in required]
        + [Skill(name=n, required=False) for n in preferred],
        competencies=[Competency(name=n, description=d) for n, d in competencies],
        responsibilities=responsibilities,
    )


CASES: tuple[RetrievalCase, ...] = (
    RetrievalCase(
        case_id="backend-engineer",
        tags=("software",),
        acceptable=("15-1252.00",),
        job_spec=_spec(
            "Senior Backend Engineer",
            Seniority.SENIOR,
            "Own the services behind our payments product and the APIs other teams build on.",
            ["Python", "PostgreSQL", "Docker", "Kubernetes", "REST APIs"],
            ["Kafka", "Terraform"],
            [
                ("System design", "Designs services that stay correct under load and failure."),
                ("Code quality", "Writes reviewable, well-tested code others can extend."),
            ],
            [
                "Design and ship HTTP services that handle payment authorisation.",
                "Write migrations and keep the relational schema coherent as it grows.",
                "Review teammates' pull requests and raise the bar on test coverage.",
                "Debug production incidents and write the follow-up postmortem.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="frontend-engineer",
        tags=("software",),
        acceptable=("15-1254.00", "15-1255.00", "15-1252.00"),
        ambiguous=True,
        note=(
            "Web Developers covers browser-facing build, Web and Digital Interface Designers "
            "the interface layer, and a React app role also reads as Software Developers."
        ),
        job_spec=_spec(
            "Frontend Engineer",
            Seniority.MID,
            "Build the customer-facing web application and the component library behind it.",
            ["JavaScript", "TypeScript", "React", "HTML", "CSS"],
            ["Figma", "Webpack"],
            [
                ("Accessibility", "Builds interfaces usable with a keyboard and a screen reader."),
                ("Visual craft", "Translates a design into a faithful, responsive layout."),
            ],
            [
                "Implement new screens in the web client from design mockups.",
                "Maintain the shared component library and its documentation.",
                "Improve page load time and interaction responsiveness.",
                "Make every new view work on mobile viewports and with assistive technology.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="data-scientist",
        tags=("data",),
        acceptable=("15-2051.00",),
        job_spec=_spec(
            "Data Scientist",
            Seniority.MID,
            "Turn our transaction and behavioural data into models that inform pricing.",
            ["Python", "SQL", "pandas", "scikit-learn", "Statistics"],
            ["Spark", "Airflow"],
            [
                (
                    "Statistical reasoning",
                    "Chooses methods that fit the data and states assumptions.",
                ),
                ("Communication", "Explains a model's limits to a non-technical audience."),
            ],
            [
                "Build predictive models of customer churn and lifetime value.",
                "Design and read out A/B experiments for the pricing team.",
                "Clean and join large datasets drawn from several internal systems.",
                "Present findings and recommendations to product leadership.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="ml-engineer",
        tags=("data", "software"),
        acceptable=("15-1252.00", "15-2051.00", "15-1221.00"),
        ambiguous=True,
        note=(
            "Productionising models spans Software Developers, Data Scientists and research "
            "scientists."
        ),
        job_spec=_spec(
            "Machine Learning Engineer",
            Seniority.SENIOR,
            "Take models from a notebook to a served, monitored production endpoint.",
            ["Python", "PyTorch", "Docker", "Kubernetes", "MLflow"],
            ["Ray", "Feature stores"],
            [
                ("Productionisation", "Turns research code into a reliable served system."),
                ("Measurement", "Instruments model quality and drift after deployment."),
            ],
            [
                "Package trained models behind low-latency inference services.",
                "Build retraining pipelines and track model versions.",
                "Monitor live model accuracy and alert on drift.",
                "Work with scientists to make their prototypes deployable.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="computer-vision-engineer",
        tags=("data", "regression-guard"),
        acceptable=("15-1221.00", "15-2051.00", "15-1252.00", "17-2199.08"),
        ambiguous=True,
        note=(
            "The case documented in FRAGMENT_WEIGHT: query-side 'computer vision' / 'vision' / "
            "'computer' redundancy once matched Orthoptists, a clinical eye-care occupation. Any "
            "computing or robotics occupation counts as a hit; a clinical one does not."
        ),
        job_spec=_spec(
            "Computer Vision Engineer",
            Seniority.SENIOR,
            "Build perception models that let our warehouse robots identify and locate stock.",
            ["Python", "PyTorch", "OpenCV", "Deep learning", "C++"],
            ["CUDA", "ROS"],
            [
                ("Model development", "Trains and evaluates image models against held-out data."),
                ("Optimisation", "Meets latency budgets on constrained on-device hardware."),
            ],
            [
                "Train object detection and segmentation models on warehouse imagery.",
                "Label pipelines and dataset curation for new product categories.",
                "Optimise inference to run on embedded GPUs on the robot itself.",
                "Evaluate model accuracy against held-out scenes and report regressions.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="devops-engineer",
        tags=("software",),
        acceptable=("15-1244.00", "15-1252.00"),
        ambiguous=True,
        note="Platform/SRE work sits between systems administration and software development.",
        job_spec=_spec(
            "DevOps Engineer",
            Seniority.MID,
            "Own the deployment pipeline and the cloud infrastructure our services run on.",
            ["Linux", "AWS", "Terraform", "Kubernetes", "CI/CD"],
            ["Prometheus", "Ansible"],
            [
                ("Reliability", "Designs infrastructure that degrades gracefully."),
                ("Automation", "Replaces manual operational steps with code."),
            ],
            [
                "Maintain Kubernetes clusters and the manifests teams deploy with.",
                "Automate provisioning of cloud resources with infrastructure as code.",
                "Run the on-call rotation and reduce alert noise.",
                "Harden the build and release pipeline against bad deploys.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="security-analyst",
        tags=("software",),
        acceptable=("15-1212.00", "15-1299.05"),
        ambiguous=True,
        note="O*NET splits the analyst and engineer variants of security work.",
        job_spec=_spec(
            "Information Security Analyst",
            Seniority.MID,
            "Detect, investigate and contain threats against our corporate and product estate.",
            ["SIEM", "Incident response", "Network security", "Python", "Threat modelling"],
            ["Penetration testing", "ISO 27001"],
            [
                ("Investigation", "Reconstructs what happened from partial evidence."),
                ("Risk judgement", "Prioritises findings by real exposure, not severity labels."),
            ],
            [
                "Triage security alerts and lead containment during incidents.",
                "Run vulnerability scans and track remediation with service owners.",
                "Review architecture proposals for security weaknesses.",
                "Write detection rules and tune them against false positives.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="database-administrator",
        tags=("software",),
        acceptable=("15-1242.00", "15-1243.00"),
        ambiguous=True,
        note="Operating databases versus designing them are adjacent O*NET occupations.",
        job_spec=_spec(
            "Database Administrator",
            Seniority.SENIOR,
            "Keep our production databases fast, backed up and recoverable.",
            [
                "PostgreSQL",
                "SQL",
                "Replication",
                "Backup and recovery",
                "Query optimisation",
            ],
            ["Oracle", "MySQL"],
            [
                ("Operational rigour", "Tests restores rather than assuming backups work."),
                ("Performance tuning", "Finds the query or index behind a slowdown."),
            ],
            [
                "Administer production database clusters and their replicas.",
                "Design backup and point-in-time recovery procedures and rehearse them.",
                "Tune slow queries and advise teams on indexing.",
                "Plan capacity and schedule major version upgrades.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="qa-automation",
        tags=("software",),
        acceptable=("15-1253.00", "15-1252.00"),
        ambiguous=True,
        note="Software QA Analysts and Testers, with Software Developers as a defensible reading.",
        job_spec=_spec(
            "QA Automation Engineer",
            Seniority.MID,
            "Build the automated test suites that gate every release.",
            ["Selenium", "Python", "Test automation", "CI/CD", "API testing"],
            ["Playwright", "Performance testing"],
            [
                ("Test design", "Picks cases that find real defects, not cases that pass."),
                ("Defect reporting", "Writes reproductions a developer can act on."),
            ],
            [
                "Write and maintain end-to-end automated test suites.",
                "Integrate test runs into the continuous integration pipeline.",
                "Reproduce and document defects found in staging.",
                "Define regression coverage for new features before release.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="systems-analyst",
        tags=("software",),
        acceptable=("15-1211.00",),
        job_spec=_spec(
            "Computer Systems Analyst",
            Seniority.MID,
            "Bridge business requirements and the technical design of our internal systems.",
            ["Requirements analysis", "SQL", "Process modelling", "UML", "Documentation"],
            ["ERP systems", "Visio"],
            [
                ("Elicitation", "Draws real requirements out of conflicting stakeholder accounts."),
                ("Trade-off analysis", "Weighs cost, risk and fit across options."),
            ],
            [
                "Gather requirements from business units and document them.",
                "Evaluate whether to configure, extend or replace existing systems.",
                "Specify data flows and integrations between internal applications.",
                "Support user acceptance testing and rollout.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="technical-writer",
        tags=("non-tech-adjacent",),
        acceptable=("27-3042.00",),
        job_spec=_spec(
            "Technical Writer",
            Seniority.MID,
            "Write the developer documentation for our public API and SDKs.",
            ["Technical writing", "Markdown", "Git", "API documentation", "Editing"],
            ["Docs-as-code", "Information architecture"],
            [
                ("Clarity", "Explains a mechanism without losing precision."),
                ("Audience sense", "Writes for the reader's task, not the product's structure."),
            ],
            [
                "Write and maintain reference and tutorial documentation.",
                "Interview engineers to understand features before documenting them.",
                "Own the information architecture of the documentation site.",
                "Review product copy and error messages for clarity.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="registered-nurse",
        tags=("healthcare",),
        acceptable=("29-1141.00",),
        job_spec=_spec(
            "Registered Nurse - Medical Surgical Unit",
            Seniority.MID,
            "Deliver direct patient care on a 30-bed medical surgical inpatient unit.",
            [
                "Patient assessment",
                "Medication administration",
                "IV therapy",
                "BLS",
                "EHR charting",
            ],
            ["Wound care", "ACLS"],
            [
                ("Clinical judgement", "Recognises deterioration early and escalates."),
                ("Patient communication", "Explains care plans to patients and families."),
            ],
            [
                "Assess patients and record vital signs and symptoms each shift.",
                "Administer prescribed medications and monitor for adverse reactions.",
                "Coordinate care plans with physicians and allied health staff.",
                "Educate patients and families on discharge instructions.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="pharmacist",
        tags=("healthcare",),
        acceptable=("29-1051.00",),
        job_spec=_spec(
            "Clinical Pharmacist",
            Seniority.SENIOR,
            "Dispense and review medication therapy in a hospital pharmacy.",
            [
                "Pharmacology",
                "Dosage calculation",
                "Drug interaction review",
                "Dispensing",
                "Compounding",
            ],
            ["Antimicrobial stewardship", "Pharmacokinetics"],
            [
                ("Accuracy", "Catches dosing and interaction errors before dispensing."),
                ("Counselling", "Advises patients on correct use and side effects."),
            ],
            [
                "Review prescriptions for appropriateness, dose and interactions.",
                "Dispense medication and supervise pharmacy technicians.",
                "Advise prescribers on therapeutic alternatives.",
                "Counsel patients on how to take their medication safely.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="physical-therapist",
        tags=("healthcare",),
        acceptable=("29-1123.00",),
        job_spec=_spec(
            "Physical Therapist",
            Seniority.MID,
            "Rehabilitate orthopaedic and post-surgical outpatients.",
            [
                "Manual therapy",
                "Exercise prescription",
                "Gait analysis",
                "Patient assessment",
                "Documentation",
            ],
            ["Dry needling", "Sports rehabilitation"],
            [
                ("Treatment planning", "Sets measurable goals and adapts to progress."),
                ("Motivation", "Keeps patients adherent to a home programme."),
            ],
            [
                "Evaluate mobility, strength and range of motion at intake.",
                "Design and progress individualised rehabilitation programmes.",
                "Deliver hands-on therapy and supervise therapeutic exercise.",
                "Document functional outcomes and report to referring physicians.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="dental-hygienist",
        tags=("healthcare",),
        acceptable=("29-1292.00",),
        job_spec=_spec(
            "Dental Hygienist",
            Seniority.MID,
            "Provide preventive dental care in a busy family practice.",
            [
                "Scaling",
                "Periodontal charting",
                "Dental radiography",
                "Fluoride application",
                "Infection control",
            ],
            ["Local anaesthesia", "Sealants"],
            [
                ("Technique", "Works thoroughly without causing patient discomfort."),
                ("Patient education", "Changes home care habits, not just teeth."),
            ],
            [
                "Clean teeth and remove plaque and calculus deposits.",
                "Take and develop dental radiographs.",
                "Chart periodontal findings and flag concerns to the dentist.",
                "Teach patients brushing, flossing and dietary habits.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="veterinarian",
        tags=("healthcare",),
        acceptable=("29-1131.00",),
        job_spec=_spec(
            "Small Animal Veterinarian",
            Seniority.MID,
            "Diagnose and treat companion animals in a small animal clinic.",
            [
                "Clinical diagnosis",
                "Surgery",
                "Anaesthesia",
                "Radiography",
                "Vaccination protocols",
            ],
            ["Dentistry", "Exotic animal medicine"],
            [
                ("Diagnostic reasoning", "Works from signs to a differential list efficiently."),
                ("Owner communication", "Explains prognosis and cost honestly."),
            ],
            [
                "Examine animals and diagnose illness and injury.",
                "Perform routine and emergency surgical procedures.",
                "Prescribe medication and design treatment plans.",
                "Advise owners on nutrition, behaviour and preventive care.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="accountant",
        tags=("business",),
        acceptable=("13-2011.00",),
        job_spec=_spec(
            "Senior Accountant",
            Seniority.SENIOR,
            "Own the monthly close and statutory reporting for a mid-sized group.",
            ["IFRS", "General ledger", "Month-end close", "Reconciliation", "Excel"],
            ["SAP", "Tax compliance"],
            [
                ("Accuracy", "Produces statements that survive audit scrutiny."),
                ("Control mindset", "Designs checks that catch errors before reporting."),
            ],
            [
                "Prepare monthly and annual financial statements.",
                "Reconcile accounts and investigate variances.",
                "Liaise with external auditors during the annual audit.",
                "Review tax filings for accuracy and compliance.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="bookkeeper",
        tags=("business",),
        acceptable=("43-3031.00",),
        job_spec=_spec(
            "Bookkeeper",
            Seniority.JUNIOR,
            "Keep the day-to-day books for a group of small business clients.",
            ["Bookkeeping", "Accounts payable", "Accounts receivable", "QuickBooks", "Data entry"],
            ["Payroll", "Xero"],
            [
                ("Diligence", "Keeps ledgers current and tied out without prompting."),
                ("Confidentiality", "Handles client financial data discreetly."),
            ],
            [
                "Record daily financial transactions in the accounting system.",
                "Process supplier invoices and chase customer payments.",
                "Reconcile bank statements monthly.",
                "Prepare basic financial summaries for the accountant.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="market-research-analyst",
        tags=("business",),
        acceptable=("13-1161.00",),
        job_spec=_spec(
            "Market Research Analyst",
            Seniority.MID,
            "Size markets and track competitors to guide our go-to-market decisions.",
            ["Survey design", "Market sizing", "Excel", "SQL", "Competitive analysis"],
            ["Tableau", "Conjoint analysis"],
            [
                ("Research design", "Asks questions that produce decision-grade answers."),
                ("Synthesis", "Turns scattered data into a clear recommendation."),
            ],
            [
                "Design and field customer surveys and interpret the results.",
                "Build market sizing models for new product categories.",
                "Track competitor pricing and positioning.",
                "Brief marketing and product teams on findings.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="hr-specialist",
        tags=("business",),
        acceptable=("13-1071.00",),
        job_spec=_spec(
            "Human Resources Specialist",
            Seniority.MID,
            "Run recruitment and employee relations for a 400-person organisation.",
            ["Recruitment", "Interviewing", "Onboarding", "Employment law", "HRIS"],
            ["Compensation benchmarking", "Workday"],
            [
                ("Judgement", "Handles sensitive personnel matters proportionately."),
                ("Stakeholder management", "Holds hiring managers to a fair process."),
            ],
            [
                "Source and screen candidates and coordinate interview panels.",
                "Advise managers on performance and disciplinary processes.",
                "Administer onboarding and maintain employee records.",
                "Keep policies aligned with current employment legislation.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="logistician",
        tags=("business",),
        acceptable=("13-1081.02", "13-1081.00", "13-1081.01"),
        ambiguous=True,
        note="Same SOC family: Logisticians / Logistics Engineers / Logistics Analysts.",
        job_spec=_spec(
            "Supply Chain Analyst",
            Seniority.MID,
            "Plan and optimise the flow of goods from suppliers to our distribution centres.",
            [
                "Supply chain planning",
                "Inventory management",
                "Demand forecasting",
                "Excel",
                "ERP",
            ],
            ["SQL", "Lean"],
            [
                ("Systems thinking", "Sees how a local fix shifts cost elsewhere."),
                ("Vendor management", "Holds suppliers to lead-time commitments."),
            ],
            [
                "Forecast demand and set inventory targets by location.",
                "Coordinate inbound freight and resolve supplier delays.",
                "Analyse logistics cost and propose network improvements.",
                "Track supplier performance against service levels.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="paralegal",
        tags=("business",),
        acceptable=("23-2011.00",),
        job_spec=_spec(
            "Paralegal",
            Seniority.MID,
            "Support a corporate litigation team with research and document management.",
            ["Legal research", "Document review", "Case management", "Drafting", "E-filing"],
            ["Westlaw", "Discovery platforms"],
            [
                ("Thoroughness", "Finds the relevant authority and the inconvenient one."),
                ("Organisation", "Keeps large document sets navigable under deadline."),
            ],
            [
                "Research case law and summarise findings for attorneys.",
                "Draft pleadings, correspondence and discovery requests.",
                "Organise and index case files and exhibits.",
                "File documents with courts and track procedural deadlines.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="mechanical-engineer",
        tags=("engineering",),
        acceptable=("17-2141.00",),
        job_spec=_spec(
            "Mechanical Design Engineer",
            Seniority.MID,
            "Design and validate mechanical assemblies for industrial pumping equipment.",
            [
                "SolidWorks",
                "Finite element analysis",
                "GD&T",
                "Thermodynamics",
                "Design for manufacture",
            ],
            ["ANSYS", "Fatigue analysis"],
            [
                ("Analytical design", "Backs design choices with calculation, not intuition."),
                ("Manufacturability", "Designs parts a supplier can actually make."),
            ],
            [
                "Produce 3D models and manufacturing drawings for new assemblies.",
                "Run structural and thermal analyses to validate designs.",
                "Specify materials, tolerances and surface treatments.",
                "Support prototype build and design-for-manufacture reviews.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="civil-engineer",
        tags=("engineering",),
        acceptable=("17-2051.00",),
        job_spec=_spec(
            "Civil Engineer - Infrastructure",
            Seniority.SENIOR,
            "Lead design of highway drainage and earthworks on major road schemes.",
            ["AutoCAD", "Civil 3D", "Structural analysis", "Drainage design", "Building codes"],
            ["Geotechnical analysis", "BIM"],
            [
                ("Design authority", "Takes responsibility for a sealed design."),
                ("Code compliance", "Reconciles design intent with regulatory limits."),
            ],
            [
                "Prepare design drawings and specifications for highway works.",
                "Perform hydraulic calculations for drainage systems.",
                "Review contractor submittals and site queries.",
                "Coordinate with geotechnical and structural disciplines.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="electrical-engineer",
        tags=("engineering",),
        acceptable=("17-2071.00",),
        job_spec=_spec(
            "Electrical Engineer",
            Seniority.MID,
            "Design power distribution and control systems for manufacturing plants.",
            [
                "Circuit design",
                "AutoCAD Electrical",
                "PLC programming",
                "Power systems",
                "IEC standards",
            ],
            ["SCADA", "Motor control"],
            [
                ("Safety discipline", "Designs to standards without being told to."),
                ("Commissioning", "Diagnoses faults on live plant methodically."),
            ],
            [
                "Design low and medium voltage distribution schemes.",
                "Produce schematics, panel layouts and cable schedules.",
                "Specify switchgear, drives and protection devices.",
                "Support installation and commissioning on site.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="industrial-engineer",
        tags=("engineering",),
        acceptable=("17-2112.00", "17-2112.03"),
        ambiguous=True,
        note="Manufacturing Engineers (17-2112.03) is a detailed child of Industrial Engineers.",
        job_spec=_spec(
            "Industrial Engineer",
            Seniority.MID,
            "Improve throughput and reduce waste across our assembly lines.",
            [
                "Lean manufacturing",
                "Six Sigma",
                "Time study",
                "Process mapping",
                "Capacity planning",
            ],
            ["Simulation modelling", "Minitab"],
            [
                ("Measurement", "Quantifies a process before changing it."),
                ("Change management", "Gets operators to adopt a new method."),
            ],
            [
                "Analyse production processes to find bottlenecks.",
                "Redesign workstation layouts and material flow.",
                "Run time and motion studies and set standard times.",
                "Lead continuous improvement projects on the shop floor.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="graphic-designer",
        tags=("creative",),
        acceptable=("27-1024.00",),
        job_spec=_spec(
            "Graphic Designer",
            Seniority.MID,
            "Produce brand and campaign artwork across print and digital channels.",
            [
                "Adobe Illustrator",
                "Adobe Photoshop",
                "Typography",
                "Layout",
                "Brand guidelines",
            ],
            ["After Effects", "InDesign"],
            [
                ("Visual craft", "Makes typographic and compositional choices deliberately."),
                ("Feedback handling", "Iterates on critique without losing the idea."),
            ],
            [
                "Design campaign assets for social, web and print.",
                "Maintain and extend the brand visual identity.",
                "Prepare artwork files for print production.",
                "Present concepts to marketing stakeholders.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="public-relations",
        tags=("creative",),
        acceptable=("27-3031.00",),
        job_spec=_spec(
            "Public Relations Specialist",
            Seniority.MID,
            "Manage press relationships and our public narrative.",
            [
                "Media relations",
                "Press release writing",
                "Crisis communication",
                "Copywriting",
                "Media monitoring",
            ],
            ["Social listening", "Event management"],
            [
                ("Message discipline", "Keeps a story on message under pressure."),
                ("Relationship building", "Earns journalists' trust over time."),
            ],
            [
                "Write press releases and pitch stories to journalists.",
                "Prepare spokespeople with briefing notes and Q&A.",
                "Monitor coverage and report on share of voice.",
                "Draft holding statements for emerging issues.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="elementary-teacher",
        tags=("education",),
        acceptable=("25-2021.00",),
        job_spec=_spec(
            "Elementary School Teacher - Grade 4",
            Seniority.MID,
            "Teach a mixed-ability grade 4 class across the core curriculum.",
            [
                "Lesson planning",
                "Classroom management",
                "Differentiated instruction",
                "Assessment",
                "Curriculum standards",
            ],
            ["Special educational needs support", "Educational technology"],
            [
                ("Classroom management", "Holds attention and sets consistent expectations."),
                ("Differentiation", "Reaches the strongest and weakest pupils in one room."),
            ],
            [
                "Plan and deliver daily lessons in literacy, numeracy and science.",
                "Assess pupil progress and keep records for reporting.",
                "Adapt instruction for pupils with additional needs.",
                "Communicate with parents about progress and behaviour.",
            ],
        ),
    ),
    RetrievalCase(
        case_id="chef",
        tags=("hospitality",),
        acceptable=("35-1011.00",),
        job_spec=_spec(
            "Head Chef",
            Seniority.LEAD,
            "Run the kitchen of a 90-cover restaurant, from menu to margin.",
            [
                "Menu development",
                "Food safety",
                "Kitchen management",
                "Cost control",
                "Food preparation",
            ],
            ["Pastry", "Supplier negotiation"],
            [
                ("Service leadership", "Keeps a brigade calm and output consistent at peak."),
                ("Cost discipline", "Designs menus that hit gross margin targets."),
            ],
            [
                "Design seasonal menus and standardise recipes.",
                "Supervise and train kitchen staff across services.",
                "Control food cost, portioning and waste.",
                "Maintain hygiene standards and pass inspections.",
            ],
        ),
    ),
)


def case_by_id(case_id: str) -> RetrievalCase:
    for case in CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(case_id)
