import { afterEach, describe, expect, it, vi } from "vitest"
import { demandFrame } from "./demandFrame"
afterEach(() => vi.unstubAllGlobals())
describe("Landing demand scheduler", () => {
  it("coalesces events, sleeps when hidden, resumes once, and cancels on disposal", () => {
    const pending = new Map<number, FrameRequestCallback>(); let id = 0
    vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => { pending.set(++id, fn); return id })
    vi.stubGlobal("cancelAnimationFrame", (key: number) => pending.delete(key))
    Object.defineProperty(document, "hidden", { configurable: true, value: false })
    const draw = vi.fn(), work = demandFrame(draw)
    for (let i = 0; i < 20; i++) work.invalidate()
    expect(pending.size).toBe(1)
    const batch = [...pending.values()]; pending.clear(); batch.forEach(fn => fn(0))
    expect(draw).toHaveBeenCalledOnce(); expect(pending.size).toBe(0)
    work.invalidate()
    Object.defineProperty(document, "hidden", { configurable: true, value: true })
    document.dispatchEvent(new Event("visibilitychange")); work.invalidate()
    expect(pending.size).toBe(0)
    Object.defineProperty(document, "hidden", { configurable: true, value: false })
    document.dispatchEvent(new Event("visibilitychange")); expect(pending.size).toBe(1)
    work.dispose(); work.invalidate(); document.dispatchEvent(new Event("visibilitychange"))
    expect(pending.size).toBe(0)
  })
})
