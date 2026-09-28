from app.domain.job import JobSpec, Seniority, Skill


def test_jobspec_defaults():
    spec = JobSpec(role_title="Backend Engineer")
    assert spec.seniority is Seniority.UNKNOWN
    assert spec.skills == []
    assert spec.competencies == []
    assert spec.summary is None


def test_skill_required_defaults_true_and_is_overridable():
    spec = JobSpec(
        role_title="Backend Engineer",
        seniority=Seniority.SENIOR,
        skills=[Skill(name="Python"), Skill(name="Kafka", required=False)],
    )
    assert spec.skills[0].required is True
    assert spec.skills[1].required is False


def test_seniority_accepts_string_value():
    spec = JobSpec.model_validate({"role_title": "SRE", "seniority": "lead"})
    assert spec.seniority is Seniority.LEAD
