import pytest

from app.core.exceptions import ConfigurationError, OccupationNotFound
from app.domain.job import Competency, JobSpec, Skill
from app.knowledge.onet_kb import OnetKnowledgeBase
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"


def test_loads_fixture_kb():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    assert len(kb) == 2


def test_get_occupation_returns_record():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    occ = kb.get_occupation("15-1252.00")
    assert occ.title == "Software Developers"
    assert occ.onet_soc_code == "15-1252.00"
    skill_names = ["Programming", "Critical Thinking", "Active Learning"]
    assert [c.skill for c in occ.competencies] == skill_names
    assert [t.technology for t in occ.technologies] == ["Python", "Git"]
    assert len(occ.core_tasks) == 2


def test_get_occupation_unknown_code_raises():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    with pytest.raises(OccupationNotFound):
        kb.get_occupation("00-0000.00")


def test_match_jobspec_ranks_relevant_occupation_first():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    job_spec = JobSpec(
        role_title="Backend Software Engineer",
        skills=[Skill(name="Python"), Skill(name="Git")],
        competencies=[Competency(name="Critical Thinking")],
        summary="Builds and maintains backend software services.",
    )
    matches = kb.match_jobspec(job_spec, top_k=2)
    assert len(matches) == 2
    assert matches[0].onet_soc_code == "15-1252.00"
    assert matches[0].score > matches[1].score
    assert matches[0].score > 0.0


def test_match_jobspec_respects_top_k():
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    job_spec = JobSpec(role_title="Software Engineer")
    matches = kb.match_jobspec(job_spec, top_k=1)
    assert len(matches) == 1


def test_missing_kb_file_raises_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError):
        OnetKnowledgeBase(path=tmp_path / "does_not_exist.jsonl")


def test_empty_kb_file_raises_configuration_error(tmp_path):
    empty_path = tmp_path / "empty.jsonl"
    empty_path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        OnetKnowledgeBase(path=empty_path)


def test_invalid_json_line_raises_configuration_error(tmp_path):
    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        OnetKnowledgeBase(path=bad_path)


def test_duplicate_occupation_code_is_rejected_not_silently_overwritten(tmp_path):
    dup_path = tmp_path / "dup.jsonl"
    record = (
        '{"onet_soc_code": "11-1011.00", "title": "Chief Executives", '
        '"description": "Lead things.", "competencies": [], "technologies": [], '
        '"core_tasks": [], "search_text": "Chief Executives"}'
    )
    dup_path.write_text(f"{record}\n{record}\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="duplicate onet_soc_code"):
        OnetKnowledgeBase(path=dup_path)


@pytest.mark.parametrize(
    "bad_record",
    [
        '{"title": "Missing code", "description": "No onet_soc_code field."}',
        '{"onet_soc_code": "11-1011.00", "description": "Missing title."}',
        '{"onet_soc_code": "11-1011.00", "title": "Missing description."}',
    ],
)
def test_malformed_record_raises_configuration_error_not_keyerror(tmp_path, bad_record):
    bad_path = tmp_path / "malformed.jsonl"
    bad_path.write_text(bad_record, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not a valid occupation record"):
        OnetKnowledgeBase(path=bad_path)


@pytest.mark.parametrize("bad_top_k", [0, -1, -5])
def test_match_jobspec_rejects_invalid_top_k(bad_top_k):
    kb = OnetKnowledgeBase(path=FIXTURE_KB_PATH)
    job_spec = JobSpec(role_title="Software Engineer")
    with pytest.raises(ValueError, match="top_k"):
        kb.match_jobspec(job_spec, top_k=bad_top_k)
