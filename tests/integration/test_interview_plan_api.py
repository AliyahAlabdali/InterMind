import pytest

from app.api.deps import get_llm_client, get_onet_kb
from app.knowledge.onet_kb import OnetKnowledgeBase
from app.llm.fake_client import FakeLLMClient
from tests.conftest import FIXTURES

FIXTURE_KB_PATH = FIXTURES / "onet_kb_fixture.jsonl"


@pytest.fixture(autouse=True)
def _use_fixture_kb(app):
    # Keep this suite independent of the real, generated data/processed/onet/onet_kb.jsonl.
    app.dependency_overrides[get_onet_kb] = lambda: OnetKnowledgeBase(path=FIXTURE_KB_PATH)


async def test_create_then_get_interview_plan(client):
    jd = "Backend Software Engineer\nPython and Git experience required. Critical thinking a must."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    create_resp = await client.post(f"/jobs/{job_id}/interview-plan")
    assert create_resp.status_code == 201
    plan = create_resp.json()
    assert plan["job_id"] == job_id
    assert plan["occupation_match"]["onet_soc_code"] == "15-1252.00"
    assert len(plan["questions"]) > 0
    assert len(plan["competencies"]) > 0
    assert len(plan["technologies"]) > 0

    get_resp = await client.get(f"/jobs/{job_id}/interview-plan")
    assert get_resp.status_code == 200
    assert get_resp.json() == plan


async def test_create_interview_plan_for_unknown_job_returns_404(client):
    resp = await client.post("/jobs/does-not-exist/interview-plan")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found: does-not-exist"


async def test_get_interview_plan_before_creation_returns_404(client):
    jd = "Software Developer\nPython required."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]

    resp = await client.get(f"/jobs/{job_id}/interview-plan")
    assert resp.status_code == 404
    assert resp.json()["detail"] == f"Interview plan not found: {job_id}"


async def test_repeated_post_is_idempotent_and_preserves_plan_identity(client):
    jd = "Software Developer\nPython required."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]

    first = await client.post(f"/jobs/{job_id}/interview-plan")
    second = await client.post(f"/jobs/{job_id}/interview-plan")
    third = await client.post(f"/jobs/{job_id}/interview-plan")

    # Only the first call actually creates a plan; repeats return the same one unchanged.
    assert first.status_code == 201
    assert second.status_code == 200
    assert third.status_code == 200
    assert first.json() == second.json() == third.json()

    first_question_ids = [q["id"] for q in first.json()["questions"]]
    second_question_ids = [q["id"] for q in second.json()["questions"]]
    assert first_question_ids == second_question_ids

    got = await client.get(f"/jobs/{job_id}/interview-plan")
    assert got.json() == first.json()


async def test_interview_plan_flow_works_without_openai_credits(app, client):
    # Explicitly exercise the fake provider end-to-end, per the "no paid API for tests" rule.
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    jd = "Software Developer\nPython required."
    job_resp = await client.post("/jobs", json={"job_description": jd})
    job_id = job_resp.json()["id"]

    resp = await client.post(f"/jobs/{job_id}/interview-plan")
    assert resp.status_code == 201
    assert len(resp.json()["questions"]) > 0
