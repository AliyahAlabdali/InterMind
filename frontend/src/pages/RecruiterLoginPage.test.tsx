import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { RecruiterLoginPage } from "./RecruiterLoginPage"
import { ApiError } from "../api/client"

/**
 * The recruiter sign-in screen.
 *
 * Replaces a "Workspace access key" field that told every visitor it was a development
 * mechanism. What matters here is that it is a real email/password form, that it never reveals
 * which half of a wrong credential was wrong, and that the password never leaves the component.
 */

const getRecruiterSession = vi.fn()
const recruiterLogin = vi.fn()

// The brand mark animates and does not render under jsdom. Irrelevant to sign-in behaviour.
vi.mock("../brand/Logo", () => ({ Logo: () => <span>InterMind</span> }))

vi.mock("../api/auth", () => ({
  getRecruiterSession: (...a: unknown[]) => getRecruiterSession(...a),
  recruiterLogin: (...a: unknown[]) => recruiterLogin(...a),
}))

function renderLogin(initialEntry = "/login") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/login" element={<RecruiterLoginPage />} />
        <Route path="/interviews" element={<p>Workspace home</p>} />
        <Route path="/reports/abc" element={<p>The requested report</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

/** Controlled inputs need a real input event, not a direct value assignment. */
function type(labelText: string, value: string) {
  fireEvent.change(screen.getByLabelText(labelText), { target: { value } })
}

async function fillAndSubmit(email = "recruiter@example.com", password = "a-password") {
  await screen.findByLabelText("Email address")
  type("Email address", email)
  type("Password", password)
  fireEvent.click(screen.getByRole("button", { name: /sign in/i }))
}

describe("RecruiterLoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getRecruiterSession.mockResolvedValue({ authenticated: false })
    vi.spyOn(Storage.prototype, "setItem")
  })
  afterEach(() => vi.restoreAllMocks())

  it("asks for an email and a password, not an access key", async () => {
    renderLogin()

    const email = await screen.findByLabelText("Email address")
    const password = screen.getByLabelText("Password")

    expect(email.getAttribute("type")).toBe("email")
    expect(email.getAttribute("autocomplete")).toBe("username")
    expect(password.getAttribute("type")).toBe("password")
    expect(password.getAttribute("autocomplete")).toBe("current-password")
    expect(screen.queryByText(/access key/i)).toBeNull()
  })

  it("does not explain the authentication mechanism to the user", async () => {
    renderLogin()
    await screen.findByLabelText("Email address")

    // This belongs in docs/recruiter-auth.md, not on screen.
    expect(screen.queryByText(/development access mechanism/i)).toBeNull()
    expect(screen.queryByText(/in-memory|backend restart/i)).toBeNull()
  })

  it("requires both fields before it will submit", async () => {
    renderLogin()
    await screen.findByLabelText("Email address")

    const submit = screen.getByRole("button", { name: /sign in/i })
    expect((submit as HTMLButtonElement).disabled).toBe(true)

    type("Email address", "recruiter@example.com")
    expect((submit as HTMLButtonElement).disabled).toBe(true)

    type("Password", "a-password")
    expect((submit as HTMLButtonElement).disabled).toBe(false)
  })

  it("shows one generic accessible error for bad credentials", async () => {
    recruiterLogin.mockRejectedValue(new ApiError(401, "Incorrect email or password."))
    renderLogin()
    await fillAndSubmit()

    const alert = await screen.findByRole("alert")
    expect(alert.textContent).toBe("Incorrect email or password.")
    // Never says which half was wrong - that would make this an account-enumeration oracle.
    expect(alert.textContent).not.toMatch(/email (is|was) (not|un)/i)
    expect(alert.textContent).not.toMatch(/password (is|was) (wrong|incorrect)/i)
    expect(screen.getByLabelText("Email address").getAttribute("aria-invalid")).toBe("true")
    expect(screen.getByLabelText("Password").getAttribute("aria-invalid")).toBe("true")
  })

  it("enters the workspace on success", async () => {
    recruiterLogin.mockResolvedValue({ authenticated: true })
    renderLogin()
    await fillAndSubmit()

    await waitFor(() => expect(screen.getByText("Workspace home")).toBeTruthy())
    expect(recruiterLogin).toHaveBeenCalledWith("recruiter@example.com", "a-password")
  })

  it("returns to the route the recruiter originally asked for", async () => {
    recruiterLogin.mockResolvedValue({ authenticated: true })
    render(
      <MemoryRouter initialEntries={[{ pathname: "/login", state: { from: "/reports/abc" } }]}>
        <Routes>
          <Route path="/login" element={<RecruiterLoginPage />} />
          <Route path="/interviews" element={<p>Workspace home</p>} />
          <Route path="/reports/abc" element={<p>The requested report</p>} />
        </Routes>
      </MemoryRouter>,
    )
    await fillAndSubmit()

    await waitFor(() => expect(screen.getByText("The requested report")).toBeTruthy())
  })

  it("does not show the form to someone already signed in", async () => {
    getRecruiterSession.mockResolvedValue({ authenticated: true })
    renderLogin()

    await waitFor(() => expect(screen.getByText("Workspace home")).toBeTruthy())
    expect(screen.queryByLabelText("Password")).toBeNull()
  })

  it("never writes the password to browser storage", async () => {
    recruiterLogin.mockResolvedValue({ authenticated: true })
    renderLogin()
    await fillAndSubmit("recruiter@example.com", "super-secret-value")

    await waitFor(() => expect(recruiterLogin).toHaveBeenCalled())
    expect(Storage.prototype.setItem).not.toHaveBeenCalled()
    expect(JSON.stringify(localStorage)).not.toContain("super-secret-value")
    expect(JSON.stringify(sessionStorage)).not.toContain("super-secret-value")
  })

  it("has one h1 and a main landmark", async () => {
    renderLogin()
    await screen.findByLabelText("Email address")

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
    expect(screen.getByRole("main")).toBeTruthy()
  })
})
