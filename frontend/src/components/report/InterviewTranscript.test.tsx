/**
 * The interview record is the conversation, not the scoring view.
 *
 * A real production interview asked one question, got an answer, asked a targeted follow-up, and
 * got a second answer. The report's `question_evaluations` keeps one entry per requirement (the
 * answer that settled it), so that interview appeared in the record as a single exchange - the
 * follow-up - and the page claimed one question had been asked. These pin the fix: the record
 * renders every turn the interview actually produced, in order, with its own answer.
 */

import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { InterviewTranscript } from "./InterviewTranscript"
import { transcriptCounts } from "../../lib/transcript"
import type { CandidateAnswerTurn } from "../../types"

/** One coverage target, asked directly and then followed up: the follow-up carries its own id. */
const TARGET_IDS = ["target-llm"]

const TURNS: CandidateAnswerTurn[] = [
  {
    question_id: "target-llm",
    question: "How have you worked with large language models?",
    answer: "I built a computer vision model with YOLO for defect detection.",
  },
  {
    question_id: "followup-target-llm-1",
    question: "Have you worked directly with a language model rather than a vision model?",
    answer: "Not directly, no. My work has been on the vision side.",
  },
]

describe("InterviewTranscript", () => {
  it("shows the main question and its follow-up, in the order they were asked", () => {
    render(<InterviewTranscript turns={TURNS} targetIds={TARGET_IDS} />)

    const rows = screen.getAllByRole("listitem")
    expect(rows).toHaveLength(2)

    expect(within(rows[0]).getByText("Question 1")).toBeTruthy()
    expect(
      within(rows[0]).getByText("How have you worked with large language models?"),
    ).toBeTruthy()

    expect(within(rows[1]).getByText("Follow-up")).toBeTruthy()
    expect(
      within(rows[1]).getByText(
        "Have you worked directly with a language model rather than a vision model?",
      ),
    ).toBeTruthy()
  })

  it("keeps each answer with the question it answered", () => {
    render(<InterviewTranscript turns={TURNS} targetIds={TARGET_IDS} />)
    const rows = screen.getAllByRole("listitem")

    expect(
      within(rows[0]).getByText("I built a computer vision model with YOLO for defect detection."),
    ).toBeTruthy()
    expect(
      within(rows[1]).getByText("Not directly, no. My work has been on the vision side."),
    ).toBeTruthy()
  })

  it("counts every question put to the candidate, follow-ups included", () => {
    expect(transcriptCounts(TURNS, TARGET_IDS)).toEqual({ total: 2, followUps: 1 })
  })

  it("still numbers every turn when the plan is unavailable to mark follow-ups", () => {
    render(<InterviewTranscript turns={TURNS} targetIds={[]} />)

    expect(screen.getByText("Question 1")).toBeTruthy()
    expect(screen.getByText("Question 2")).toBeTruthy()
    expect(screen.queryByText("Follow-up")).toBeNull()
    expect(transcriptCounts(TURNS, [])).toEqual({ total: 2, followUps: 0 })
  })

  it("says so plainly when a turn has no recorded answer", () => {
    render(
      <InterviewTranscript
        turns={[{ question_id: "target-llm", question: "A question.", answer: "   " }]}
        targetIds={TARGET_IDS}
      />,
    )

    expect(screen.getByText("No answer was recorded for this question.")).toBeTruthy()
  })
})
