import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { RecruiterSignupPage } from "./RecruiterSignupPage"
import { ApiError } from "../api/client"

/**
 * Recruiter registration.
 *
 * What matters: both passwords are required and must match, the length rule is stated before
 * submitting rather than discovered by rejection, a successful signup lands in the workspace
 * already authenticated, and the password never leaves the component.
 */

const getRecruiterSession = vi.fn()
const recruiterSignup = vi.fn()

vi.mock("../brand/Logo", () => ({ Logo: () => <span>InterMind</span> }))
vi.mock("../api/auth", async () => {
  const actual = await vi.importActual<typeof import("../api/auth")>("../api/auth")
  return {
    MIN_PASSWORD_LENGTH: actual.MIN_PASSWORD_LENGTH,
    getRecruiterSession: (...a: unknown[]) => getRecruiterSession(...a),
    recruiterSignup: (...a: unknown[]) => recruiterSignup(...a),
  }
})

function renderSignup() {
  return render(
    <MemoryRouter initialEntries={["/signup"]}>
      <Routes>
        <Route path="/signup" element={<RecruiterSignupPage />} />
        <Route path="/interviews" element={<p>Workspace home</p>} />
        <Route path="/login" element={<p>Sign in page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

const GOOD_PASSWORD = "a-long-enough-passphrase"

async function fill(password = GOOD_PASSWORD, confirm = password) {
  await screen.findByLabelText("Email address")
  type("Email address", "new@example.com")
  type("Password", password)
  type("Confirm password", confirm)
}

describe("RecruiterSignupPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getRecruiterSession.mockResolvedValue({ authenticated: false })
    vi.spyOn(Storage.prototype, "setItem")
  })
  afterEach(() => vi.restoreAllMocks())

  it("asks only for email and password - no company or name fields", async () => {
    renderSignup()

    const email = await screen.findByLabelText("Email address")
    expect(email.getAttribute("type")).toBe("email")
    expect(email.getAttribute("autocomplete")).toBe("email")
    expect(screen.getByLabelText("Password").getAttribute("autocomplete")).toBe("new-password")
    expect(screen.getByLabelText("Confirm password").getAttribute("autocomplete")).toBe(
      "new-password",
    )
    for (const absent of [/company/i, /first name/i, /last name/i, /phone/i, /job title/i]) {
      expect(screen.queryByText(absent)).toBeNull()
    }
  })

  it("states the password rule before anything is submitted", async () => {
    renderSignup()
    await screen.findByLabelText("Email address")

    expect(screen.getByText(/at least 12 characters/i)).toBeTruthy()
    expect(recruiterSignup).not.toHaveBeenCalled()
  })

  it("requires every field before it will submit", async () => {
    renderSignup()
    await screen.findByLabelText("Email address")
    const submit = () => screen.getByRole("button", { name: /create account/i })

    expect((submit() as HTMLButtonElement).disabled).toBe(true)
    type("Email address", "new@example.com")
    expect((submit() as HTMLButtonElement).disabled).toBe(true)
    type("Password", GOOD_PASSWORD)
    expect((submit() as HTMLButtonElement).disabled).toBe(true)
    type("Confirm password", GOOD_PASSWORD)
    expect((submit() as HTMLButtonElement).disabled).toBe(false)
  })

  it("will not submit when the two passwords differ", async () => {
    renderSignup()
    await fill(GOOD_PASSWORD, "something-else-entirely")

    const alert = await screen.findByRole("alert")
    expect(alert.textContent).toBe("Both passwords must match.")
    expect(screen.getByLabelText("Confirm password").getAttribute("aria-invalid")).toBe("true")
    expect((screen.getByRole("button", { name: /create account/i }) as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it("will not submit a password under the minimum length", async () => {
    renderSignup()
    await fill("tooshort", "tooshort")

    expect(screen.getByLabelText("Password").getAttribute("aria-invalid")).toBe("true")
    expect((screen.getByRole("button", { name: /create account/i }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect(recruiterSignup).not.toHaveBeenCalled()
  })

  it("enters the workspace on success, already signed in", async () => {
    recruiterSignup.mockResolvedValue({ authenticated: true })
    renderSignup()
    await fill()
    fireEvent.click(screen.getByRole("button", { name: /create account/i }))

    await waitFor(() => expect(screen.getByText("Workspace home")).toBeTruthy())
    expect(recruiterSignup).toHaveBeenCalledWith("new@example.com", GOOD_PASSWORD)
  })

  it("shows a backend validation error accessibly", async () => {
    recruiterSignup.mockRejectedValue(
      new ApiError(409, "An account with that email already exists."),
    )
    renderSignup()
    await fill()
    fireEvent.click(screen.getByRole("button", { name: /create account/i }))

    const alert = await screen.findByRole("alert")
    expect(alert.textContent).toBe("An account with that email already exists.")
  })

  it("never writes the password to browser storage", async () => {
    recruiterSignup.mockResolvedValue({ authenticated: true })
    renderSignup()
    await fill("correct-horse-battery-staple")
    fireEvent.click(screen.getByRole("button", { name: /create account/i }))

    await waitFor(() => expect(recruiterSignup).toHaveBeenCalled())
    expect(Storage.prototype.setItem).not.toHaveBeenCalled()
    expect(JSON.stringify(localStorage)).not.toContain("correct-horse-battery-staple")
    expect(JSON.stringify(sessionStorage)).not.toContain("correct-horse-battery-staple")
  })

  it("does not show the form to someone already signed in", async () => {
    getRecruiterSession.mockResolvedValue({ authenticated: true })
    renderSignup()

    await waitFor(() => expect(screen.getByText("Workspace home")).toBeTruthy())
    expect(screen.queryByLabelText("Password")).toBeNull()
  })

  it("offers a way back to sign-in", async () => {
    renderSignup()
    await screen.findByLabelText("Email address")

    fireEvent.click(screen.getByRole("link", { name: /sign in/i }))
    await waitFor(() => expect(screen.getByText("Sign in page")).toBeTruthy())
  })

  it("has one h1 and a main landmark", async () => {
    renderSignup()
    await screen.findByLabelText("Email address")

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1)
    expect(screen.getByRole("main")).toBeTruthy()
  })
})
