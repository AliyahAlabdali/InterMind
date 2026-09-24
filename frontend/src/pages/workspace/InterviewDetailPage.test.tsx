/**
 * Regression tests for the interview (role) page's coverage cleanup.
 *
 * The page used to end in a section headed "What this interview explores" that listed every
 * coverage target in the plan - fifteen rows of the interview's internal brief, on a recruiter
 * page. It was not actionable, and worse, it was not honest about any individual candidate:
 * every requirement looked identical whether it had been assessed, partially evidenced, or
 * never reached at all, which reads as a scorecard of failures.
 *
 * These tests pin the removal and pin what replaced it: the compact facts stay in the header,
 * and what a candidate actually reached stays on their own row.
 */

import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("../../api/jobs", () => ({
  getJob: vi.fn(),
}))
vi.mock("../../api/interviewPlans", () => ({
  getInterviewPlan: vi.fn(),
  createInterviewPlan: vi.fn(),
}))
vi.mock("../../api/interviews", () => ({
  listJobInterviews: vi.fn(),
  startInterview: vi.fn(),
}))

import { getInterviewPlan } from "../../api/interviewPlans"
import { listJobInterviews } from "../../api/interviews"
import { getJob } from "../../api/jobs"
import { InterviewDetailPage } from "./InterviewDetailPage"

const JOB = {
  id: "job-1",
  job_spec: {
    role_title: "Senior Backend Software Engineer",
    seniority: "senior",
    responsibilities: [],
    required_skills: [],
    preferred_skills: [],
  },
  raw_text: "A job description.",
}

/** Fifteen targets, as in the QA scenario - the inventory that used to be printed in full. */
const TARGETS = [
  "Communication",
  "Python",
  "Docker",
  "Distributed Systems",
  "Testing",
  "Debugging",
  "Problem Solving",
  "FastAPI",
  "REST APIs",
  "PostgreSQL",
  "Mentoring",
  "Design Review",
  "Kubernetes",
  "GraphQL",
  "CI/CD",
].map((target, index) => ({
  id: `t-${index}`,
  category: "technology",
  target,
  requirement_level: index < 11 ? "required" : "preferred",
  source: "jobspec",
  priority: index,
  grounding: "Job description requirement",
}))

const PLAN = {
  job_id: "job-1",
  role_title: "Senior Backend Software Engineer",
  seniority: "senior",
  coverage_targets: TARGETS,
  occupation_match: { onet_soc_code: "15-1252.00", title: "Software Developers", score: 1 },
  alternate_matches: [],
  onet_grounding_used: true,
  onet_context: "",
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/interviews/job-1"]}>
      <Routes>
        <Route path="/interviews/:jobId" element={<InterviewDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("InterviewDetailPage coverage cleanup", () => {
  beforeEach(() => {
    vi.mocked(getJob).mockResolvedValue(JOB as never)
    vi.mocked(getInterviewPlan).mockResolvedValue(PLAN as never)
    vi.mocked(listJobInterviews).mockResolvedValue([] as never)
  })

  it("no longer renders the internal target inventory", async () => {
    renderPage()
    await screen.findByText(/Senior Backend Software Engineer/)

    expect(screen.queryByText(/What this interview explores/i)).toBeNull()
  })

  it("does not list every coverage target from the plan", async () => {
    renderPage()
    await screen.findByText(/Senior Backend Software Engineer/)

    // A representative spread: an early target, a late one, and one that a real interview
    // would typically never reach. None of them belong on this page.
    await waitFor(() => {
      expect(screen.queryByText("Kubernetes")).toBeNull()
    })
    expect(screen.queryByText("GraphQL")).toBeNull()
    expect(screen.queryByText("Distributed Systems")).toBeNull()
    expect(screen.queryByText("CI/CD")).toBeNull()
  })

  it("keeps the compact factual summary in the header", async () => {
    renderPage()

    // Counts, not an inventory: how big the interview is, without naming what it probes.
    expect(await screen.findByText(/15 areas to explore/)).toBeTruthy()
    expect(screen.getByText(/11 required/)).toBeTruthy()
  })

  it("still shows the role itself", async () => {
    renderPage()
    expect(await screen.findByText("Senior Backend Software Engineer")).toBeTruthy()
  })
})
