/**
 * The report page's interview record, end to end.
 *
 * The record used to render `question_evaluations`, which carries one entry per requirement (the
 * answer that settled it). An interview that asked a question and then followed up on it
 * therefore showed only the follow-up, and the page said "1 question was asked". The record now
 * comes from the interview's own history, so it shows the conversation that actually happened.
 *
 * The second test is the other half of that: the history fetch is an extra call on a page whose
 * content comes from the report, so losing it must cost the transcript and nothing else.
 */

import { render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("../../api/interviews", () => ({
  getInterview: vi.fn(),
  getInterviewReport: vi.fn(),
  listJobInterviews: vi.fn(),
}))
vi.mock("../../api/jobs", () => ({ getJobDetail: vi.fn() }))
vi.mock("../../api/interviewPlans", () => ({ getInterviewPlan: vi.fn() }))

import { getInterview, getInterviewReport, listJobInterviews } from "../../api/interviews"
import { getInterviewPlan } from "../../api/interviewPlans"
import { getJobDetail } from "../../api/jobs"
import { ReportPage } from "./ReportPage"

const TARGET_ID = "target-llm"

const REPORT = {
  interview_id: "int-1",
  job_id: "job-1",
  overall_score: 0.2,
  overall_evidence_strength: "insufficient",
  recommendation: "no_hire",
  summary: "The interview did not establish experience with large language models.",
  strengths: [],
  weaknesses: [],
  competencies: [
    {
      name: "LLM (Large Language Models)",
      category: "technology",
      score: 0.2,
      evidence_strength: "insufficient",
      evidence_type: "insufficient",
      evidence_label: "Nothing established",
      evidence: [],
      strengths: [],
      weaknesses: [],
      assessment_method: "direct",
    },
  ],
  // One entry for the requirement, carrying the follow-up turn: this is exactly the collapse
  // that made the record look like a single-question interview.
  question_evaluations: [
    {
      question_id: "followup-target-llm-1",
      question: "Have you worked directly with a language model rather than a vision model?",
      category: "technology",
      target: "LLM (Large Language Models)",
      candidate_answer: "Not directly, no. My work has been on the vision side.",
      score: 0.2,
      evidence_strength: "insufficient",
      evidence_type: "insufficient",
      evidence_label: "Nothing established",
      decision: "advance",
      evidence: [],
      strengths: [],
      weaknesses: [],
      assessment_method: "direct",
    },
  ],
  unassessed_required_targets: [],
  score_basis_note: "Based on assessed evidence only.",
  completion_reason: "sufficient_evidence",
}

const PLAN = {
  job_id: "job-1",
  role_title: "AI Engineer",
  seniority: "mid",
  occupation_match: { onet_soc_code: "15-2051.00", title: "Data Scientists", score: 0.14 },
  alternate_matches: [],
  onet_grounding_used: true,
  onet_context: [],
  competencies: [],
  technologies: [],
  tasks: [],
  coverage_targets: [
    {
      id: TARGET_ID,
      category: "technology",
      target: "LLM (Large Language Models)",
      requirement_level: "required",
      source: "jobspec",
      priority: 0,
      grounding: "Job description requirement",
    },
  ],
}

const JOB = {
  id: "job-1",
  job_spec: {
    role_title: "AI Engineer",
    seniority: "mid",
    responsibilities: [],
    required_skills: [],
    preferred_skills: [],
  },
  raw_text: "A job description.",
}

const HISTORY = [
  {
    question_id: TARGET_ID,
    question: "How have you worked with large language models?",
    answer: "I built a computer vision model with YOLO for defect detection.",
  },
  {
    question_id: "followup-target-llm-1",
    question: "Have you worked directly with a language model rather than a vision model?",
    answer: "Not directly, no. My work has been on the vision side.",
  },
]

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/reports/int-1"]}>
      <Routes>
        <Route path="/reports/:interviewId" element={<ReportPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("ReportPage interview record", () => {
  beforeEach(() => {
    vi.mocked(getInterviewReport).mockResolvedValue(REPORT as never)
    vi.mocked(getJobDetail).mockResolvedValue(JOB as never)
    vi.mocked(getInterviewPlan).mockResolvedValue(PLAN as never)
    vi.mocked(listJobInterviews).mockResolvedValue([
      {
        interview_id: "int-1",
        candidate_name: "Aliyah",
        candidate_email: "",
        status: "completed",
      },
    ] as never)
    vi.mocked(getInterview).mockResolvedValue({ history: HISTORY } as never)
  })

  it("renders both the question and its follow-up, in order, with their answers", async () => {
    renderPage()

    expect(
      await screen.findByText("How have you worked with large language models?"),
    ).toBeTruthy()
    expect(
      screen.getByText("Have you worked directly with a language model rather than a vision model?"),
    ).toBeTruthy()
    expect(
      screen.getByText("I built a computer vision model with YOLO for defect detection."),
    ).toBeTruthy()

    // Marking follow-ups needs the plan's target ids, which load separately from the history.
    expect(await screen.findByText("Follow-up")).toBeTruthy()

    const record = screen.getByRole("heading", { name: "Interview record" }).closest("section")!
    const rows = within(record).getAllByRole("listitem")
    expect(within(rows[0]).getByText("Question 1")).toBeTruthy()
    expect(within(rows[1]).getByText("Follow-up")).toBeTruthy()
    expect(within(record).getByText(/2 questions asked, including 1 follow-up\./)).toBeTruthy()
  })

  it("keeps the report readable when the interview history cannot be loaded", async () => {
    vi.mocked(getInterview).mockRejectedValue(new Error("state unavailable"))
    renderPage()

    // The assessment and the evidence are built from the report itself, so they stay.
    expect(await screen.findByText("Evidence assessment")).toBeTruthy()
    expect(screen.getByText("Limited evidence")).toBeTruthy()
    expect(screen.getByText("LLM (Large Language Models)")).toBeTruthy()

    await waitFor(() =>
      expect(
        screen.getByText(/The conversation is not available for this interview\./),
      ).toBeTruthy(),
    )
    // No question count is claimed when there is nothing to count.
    expect(screen.queryByText(/questions asked/)).toBeNull()
  })
})
