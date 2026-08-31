# Autonomous AI Interviewer

Production-oriented portfolio project. An autonomous system that will eventually take a
job description from an HR user, build an adaptive interview plan, conduct the interview,
score answers with evidence, and produce an HR report.

## Milestone 1 (current scope)

A minimal, typed FastAPI service that turns a job description into a structured `JobSpec`.

- `GET /health` - liveness check
- `POST /jobs` - submit a job description, get a structured `JobSpec` back (stored in memory)
- `GET /jobs/{id}` - retrieve a previously analysed job

Not in this milestone: LangGraph, RAG, multi-agent, voice, frontend, Docker/deployment,
scoring engine, interview engine, report generation, and any database (storage is in-memory).

## Architecture

Layered / hexagonal. Business logic in `app/domain` and `app/services` never imports
FastAPI or the OpenAI SDK; those live at the edges behind small interfaces:

- `app/llm/ports.py` - `LLMClient` protocol, implemented by `openai_client.py` and `fake_client.py`
- `app/repositories/ports.py` - `JobRepository` protocol, implemented by `in_memory.py`

Prompts are versioned files under `app/llm/prompts/` and loaded by name + version.

Datasets (O*NET etc.) live only under `data/`; preprocessing scripts live under `scripts/`
and transform `data/raw` -> `data/processed`. Neither is imported by `app/`.

## Setup

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# bash:                source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # defaults to the offline fake LLM; no API key needed
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Interactive docs at http://127.0.0.1:8000/docs

## Test

```bash
pytest
```

## Example

```bash
curl -s -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"job_description": "Senior Backend Engineer\nWe need strong Python and FastAPI experience, plus PostgreSQL. Kafka is a plus."}'
```
