import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { PrivacyPage } from "./PrivacyPage"

describe("privacy notice", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("uses the verified contact and does not claim retention is live", () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: false, addEventListener() {}, removeEventListener() {},
    }))
    render(<MemoryRouter><PrivacyPage /></MemoryRouter>)
    const contact = screen.getByRole("link", { name: "AliyahAlabdali24@gmail.com" })
    expect(contact.getAttribute("href")).toBe("mailto:AliyahAlabdali24@gmail.com")
    expect(screen.getByText(/not yet operating on the public deployment/i)).toBeTruthy()
    expect(screen.getByText(/PostgreSQL database runs on Neon in Frankfurt/i)).toBeTruthy()
    expect(screen.getByText(/Microsoft Azure AI Speech in East US/i)).toBeTruthy()
  })
})
