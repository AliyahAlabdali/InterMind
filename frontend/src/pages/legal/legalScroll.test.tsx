import { StrictMode } from "react"
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { CookiesPage } from "./CookiesPage"
import { PrivacyPage } from "./PrivacyPage"
import { TermsPage } from "./TermsPage"
import { WelcomePage } from "../WelcomePage"

// Use the landing-page test's existing mocks while keeping its real footer links.
vi.mock("../../site/InteractiveHero3D", () => ({ InteractiveHero3D: () => null }))
vi.mock("../../site/ProcessStage", () => ({ ProcessStage: () => <section id="process-follow" /> }))
vi.mock("../../components/layout/ScrollMeter", () => ({ ScrollMeter: () => null }))

/**
 * These three pages share one shell, and the shell is where the scroll reset lives.
 *
 * The bug it fixes is invisible in a unit test's zero-height window, so what is asserted here is
 * the decision rather than the pixel: that arriving at a different legal route asks to be taken
 * to the top, and that stepping *back* through history does not - because that is the one case
 * where the visitor is asking for a position they already had, and the browser restores it.
 */
let scrollTo: ReturnType<typeof vi.spyOn>
const restorationWrite = vi.fn()
let originalRestoration: PropertyDescriptor | undefined

beforeEach(() => {
  // Same matchMedia stub as WelcomePage.test.tsx. Keep the actual shared shell, including
  // NightAtmosphere and Logo (whose reduced-motion hook needs matchMedia).
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {})
  originalRestoration = Object.getOwnPropertyDescriptor(window.history, "scrollRestoration")
  restorationWrite.mockClear()
  Object.defineProperty(window.history, "scrollRestoration", {
    configurable: true,
    get: () => "auto",
    set: restorationWrite,
  })
})
afterEach(() => {
  cleanup()
  expect(restorationWrite).not.toHaveBeenCalled()
  if (originalRestoration) {
    Object.defineProperty(window.history, "scrollRestoration", originalRestoration)
  } else {
    Reflect.deleteProperty(window.history, "scrollRestoration")
  }
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

/** The sidebar link, not a cross-reference of the same name in the body copy. */
const sidebarLink = (name: string) =>
  within(screen.getByRole("navigation", { name: "Legal pages" })).getByRole("link", { name })

const legalPages = ["Privacy", "Terms", "Cookies"] as const
const route = (name: string) => `/legal/${name.toLowerCase()}`
const directions = [
  ["Privacy", "Terms"], ["Terms", "Cookies"], ["Cookies", "Privacy"],
  ["Terms", "Privacy"], ["Cookies", "Terms"], ["Privacy", "Cookies"],
] as const

/** Exercise history POPs and programmatic navigation without link-specific handlers. */
function NavigationControls() {
  const navigate = useNavigate()
  return <>
    <button onClick={() => navigate(-1)}>go back</button>
    <button onClick={() => navigate(1)}>go forward</button>
    {legalPages.map(name => <button key={name} onClick={() => navigate(route(name), { replace: true })}>
      replace with {name}
    </button>)}
  </>
}

function renderLegal(initial = "/legal/privacy") {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={[initial]}>
        <NavigationControls />
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="/legal/privacy" element={<PrivacyPage />} />
          <Route path="/legal/terms" element={<TermsPage />} />
          <Route path="/legal/cookies" element={<CookiesPage />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  )
}

describe("Legal page scroll", () => {
  it.each(legalPages)("leaves an initial %s load or refresh to native restoration", name => {
    vi.stubGlobal("scrollY", 1175)
    renderLegal(route(name))
    expect(scrollTo).not.toHaveBeenCalled()
    expect(window.scrollY).toBe(1175)
  })

  it.each(directions)("resets %s → %s via the sidebar", (from, to) => {
    renderLegal(route(from))
    vi.stubGlobal("scrollY", 3038)
    scrollTo.mockClear()
    fireEvent.click(sidebarLink(to))
    expect(screen.getByRole("heading", { level: 1, name: to })).toBeTruthy()
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it.each(directions)("resets %s → %s via programmatic REPLACE", (from, to) => {
    renderLegal(route(from))
    vi.stubGlobal("scrollY", 1200)
    scrollTo.mockClear()
    fireEvent.click(screen.getByRole("button", { name: `replace with ${to}` }))
    expect(screen.getByRole("heading", { level: 1, name: to })).toBeTruthy()
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it.each([
    ["Privacy", "Cookies"], ["Terms", "Privacy"], ["Cookies", "Privacy"],
  ])("resets %s → %s via the existing body link", (from, to) => {
    renderLegal(route(from))
    vi.stubGlobal("scrollY", 1800)
    scrollTo.mockClear()
    fireEvent.click(within(screen.getByRole("main")).getByRole("link", { name: to }))
    expect(screen.getByRole("heading", { level: 1, name: to })).toBeTruthy()
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it.each(legalPages)("resets when entering %s from the actual landing footer", name => {
    renderLegal("/")
    vi.stubGlobal("scrollY", 3038)
    scrollTo.mockClear()
    fireEvent.click(within(screen.getByRole("navigation", { name: "Footer" })).getByRole("link", { name }))
    expect(screen.getByRole("heading", { level: 1, name })).toBeTruthy()
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })

  it.each(directions)("leaves Back/Forward between %s and %s to native restoration", (from, to) => {
    renderLegal(route(from))
    fireEvent.click(sidebarLink(to))
    scrollTo.mockClear()

    fireEvent.click(screen.getByRole("button", { name: "go back" }))
    expect(screen.getByRole("heading", { level: 1, name: from })).toBeTruthy()
    expect(scrollTo).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "go forward" }))
    expect(screen.getByRole("heading", { level: 1, name: to })).toBeTruthy()
    expect(scrollTo).not.toHaveBeenCalled()

    // A new PUSH after POP still resets, including when returning to the previous pathname.
    fireEvent.click(sidebarLink(from))
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
  })
})
