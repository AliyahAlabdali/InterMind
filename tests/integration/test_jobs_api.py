from app.api.deps import get_llm_client
from app.core.exceptions import ConfigurationError


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_create_then_get_job(client):
    jd = "Senior Backend Engineer\nPython, FastAPI, PostgreSQL. Kafka is a plus."
    resp = await client.post("/jobs", json={"job_description": jd})
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_spec"]["role_title"] == "Senior Backend Engineer"
    assert body["id"]

    got = await client.get(f"/jobs/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body


async def test_get_unknown_job_returns_404(client):
    resp = await client.get("/jobs/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found: does-not-exist"


async def test_create_job_rejects_empty_description(client):
    resp = await client.post("/jobs", json={"job_description": ""})
    assert resp.status_code == 422


async def test_create_job_requires_field(client):
    resp = await client.post("/jobs", json={})
    assert resp.status_code == 422


async def test_configuration_error_maps_to_stable_500(app, client):
    def _raise_config_error():
        raise ConfigurationError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")

    app.dependency_overrides[get_llm_client] = _raise_config_error
    resp = await client.post("/jobs", json={"job_description": "anything"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Service is not configured correctly."}
