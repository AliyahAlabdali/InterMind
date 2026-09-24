import { describe, expect, it } from "vitest"
import { desktopEligible, journeyState, type JourneyAnchor } from "./journeyState"

const anchors: JourneyAnchor[] = [0, 100, 250, 400].map((at, pose) => ({ at, pose, x: pose * 10, y: at, size: 400, name: `pose-${pose}` }))
describe("Journey position mapping", () => {
  it("gives identical states after jumps and reverse scrolling", () => {
    const expected = journeyState(175, anchors)
    for (const y of [0, 7000, 300, 120, 500, -10]) journeyState(y, anchors)
    expect(journeyState(175, anchors)).toEqual(expected)
  })
  it("handles every boundary and clamps before and after the story", () => {
    for (const a of anchors) expect(journeyState(a.at, anchors)?.x).toBe(a.x)
    expect(journeyState(-100, anchors)?.x).toBe(0)
    expect(journeyState(5000, anchors)?.x).toBe(30)
    for (const a of anchors.slice(1)) expect(Math.abs(journeyState(a.at - .001, anchors)!.x - journeyState(a.at + .001, anchors)!.x)).toBeLessThan(.001)
  })
  it("holds an authored pause regardless of scroll direction", () => {
    const paused = anchors.map(a => ({ ...a, pose: 7, x: 100, y: 200 }))
    for (const y of [20, 80, 240, 70]) {
      const state = journeyState(y, paused)!
      expect([state.from, state.to, state.x, state.y]).toEqual([7, 7, 100, 200])
    }
  })
  it("rejects invalid measurements and empty layouts", () => {
    expect(journeyState(100, [])).toBeNull()
    expect(journeyState(NaN, anchors)).toBeNull()
  })
  it("never enables mobile, short-screen or reduced-motion WebGL", () => {
    for (const width of [375, 390, 768, 1023]) expect(desktopEligible(width, 900, false)).toBe(false)
    expect(desktopEligible(1440, 599, false)).toBe(false)
    expect(desktopEligible(1920, 1080, true)).toBe(false)
    expect(desktopEligible(1366, 768, false)).toBe(true)
  })
})
