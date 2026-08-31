import pytest

from app.domain.job import JobSpec
from app.llm.fake_client import FakeLLMClient
from app.services.jd_analysis import JDAnalysisService
from tests.conftest import FIXTURES


async def test_analyze_returns_jobspec_from_canned_default():
    service = JDAnalysisService(llm=FakeLLMClient())
    result = await service.analyze("Senior Python Engineer\nFastAPI experience required.")
    assert isinstance(result, JobSpec)
    assert result.role_title == "Senior Python Engineer"
    assert [s.name for s in result.skills] == ["Python", "FastAPI"]


async def test_analyze_uses_configured_response():
    canned = JobSpec(role_title="Data Scientist")
    service = JDAnalysisService(llm=FakeLLMClient(response=canned))
    result = await service.analyze("anything at all")
    assert result == canned


async def test_analyze_with_fixture_files():
    spec = JobSpec.model_validate_json((FIXTURES / "sample_jobspec.json").read_text())
    jd = (FIXTURES / "sample_jd.txt").read_text()
    service = JDAnalysisService(llm=FakeLLMClient(response=spec))
    assert await service.analyze(jd) == spec


@pytest.mark.parametrize("bad", ["", "   ", "\n\t"])
async def test_analyze_rejects_blank_description(bad):
    service = JDAnalysisService(llm=FakeLLMClient())
    with pytest.raises(ValueError):
        await service.analyze(bad)
