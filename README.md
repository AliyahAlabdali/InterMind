<h1 align="center"> InterMind: Autonomous AI Interviewer</h1>

<p align="center">
  <em>An adaptive AI interviewer that autonomously designs, conducts, and evaluates structured, role-specific interviews.</em>
</p>

---
## Overview

InterMind is an AI engineering project for building an end-to-end interview system.

It uses job requirements and competency-driven reasoning to create structured interviews tailored to each role and candidate. The system is designed to adapt question selection, analyze candidate responses in real time, and produce evidence-based evaluations.

The project is being developed incrementally, starting with the foundation: transforming an unstructured job description into a structured `JobSpec` containing:

- Role title
- Seniority
- Required skills
- Competencies
- Job summary

This structured representation will later drive interview planning, question selection, follow-up questions, and candidate evaluation.

---

## Current Progress

### Milestone 1: Job Analysis Foundation ✅

The current API supports:

| Method | Endpoint         | Description                         |
| :----- | :--------------- | :---------------------------------- |
| `GET`  | `/health`        | Health check                        |
| `POST` | `/jobs`          | Analyze and store a job description |
| `GET`  | `/jobs/{job_id}` | Retrieve a job                      |

Implemented:

* FastAPI backend
* Structured `JobSpec`
* Fake and OpenAI LLM clients
* Versioned prompts
* In-memory repository
* Error handling
* Unit and integration tests
* Ruff checks

**Test status:** `25 passed`

---

## Project Structure

```text
.
├── app/
│   ├── api/
│   ├── core/
│   ├── domain/
│   ├── llm/
│   ├── observability/
│   ├── repositories/
│   ├── services/
│   └── main.py
├── data/
├── docs/
├── scripts/
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Tech Stack

* **Backend:** FastAPI · Uvicorn · Pydantic
* **AI / LLM:** OpenAI · Structured Outputs · Prompt Engineering
* **Testing:** Pytest · HTTPX
* **Code Quality:** Ruff
* **Architecture:** Service Layer · Repository Pattern · Dependency Injection
* **Development:** Python · Git · GitHub

---

## Getting Started

### Install

```bash
git clone https://github.com/AliyahAlabdali/Autonomous-AI-Interviewer.git
cd Autonomous-AI-Interviewer

python -m venv .venv
pip install -e ".[dev]"
```

### Configure

Copy `.env.example` to `.env`.

For local development:

```text
LLM_PROVIDER=fake
```

To use OpenAI:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key
```

### Run

```bash
uvicorn app.main:app --reload
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### Test

```bash
pytest -v
ruff check .
```

---

## Roadmap

### Milestone 2 — Dataset & Knowledge Base

* [ ] Explore and document the dataset
* [ ] Build the data processing pipeline
* [ ] Define competency and question schemas
* [ ] Prepare interview knowledge data

### Milestone 3 — Interview Planning

* [ ] Generate interview plans
* [ ] Generate role-specific questions
* [ ] Define competency coverage
* [ ] Build the first LangGraph workflow

### Milestone 4 — Autonomous Interview

* [ ] Conduct multi-turn interviews
* [ ] Track interview state
* [ ] Generate follow-up questions
* [ ] Prevent repetitive questions

### Milestone 5 — Evaluation

* [ ] Define an evaluation rubric
* [ ] Score candidate responses
* [ ] Track evidence
* [ ] Generate interview reports

### Milestone 6 — Productionization

* [ ] PostgreSQL persistence
* [ ] Authentication
* [ ] Observability
* [ ] Dockerization
* [ ] Deployment

---

<div align="center">

*Exceeds expectations* • **Aliyah Alabdali** ⭐

</div>