import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); window.history.replaceState(null, "", "/") })
async function setup(reduced = false, desktop = true) {
  vi.resetModules(); vi.useFakeTimers()
  Object.defineProperty(window, "scrollY", { configurable: true, value: 0 })
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reduced : desktop,
    addEventListener() {}, removeEventListener() {},
  }))
  return await import("./useLandingIntro")
}
describe("Finite landing opening", () => {
  it("plays the name, the turn, the interview and the docking once per session", async () => {
    const { useLandingIntro } = await setup(), view = renderHook(useLandingIntro)
    const at = (ms: number, phase: string) => { act(() => vi.advanceTimersByTime(ms)); expect(view.result.current.phase).toBe(phase) }
    expect(view.result.current.phase).toBe("brand")
    at(1250, "reveal"); at(1150, "wake"); at(650, "listen"); at(550, "analyze"); at(1300, "dock"); at(820, "settled")
    view.unmount(); expect(renderHook(useLandingIntro).result.current.phase).toBe("settled")
  })

  it("holds the name long enough for the tagline to be read before the machine turns", async () => {
    const { useLandingIntro } = await setup(), view = renderHook(useLandingIntro)
    act(() => vi.advanceTimersByTime(1200))
    expect(view.result.current.phase).toBe("brand")
  })

  it("reports how far the opening has got, so beats can be gated in order", async () => {
    const { useLandingIntro, INTRO_STEP } = await setup(), view = renderHook(useLandingIntro)
    expect(view.result.current.step).toBe(INTRO_STEP.brand)
    act(() => vi.advanceTimersByTime(3050))
    expect(view.result.current.step).toBe(INTRO_STEP.listen)
    expect(INTRO_STEP.wake).toBeLessThan(INTRO_STEP.listen)
    expect(INTRO_STEP.listen).toBeLessThan(INTRO_STEP.analyze)
    expect(INTRO_STEP.analyze).toBeLessThan(INTRO_STEP.dock)
  })

  it("cancels all later phases as soon as the user scrolls", async () => {
    const { useLandingIntro } = await setup(), view = renderHook(useLandingIntro)
    act(() => window.dispatchEvent(new Event("wheel")))
    expect(view.result.current.phase).toBe("settled")
    act(() => vi.advanceTimersByTime(8000))
    expect(view.result.current.phase).toBe("settled")
  })

  it("skips rotation and card flight for reduced motion", async () => {
    const { useLandingIntro } = await setup(true), view = renderHook(useLandingIntro)
    act(() => vi.advanceTimersByTime(320))
    expect(view.result.current.phase).toBe("settled")
  })

  it("gives a phone the name and the page, not the desktop choreography", async () => {
    const { useLandingIntro } = await setup(false, false), view = renderHook(useLandingIntro)
    act(() => vi.advanceTimersByTime(1500))
    expect(view.result.current.phase).toBe("dock")
    act(() => vi.advanceTimersByTime(600))
    expect(view.result.current.phase).toBe("settled")
  })

  it("never puts an opening in front of a direct process link", async () => {
    const { useLandingIntro } = await setup()
    window.history.replaceState(null, "", "/#process-follow")
    expect(renderHook(useLandingIntro).result.current.phase).toBe("settled")
  })
})
