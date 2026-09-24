import { describe, expect, it } from "vitest"
import { INTERVIEWER_POSE } from "../../interviewer/types"
import { processPose, PROCESS_STATES } from "./processState"

describe("Original instrument scroll poses", () => {
  it("preserves all six original configurations", () => {
    PROCESS_STATES.forEach((name, index) => expect(processPose(index)).toEqual(INTERVIEWER_POSE[name]))
  })
  it("focuses the listening aperture on the answer without history or a clock", () => {
    const middle = processPose(3.5)
    expect(middle.focus).toBe(.5)
    expect(middle.open).toBeCloseTo(.6)
    for (const position of [5, 0, 2, 4, 3]) processPose(position)
    expect(processPose(3.5)).toEqual(middle)
    expect(processPose(-1)).toEqual(INTERVIEWER_POSE.thinking)
    expect(processPose(99)).toEqual(INTERVIEWER_POSE.evidence)
  })
})
