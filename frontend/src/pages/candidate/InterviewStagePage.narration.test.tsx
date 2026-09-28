/**
 * How the interview screen narrates questions.
 *
 * The behaviour that matters to a candidate: each question is read once and only once, a
 * follow-up is read even though it keeps the same target id, and the question is on screen and
 * answerable whether or not narration works at all.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const speak = vi.fn()
const cancel = vi.fn()
const stopAndCollect = vi.fn(async () => "")
let partial = ""

vi.mock("../../speech", async () => {
  const actual = await vi.importActual<typeof import("../../speech")>("../../speech")
  return {
    ...actual,
    useSpeechOutput: () => ({
      speak,
      cancel,
      isSpeaking: false,
      level: 0,
      isSupported: true,
    }),
    useSpeechInput: () => ({
      start: vi.fn(),
      stop: vi.fn(),
      stopAndCollect,
      isRecording: false,
      isSupported: false,
      level: 0,
      error: null,
      partial,
    }),
  }
})

// The 3D interviewer is WebGL and observer-driven, and has nothing to do with narration.
vi.mock("../../interviewer/Interviewer", () => ({
  Interviewer: () => null,
}))

vi.mock("../../api/interviews", () => ({
  getInterview: vi.fn(),
  submitAnswer: vi.fn(),
}))
vi.mock("../../api/interviewPlans", () => ({
  getCandidateInterviewPlan: vi.fn(),
}))

import { getInterview, submitAnswer } from "../../api/interviews"
import { getCandidateInterviewPlan } from "../../api/interviewPlans"
import { InterviewStagePage } from "./InterviewStagePage"
import { ApiError } from "../../api/client"

const INTERVIEW = {
  interview_id: "interview-1",
  job_id: "job-1",
  candidate_name: "Candidate",
  candidate_email: "",
  status: "in_progress",
  finished: false,
  turn_index: 0,
  current_turn_id: "11111111111111111111111111111111",
  current_question_id: "target-1",
  current_question_text: "Tell me about a backend system you designed.",
  current_question_is_follow_up: false,
  asked_question_ids: ["target-1"],
  history: [],
}

const PLAN = {
  job_id: "job-1",
  role_title: "Backend Engineer",
  coverage_targets: [{ id: "target-1", target: "PostgreSQL" }],
}

function renderStage() {
  return render(
    <MemoryRouter initialEntries={["/candidate/interviews/interview-1/session?token=t"]}>
      <Routes>
        <Route
          path="/candidate/interviews/:interviewId/session"
          element={<InterviewStagePage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  // jsdom implements no media queries. The stage page asks two things: whether motion should be
  // reduced, and whether there is a fine pointer (it only auto-focuses the answer field on a
  // real pointer). Both answer "no" here, which is the phone-like case.
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      media: "",
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(),
    })),
  )
  speak.mockClear()
  cancel.mockClear()
  stopAndCollect.mockResolvedValue("")
  partial = ""
  vi.mocked(getCandidateInterviewPlan).mockResolvedValue(PLAN as never)
  vi.mocked(getInterview).mockResolvedValue(INTERVIEW as never)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe("question narration", () => {
  it("keeps the complete attempted spoken answer editable after a failed submit", async () => {
    stopAndCollect.mockResolvedValue("Final spoken sentence.")
    vi.mocked(submitAnswer).mockRejectedValue(new Error("offline"))
    renderStage()
    const field = await screen.findByRole("textbox")
    fireEvent.change(field, { target: { value: "Typed beginning." } })
    fireEvent.click(screen.getByRole("button", { name: /submit|send/i }))
    await waitFor(() => expect(submitAnswer).toHaveBeenCalled())
    expect(submitAnswer).toHaveBeenCalledWith(
      "interview-1", "Typed beginning. Final spoken sentence.", "t", INTERVIEW.current_turn_id,
    )
    await waitFor(() => expect(field).toHaveProperty(
      "value", "Typed beginning. Final spoken sentence.",
    ))
  })

  it("keeps a speech-only answer retryable without duplicating the collected segment", async () => {
    partial = "Complete spoken answer."
    stopAndCollect.mockResolvedValueOnce("Complete spoken answer.").mockResolvedValue("")
    vi.mocked(submitAnswer).mockRejectedValue(new Error("offline"))
    renderStage()
    const field = await screen.findByRole("textbox")
    fireEvent.click(screen.getByRole("button", { name: /submit|send/i }))
    await waitFor(() => expect(field).toHaveProperty("value", "Complete spoken answer."))
    await waitFor(() => expect(screen.getByRole("button", { name: /submit|send/i })).toHaveProperty("disabled", false))
    fireEvent.click(screen.getByRole("button", { name: /submit|send/i }))
    await waitFor(() => expect(submitAnswer).toHaveBeenCalledTimes(2))
    expect(vi.mocked(submitAnswer).mock.calls[1][1]).toBe("Complete spoken answer.")
  })

  it("reloads a stale turn while keeping the draft and staying on the interview", async () => {
    vi.mocked(submitAnswer).mockRejectedValue(new ApiError(412, "stale"))
    renderStage()
    const field = await screen.findByRole("textbox")
    fireEvent.change(field, { target: { value: "My draft" } })
    vi.mocked(getInterview).mockResolvedValue({ ...INTERVIEW, current_turn_id: "2".repeat(32) } as never)
    fireEvent.click(screen.getByRole("button", { name: /submit|send/i }))
    await screen.findByText(/This question changed in another tab/)
    expect(field).toHaveProperty("value", "My draft")
    expect(getInterview).toHaveBeenCalledTimes(2)
  })
  it("reads the current question aloud once it arrives", async () => {
    renderStage()

    await waitFor(() =>
      expect(speak).toHaveBeenCalledWith("Tell me about a backend system you designed."),
    )
  })

  it("reads each question exactly once, not again on every re-render", async () => {
    const { rerender } = renderStage()
    await waitFor(() => expect(speak).toHaveBeenCalled())

    rerender(
      <MemoryRouter initialEntries={["/candidate/interviews/interview-1/session?token=t"]}>
        <Routes>
          <Route
            path="/candidate/interviews/:interviewId/session"
            element={<InterviewStagePage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() =>
      expect(speak).toHaveBeenCalledWith("Tell me about a backend system you designed."),
    )
    expect(
      speak.mock.calls.filter(
        ([text]) => text === "Tell me about a backend system you designed.",
      ),
    ).toHaveLength(1)
  })

  it("shows the question text even when narration produces nothing", async () => {
    // The browser that cannot narrate at all: `speak` is called and simply never makes a sound.
    speak.mockImplementation(() => {})

    renderStage()

    // The question is on screen and answerable regardless. `findByText` throws if it never
    // appears, so reaching the assertion at all is the proof.
    expect(await screen.findByText("Tell me about a backend system you designed.")).toBeTruthy()
    expect(screen.getByRole("textbox")).toBeTruthy()
  })
})
