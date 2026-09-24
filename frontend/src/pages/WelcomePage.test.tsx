import { cleanup, render } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { WelcomePage } from "./WelcomePage"

vi.mock("../site/InteractiveHero3D", () => ({ InteractiveHero3D: () => null }))
vi.mock("../site/ProcessStage", () => ({ ProcessStage: () => <section id="process-follow" /> }))
vi.mock("../components/layout/ScrollMeter", () => ({ ScrollMeter: () => null }))
afterEach(() => { cleanup(); window.history.replaceState(null, "", "/"); vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe("Landing hash navigation", () => {
  it("honors a cold hash load once semantic HTML exists", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true })
    window.history.replaceState(null, "", "/#process-follow")
    const scroll = vi.fn()
    Object.defineProperty(Element.prototype, "scrollIntoView", { value: scroll, configurable: true })
    render(<MemoryRouter><WelcomePage /></MemoryRouter>)
    expect(scroll).toHaveBeenCalledOnce()
    expect(scroll.mock.instances[0]).toBe(document.getElementById("process-follow"))
  })
  it("preserves the browser's restored document position", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
    Object.defineProperty(window, "scrollY", { value: 1200, configurable: true })
    window.history.replaceState(null, "", "/#results")
    const scroll = vi.fn()
    Object.defineProperty(Element.prototype, "scrollIntoView", { value: scroll, configurable: true })
    render(<MemoryRouter><WelcomePage /></MemoryRouter>)
    expect(scroll).not.toHaveBeenCalled()
  })
})
