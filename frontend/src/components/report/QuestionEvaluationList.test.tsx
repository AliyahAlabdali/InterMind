import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { QuestionEvaluationList } from "./QuestionEvaluationList"
import type { QuestionEvaluationSummary } from "../../types"

/**
 * Regression: the interview record described questions the interview never asked.
 *
 * A target established from an answer to a *different* question gets a row here, because its
 * evidence belongs in the record. But it was numbered in sequence with the real questions and
 * its panel was headed "InterMind asked" - directly above the backend's own placeholder text
 * saying it was not asked directly. One row said both things at once.
 */

function summary(over: Partial<QuestionEvaluationSummary>): QuestionEvaluationSummary {
  return {
    question_id: "q1",
    question: "Can you describe a project where you used Python?",
    category: "technology",
    target: "Python",
    candidate_answer: "I built an ETL pipeline in Python.",
    score: 1,
    evidence_strength: "strong",
    evidence_type: "demonstrated",
    evidence_label: "Strong evidence",
    decision: "advance",
    evidence: [],
    strengths: [],
    weaknesses: [],
    assessment_method: "direct",
    ...over,
  }
}

const PYTHON = summary({})
const VISION = summary({
  question_id: "q2",
  target: "Computer Vision",
  assessment_method: "cross_target",
  question:
    "(Not asked directly - identified from the candidate's answer to a different question.)",
  candidate_answer: "Worked on a computer vision project using Python and PyTorch.",
})
const NLP = summary({
  question_id: "q3",
  target: "Natural Language Processing (NLP)",
  question: "Tell me about a project where you applied NLP.",
  candidate_answer: "I built a support ticket classifier.",
})

describe("QuestionEvaluationList", () => {
  it("numbers only the questions that were actually asked", () => {
    render(<QuestionEvaluationList items={[PYTHON, VISION, NLP]} />)

    const rows = screen.getAllByRole("listitem")
    expect(within(rows[0]).getByText("1")).toBeTruthy()
    // The cross-target row takes no position - it was never asked.
    expect(within(rows[1]).queryByText("2")).toBeNull()
    expect(within(rows[1]).getByLabelText("Not asked directly")).toBeTruthy()
    // ...and the next real question keeps the sequence the recruiter would count.
    expect(within(rows[2]).getByText("2")).toBeTruthy()
  })

  it("does not claim InterMind asked about a cross-target requirement", () => {
    render(<QuestionEvaluationList items={[VISION]} />)

    fireEvent.click(screen.getByRole("button", { name: /Computer Vision/ }))

    expect(screen.queryByText("InterMind asked")).toBeNull()
    expect(screen.getByText("Not asked directly")).toBeTruthy()
    // The backend's placeholder said this too; printing both is what made it contradictory.
    expect(screen.queryByText(/\(Not asked directly - identified from/)).toBeNull()
  })

  it("still shows the candidate's own words for a cross-target requirement", () => {
    render(<QuestionEvaluationList items={[VISION]} />)

    fireEvent.click(screen.getByRole("button", { name: /Computer Vision/ }))

    expect(screen.getByText("What they said")).toBeTruthy()
    expect(
      screen.getByText("Worked on a computer vision project using Python and PyTorch."),
    ).toBeTruthy()
    // Provenance and evidence state are separate things; the state label is preserved.
    expect(screen.getByText(/Strong evidence/)).toBeTruthy()
  })

  it("leaves a directly asked question reading exactly as before", () => {
    render(<QuestionEvaluationList items={[PYTHON]} />)

    fireEvent.click(screen.getByRole("button", { name: /Python/ }))

    expect(screen.getByText("InterMind asked")).toBeTruthy()
    expect(screen.getByText(PYTHON.question)).toBeTruthy()
    expect(screen.getByText("They answered")).toBeTruthy()
    expect(screen.getByText(PYTHON.candidate_answer)).toBeTruthy()
  })
})
