import { describe, expect, it } from "vitest"
import { summarizeCoverage } from "./coverage"
import type { CoverageTarget, InterviewState } from "../types"

/**
 * Regression: the candidate's progress indicator disagreed with the report.
 *
 * For a plan of Python / Computer Vision / NLP, a candidate answered the Python question with
 * "I worked on a computer vision project using Python and PyTorch...". That single answer
 * assessed Python directly and Computer Vision through cross-target evidence, and the report
 * correctly said every required area was reached - while the stage header still read "1 of 3
 * areas explored", because coverage was derived from `asked_question_ids` and a cross-target
 * target is never *asked*.
 *
 * These pin the definition: a target counts once it has an answered turn, whichever way that
 * evidence arrived, and never merely because its question is on screen.
 */

const PYTHON = "python-id"
const VISION = "vision-id"
const NLP = "nlp-id"

function target(id: string, name: string, priority: number): CoverageTarget {
  return {
    id,
    target: name,
    category: "technology",
    requirement_level: "required",
    source: "jobspec",
    priority,
    grounding: "Job description requirement",
    assessment_status: "not_assessed",
  }
}

const TARGETS = [
  target(PYTHON, "Python", 0),
  target(VISION, "Computer Vision", 1),
  target(NLP, "Natural Language Processing (NLP)", 2),
]

function turn(questionId: string, answer = "an answer") {
  return { question_id: questionId, question: "a question", answer }
}

function state(
  history: ReturnType<typeof turn>[],
  currentQuestionId: string | null,
): Pick<InterviewState, "history" | "current_question_id"> {
  return { history, current_question_id: currentQuestionId }
}

describe("summarizeCoverage", () => {
  it("counts a target assessed from its own answer", () => {
    const coverage = summarizeCoverage(TARGETS, state([turn(PYTHON)], VISION))

    expect(coverage.assessed).toBe(1)
    expect(coverage.total).toBe(3)
    expect([...coverage.assessedIds]).toEqual([PYTHON])
  })

  it("counts a target assessed through cross-target evidence", () => {
    // The exact QA reproduction: one answer, two targets established, only one of them asked.
    const coverage = summarizeCoverage(
      TARGETS,
      state([turn(PYTHON), turn(VISION, "Worked on a computer vision project.")], NLP),
    )

    expect(coverage.assessed).toBe(2)
    expect(coverage.assessedIds.has(VISION)).toBe(true)
  })

  it("does not count a target the interview has not reached", () => {
    const coverage = summarizeCoverage(TARGETS, state([turn(PYTHON)], VISION))

    expect(coverage.assessedIds.has(NLP)).toBe(false)
    expect(coverage.remaining).toBe(2)
  })

  it("does not count the target on screen until it has been answered", () => {
    // The question is being asked right now: it is active, not explored.
    const coverage = summarizeCoverage(TARGETS, state([], PYTHON))

    expect(coverage.assessed).toBe(0)
    expect(coverage.activeId).toBe(PYTHON)
    expect(coverage.assessedIds.has(PYTHON)).toBe(false)
  })

  it("reaches the full count when every target has been assessed", () => {
    const coverage = summarizeCoverage(
      TARGETS,
      state([turn(PYTHON), turn(VISION), turn(NLP)], null),
    )

    expect(coverage.assessed).toBe(3)
    expect(coverage.remaining).toBe(0)
    expect(coverage.ratio).toBe(1)
    expect(coverage.activeId).toBeNull()
  })

  /* --- the shapes `history` actually takes ------------------------------------------- */

  it("ignores follow-up turns, which carry their own id rather than a target's", () => {
    // A follow-up on Python: the graph gives that turn a synthesized id. Python is already
    // counted from the turn that first answered it, and the follow-up must not count again.
    const coverage = summarizeCoverage(
      TARGETS,
      state([turn(PYTHON), turn("python-id::follow-up-1")], PYTHON),
    )

    expect(coverage.assessed).toBe(1)
    expect([...coverage.assessedIds]).toEqual([PYTHON])
  })

  it("keeps counting a target that is being pressed further by a follow-up", () => {
    // It has been explored; the follow-up is InterMind going deeper, not starting over.
    const coverage = summarizeCoverage(TARGETS, state([turn(PYTHON)], PYTHON))

    expect(coverage.assessed).toBe(1)
    expect(coverage.activeId).toBe(PYTHON)
  })

  it("counts a target once however many turns it took", () => {
    const coverage = summarizeCoverage(
      TARGETS,
      state([turn(PYTHON), turn(PYTHON), turn(PYTHON)], VISION),
    )

    expect(coverage.assessed).toBe(1)
  })

  it("reports nothing explored before the interview has loaded", () => {
    const coverage = summarizeCoverage(TARGETS, null)

    expect(coverage).toMatchObject({ total: 3, assessed: 0, remaining: 3, ratio: 0, activeId: null })
  })

  it("survives a plan with no targets without dividing by zero", () => {
    const coverage = summarizeCoverage([], state([turn(PYTHON)], null))

    expect(coverage).toMatchObject({ total: 0, assessed: 0, ratio: 0 })
  })

  it("ignores a current question that is not one of the plan's targets", () => {
    const coverage = summarizeCoverage(TARGETS, state([turn(PYTHON)], "some-follow-up-id"))

    expect(coverage.activeId).toBeNull()
    expect(coverage.assessed).toBe(1)
  })
})
