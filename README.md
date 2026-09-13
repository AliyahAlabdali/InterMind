<h1 align="center">InterMind: Autonomous AI Interviewer</h1>

<p align="center">
  <em>An adaptive AI interviewer that designs, conducts, and evaluates structured, role-specific interviews.</em>
</p>

---

## Overview

InterMind is an AI engineering project that explores how autonomous AI agents can improve the technical interviewing process.

The system takes a **job description** as input, identifies the role's requirements, and creates a structured interview tailored to that position. During the interview, the AI is designed to select questions, respond to the candidate's answers, ask relevant follow-up questions when needed, and evaluate responses based on predefined criteria.

The goal is to build an interview system that is **structured, adaptive, and explainable**, rather than simply generating a fixed list of questions.

### How It Works

```text
Job Description
       ↓
Job Requirements
       ↓
Role-Specific Interview Plan
       ↓
Adaptive Interview
       ↓
Candidate Evaluation
       ↓
Interview Report
```

---

## Current Status

InterMind is being developed incrementally. The first three stages are complete, and the autonomous interview workflow is currently under development.

### 1. Job Analysis ✅

The system converts an unstructured job description into a structured `JobSpec` containing:

* Role title
* Seniority level
* Required skills
* Competencies
* Job summary

This structured information provides the foundation for the rest of the interview process.

### 2. Interview Knowledge Base ✅

InterMind uses **O*NET 31.0**, a public occupational database, to provide additional information about occupations, skills, technologies, and tasks.

A data processing pipeline prepares the O*NET data into a searchable knowledge base. A TF-IDF matching baseline is then used to identify occupations that are relevant to the requirements extracted from a job description.

### 3. Interview Planning ✅

The system combines the job requirements with relevant occupational information to create a structured interview plan.

The plan includes role-specific questions designed around the skills and competencies required for the position.

The implementation also includes validation to ensure generated questions are complete, ordered correctly, and uniquely identifiable.

**Current test status: 66 tests passing.**

### 4. Autonomous Interview 

The next stage is building the actual interview agent using **LangGraph**.

The agent will manage the interview as a stateful workflow:

```text
Select Question
      ↓
Ask Candidate
      ↓
Receive Answer
      ↓
Evaluate Answer
      ↓
Decide What to Do Next
      ↓
 ┌───────────────┐
 │               │
Follow Up     Next Question
 │               │
 └───────┬───────┘
         ↓
       Finish
```

The agent will eventually be able to adapt the interview based on the candidate's responses instead of following a completely fixed sequence.

---

## Features

* Job description analysis
* Structured job requirements
* Role-specific interview planning
* O*NET-based occupational knowledge
* Automated question generation
* Adaptive interview workflow
* Candidate response evaluation
* Evidence-based assessment
* Structured interview reports

> Features marked as part of the future workflow are currently under development.

---

## Tech Stack

| Area                | Technologies                                   |
| :------------------ | :--------------------------------------------- |
| Backend             | FastAPI, Uvicorn, Pydantic                     |
| AI / LLM            | OpenAI, Structured Outputs, Prompt Engineering |
| Agent Orchestration | LangGraph                                      |
| Knowledge Base      | O*NET 31.0, TF-IDF                             |
| Testing             | Pytest, HTTPX                                  |
| Code Quality        | Ruff                                           |
| Language            | Python                                         |
| Development         | Git, GitHub                                    |

---

## Project Structure

```text
.
├── app/
│   ├── agents/
│   ├── api/
│   ├── core/
│   ├── domain/
│   ├── knowledge/
│   ├── llm/
│   ├── observability/
│   ├── repositories/
│   ├── services/
│   └── main.py
├── data/
│   ├── raw/
│   └── processed/
├── docs/
├── notebooks/
├── scripts/
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Getting Started

### Requirements

* Python 3.11+
* Git

### Installation

```bash
git clone https://github.com/AliyahAlabdali/InterMind.git
cd InterMind

python -m venv .venv
pip install -e ".[dev]"
```

### Configuration

Copy `.env.example` to `.env`.

For local development and testing:

```text
LLM_PROVIDER=fake
```

To use OpenAI:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key
```

### Run the API

```bash
uvicorn app.main:app --reload
```

Once running, the API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

### Run Tests

```bash
pytest -v
ruff check .
```

---

## Roadmap

* [x] Analyze job descriptions
* [x] Build structured job requirements
* [x] Build O*NET knowledge base
* [x] Match job requirements to relevant occupations
* [x] Generate role-specific interview plans
* [x] Generate and validate interview questions
* [x] Build initial LangGraph workflow
* [ ] Conduct multi-turn interviews
* [ ] Generate adaptive follow-up questions
* [ ] Evaluate candidate responses
* [ ] Generate structured interview reports
* [ ] Add persistent database storage
* [ ] Add authentication
* [ ] Add observability
* [ ] Dockerize and deploy

---

## Project Goal

InterMind is being built as a **production-oriented AI engineering project**, with an emphasis on reliable system design rather than simply connecting an LLM to an application.

The project focuses on structured data, deterministic components where appropriate, validation, stateful agent workflows, and clear separation between the AI components and the application logic.

---

<div align="center">

Exceeds expectations • Aliyah Alabdali ⭐

</div>
