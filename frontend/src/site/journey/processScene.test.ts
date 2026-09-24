import { afterEach, describe, expect, it, vi } from "vitest"
const fake = vi.hoisted(() => ({ render: vi.fn(), dispose: vi.fn(), fail: false, lost: false }))
vi.mock("three", async original => {
  const three = await original<typeof import("three")>()
  return { ...three, WebGLRenderer: class {
    info = { render: { calls: 2, triangles: 13184 } }
    constructor() { if (fake.fail) throw Error("No WebGL") }
    setPixelRatio() {} setSize() {} async compileAsync() {}
    getContext() { return { isContextLost: () => fake.lost } }
    render = fake.render; dispose = fake.dispose
  } }
})
import { createProcessScene } from "./processScene"
import { processPose } from "./processState"
afterEach(() => { fake.fail = false; fake.lost = false; fake.render.mockClear(); fake.dispose.mockClear() })
describe("Landing original-instrument renderer", () => {
  it("draws only a changed scroll sample and releases resources once", async () => {
    Object.defineProperty(document, "hidden", { configurable: true, value: false })
    const canvas = document.createElement("canvas")
    Object.defineProperties(canvas, { clientWidth: { value: 352 }, clientHeight: { value: 352 } })
    const scene = createProcessScene(canvas)!
    await scene.ready
    scene.draw(processPose(3), 3); scene.draw(processPose(3), 3)
    expect(fake.render).toHaveBeenCalledOnce()
    scene.draw(processPose(3.5), 3.5); expect(fake.render).toHaveBeenCalledTimes(2)
    Object.defineProperty(document, "hidden", { configurable: true, value: true })
    expect(scene.draw(processPose(4), 4)).toBe(false)
    Object.defineProperty(document, "hidden", { configurable: true, value: false })
    fake.lost = true; expect(scene.draw(processPose(4), 4)).toBe(false)
    scene.dispose(); scene.dispose(); expect(fake.dispose).toHaveBeenCalledOnce()
  })
  it("returns the static fallback path when WebGL is unavailable", () => {
    fake.fail = true
    expect(createProcessScene(document.createElement("canvas"))).toBeNull()
  })
})
