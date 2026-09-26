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

  it("skips rotation and card flight for reduced motion, but holds long enough to be read", async () => {
    const { useLandingIntro } = await setup(true), view = renderHook(useLandingIntro)
    // Was 320ms, which is under the time it takes to focus on a word: the opening registered as
    // a black flash rather than as a quiet version of itself. Reduced motion means no travel,
    // not no opening.
    act(() => vi.advanceTimersByTime(320))
    expect(view.result.current.phase).toBe("brand")
    act(() => vi.advanceTimersByTime(800))
    expect(view.result.current.phase).toBe("settled")
  })

  it("gives a phone branding only, and briefly", async () => {
    const { useLandingIntro } = await setup(false, false), view = renderHook(useLandingIntro)
    const at = (ms: number, phase: string) => { act(() => vi.advanceTimersByTime(ms)); expect(view.result.current.phase).toBe(phase) }
    // The machine's entrance belongs to the Hero now (see useHeroReveal), so the splash is a
    // wordmark and nothing else. Staging the composition in here put it mostly below a phone's
    // fold and then played it again when the Hero took over.
    at(1180, "dock"); at(640, "settled")
  })

  it("hands over at `dock`, which is what the Hero reveal waits for", async () => {
    const { useLandingIntro, INTRO_STEP } = await setup(false, false), view = renderHook(useLandingIntro)
    expect(view.result.current.step).toBeLessThan(INTRO_STEP.dock)
    act(() => vi.advanceTimersByTime(1180))
    expect(view.result.current.step).toBeGreaterThanOrEqual(INTRO_STEP.dock)
  })

  it("puts a skip past the hand-off, so the Hero still gets to reveal itself", async () => {
    // `finish()` jumps to `settled`, which is past `dock`. That is what stops a skip from
    // dropping the visitor onto a composition that has already finished arriving.
    const { useLandingIntro, INTRO_STEP } = await setup(false, false), view = renderHook(useLandingIntro)
    act(() => window.dispatchEvent(new Event("touchstart")))
    expect(view.result.current.step).toBeGreaterThanOrEqual(INTRO_STEP.dock)
  })

  it("is not ended by a viewport resize", async () => {
    // The bug this pins: `resize` used to dismiss the opening, and iOS Safari fires it by itself
    // while the address bar settles during load. On a phone the opening ended before its first
    // frame, every time, with no user action at all.
    const { useLandingIntro } = await setup(false, false), view = renderHook(useLandingIntro)
    act(() => window.dispatchEvent(new Event("resize")))
    expect(view.result.current.phase).not.toBe("settled")
  })

  it("is not ended by the few pixels a collapsing browser chrome scrolls the page", async () => {
    const { useLandingIntro } = await setup(false, false), view = renderHook(useLandingIntro)
    Object.defineProperty(window, "scrollY", { configurable: true, value: 12 })
    act(() => window.dispatchEvent(new Event("scroll")))
    expect(view.result.current.phase).not.toBe("settled")
  })

  it("is ended by a scroll that actually travels", async () => {
    const { useLandingIntro } = await setup(false, false), view = renderHook(useLandingIntro)
    Object.defineProperty(window, "scrollY", { configurable: true, value: 260 })
    act(() => window.dispatchEvent(new Event("scroll")))
    expect(view.result.current.phase).toBe("settled")
  })

  it("never puts an opening in front of a direct process link", async () => {
    const { useLandingIntro } = await setup()
    window.history.replaceState(null, "", "/#process-follow")
    expect(renderHook(useLandingIntro).result.current.phase).toBe("settled")
  })
})
