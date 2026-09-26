import { act, cleanup, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { resetHeroReveal, useHeroReveal } from "./useHeroReveal"

/**
 * The portrait Hero's entrance is its own machine, and these are the properties that make it one:
 * it starts on arrival rather than on scroll, it ends exactly where the resting Hero already is,
 * it plays once, and it does not exist at all on desktop or under reduced motion.
 */
beforeEach(() => { vi.useFakeTimers(); resetHeroReveal() })
afterEach(() => { cleanup(); vi.useRealTimers() })

const render = (active: boolean, enabled = true) =>
  renderHook(({ a, e }: { a: boolean; e: boolean }) => useHeroReveal({ active: a, enabled: e }), {
    initialProps: { a: active, e: enabled },
  })

describe("Portrait Hero reveal", () => {
  it("holds the machine below the frame until the branding hands over", () => {
    const view = render(false)
    expect(view.result.current).toBe("hidden")
    act(() => vi.advanceTimersByTime(4000))
    expect(view.result.current).toBe("hidden")
  })

  it("runs machine, then panels, then channel, then settles", () => {
    const view = render(true)
    const at = (ms: number, stage: string) => { act(() => vi.advanceTimersByTime(ms)); expect(view.result.current).toBe(stage) }
    at(40, "machine"); at(580, "panels"); at(440, "channel"); at(560, "settled")
  })

  it("starts as soon as it becomes active, with no scroll involved", () => {
    const view = render(false)
    view.rerender({ a: true, e: true })
    act(() => vi.advanceTimersByTime(40))
    expect(view.result.current).toBe("machine")
  })

  it("does not replay when the viewport changes under it", () => {
    // iOS fires resize continuously while the address bar collapses. Restaging the Hero under
    // the visitor every time that happened would be worse than having no entrance at all.
    const view = render(true)
    act(() => vi.advanceTimersByTime(2000))
    expect(view.result.current).toBe("settled")
    view.rerender({ a: false, e: true })
    view.rerender({ a: true, e: true })
    act(() => vi.advanceTimersByTime(2000))
    expect(view.result.current).toBe("settled")
  })

  it("plays once per session, not once per mount", () => {
    const first = render(true)
    act(() => vi.advanceTimersByTime(2000))
    expect(first.result.current).toBe("settled")
    first.unmount()
    expect(render(true).result.current).toBe("settled")
  })

  it("does not exist on desktop or under reduced motion", () => {
    // `null` is the signal to render no attribute at all, so those viewports keep the resting
    // Hero rather than a disabled version of an animation.
    const view = render(true, false)
    expect(view.result.current).toBeNull()
    act(() => vi.advanceTimersByTime(4000))
    expect(view.result.current).toBeNull()
  })
})
