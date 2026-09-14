<h1 align="center">InterMind: Autonomous AI Interviewer</h1>

<p align="center">
  <em>An adaptive AI interviewer that designs, conducts, and evaluates structured, role-specific interviews.</em>
</p>

---

## Overview

InterMind is an AI engineering project that explores how autonomous AI can improve the technical interviewing process.

The system takes a **job description** as input, identifies the role's requirements, and uses them to create a structured interview. During the interview, the AI can select relevant questions, evaluate candidate responses, ask follow-up questions when needed, and produce an evidence-based interview report.

The goal is to build an interview experience that is **structured, adaptive, and explainable**, rather than simply generating a fixed list of questions.

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

InterMind is being developed incrementally. The core backend workflow and a functional frontend are now in place.

### 1. Job Analysis ✅

The system converts an unstructured job description into structured information including:

* Role title
* Seniority level
* Required and preferred skills
* Competencies
* Job summary

This information is used to build the interview around the specific role.

### 2. Interview Knowledge Base ✅

InterMind uses **O*NET 31.0** to provide additional occupational information, including relevant skills, technologies, and tasks.

A data processing pipeline converts the O*NET data into a searchable knowledge base. The system then uses a TF-IDF matching approach to identify occupations that are relevant to the job requirements.

### 3. Interview Planning ✅

The system combines the requirements extracted from the job description with relevant O*NET information to create a structured interview plan.

The plan includes:

* Competency-based questions
* Technology-based questions
* Task-based questions
* Evidence showing whether each question comes from the job description or O*NET

Generated questions are validated to ensure they are complete, correctly ordered, and uniquely identifiable.

### 4. Autonomous Interview ✅

The interview is managed as a stateful workflow using **LangGraph**.

The system can:

* Select the next relevant question
* Receive and evaluate candidate answers
* Decide whether a follow-up question is needed
* Continue to the next question
* Track interview progress
* Safely handle completed or invalid interview sessions

This allows the interview to adapt to the candidate's responses rather than following only a fixed sequence.

### 5. Candidate Evaluation & Report ✅

Candidate responses are evaluated against the requirements covered during the interview.

The system produces a structured report containing:

* Overall score
* Recommendation
* Competency assessments
* Question-level evaluations
* Evidence from candidate responses
* Strengths and areas for improvement

The evaluation logic is designed to be consistent and traceable rather than relying only on an unstructured LLM-generated conclusion.

### 6. Web Application ✅

InterMind includes a React-based frontend connected to the FastAPI backend.

The current interface supports the complete core flow:

```text
Create Job
   ↓
View Interview Plan
   ↓
Conduct Interview
   ↓
Complete Interview
   ↓
View Interview Report
```

---

## Features

* Job description analysis
* Structured job requirements
* O*NET-based occupational matching
* Role-specific interview planning
* Automated question generation
* Adaptive interview workflow
* Candidate response evaluation
* Evidence-based assessment
* Structured interview reports
* React web interface
* FastAPI backend
* Automated tests and validation

---

## Tech Stack

| Area                | Technologies                                   |
| :------------------ | :--------------------------------------------- |
| Frontend            | React, TypeScript, Vite, Tailwind CSS          |
| Backend             | FastAPI, Uvicorn, Pydantic                     |
| AI / LLM            | OpenAI, Structured Outputs, Prompt Engineering |
| Agent Orchestration | LangGraph                                      |
| Knowledge Base      | O*NET 31.0, TF-IDF                             |
| Testing             | Pytest, HTTPX                                  |
| Code Quality        | Ruff, oxlint                                   |
| Language            | Python, TypeScript                             |
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
│   ├── repositories/
│   ├── services/
│   └── main.py
├── data/
│   ├── raw/
│   └── processed/
├── docs/
├── frontend/
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
* Node.js 18+
* Git

### Installation

Clone the repository:

```bash
git clone https://github.com/AliyahAlabdali/InterMind.git
cd InterMind
```

Create and activate a Python virtual environment:

```bash
python -m venv .venv
```

Install the backend dependencies:

```bash
pip install -e ".[dev]"
```

Install the frontend dependencies:

```bash
cd frontend
npm install
cd ..
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

API keys should be kept in local environment files and never committed to the repository.

### Run the Backend

From the project root:

```bash
uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

### Run the Frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

The web application will be available at:

```text
http://localhost:5173
```

### Run Tests

From the project root:

```bash
pytest -v
```

Run code quality checks:

```bash
ruff check .
```

The current test suite contains **139 passing tests**.

---

## Roadmap

### Completed

* [x] Analyze job descriptions
* [x] Build structured job requirements
* [x] Build O*NET knowledge base
* [x] Match job requirements to relevant occupations
* [x] Generate role-specific interview plans
* [x] Generate and validate interview questions
* [x] Build LangGraph interview workflow
* [x] Conduct multi-turn interviews
* [x] Generate adaptive follow-up questions
* [x] Evaluate candidate responses
* [x] Generate structured interview reports
* [x] Build functional web frontend

### In Progress

* [ ] UI redesign and visual identity
* [ ] Improve interview experience and animations
* [ ] Improve occupation matching beyond the current TF-IDF baseline

### Planned

* [ ] PostgreSQL persistence
* [ ] Authentication and role-based access
* [ ] Observability
* [ ] Dockerization
* [ ] Production deployment
* [ ] Portfolio integration

---

## Project Goal

InterMind is being built as a **production-oriented AI engineering project**.

The project focuses on designing an AI system as a complete application rather than simply connecting an LLM to an interface. It combines structured data, deterministic processing, validation, stateful agent workflows, evidence-based evaluation, and clear separation between AI components and application logic.

The long-term goal is to create an interviewer that can understand a role, conduct a meaningful adaptive interview, evaluate candidate evidence, and provide a useful report for hiring decisions.

---

<div align="center">

Exceeds expectations • Aliyah Alabdali ⭐

</div>
