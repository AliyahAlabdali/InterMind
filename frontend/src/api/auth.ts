import { apiGet, apiPost } from "./client"

/**
 * Recruiter sign-in.
 *
 * The password is sent once, in the body of a POST, and is never kept: not in a variable that
 * outlives the request, not in `localStorage` or `sessionStorage`, not in the URL, and not in
 * React state beyond the controlled input it was typed into. What comes back is a session in an
 * `HttpOnly` cookie the browser cannot read.
 *
 * The backend verifies the password against the scrypt hash stored for that registered
 * recruiter account - a real credential check, not an email field bolted onto a shared key. See
 * `app/core/security.py` and `docs/recruiter-auth.md`.
 */

export interface RecruiterSessionState {
  authenticated: boolean
  expires_in_seconds?: number | null
}

/** Minimum password length. Mirrors the backend rule so the form can say so before submitting;
 * the backend is what enforces it. */
export const MIN_PASSWORD_LENGTH = 12

/** Creates an account and signs straight in. Throws `ApiError`: 409 if the email is taken,
 * 422 if the email or password was rejected. */
export function recruiterSignup(
  email: string,
  password: string,
): Promise<RecruiterSessionState> {
  return apiPost<RecruiterSessionState>("/auth/recruiter/signup", { email, password })
}

/** Signs in and starts a session. Throws `ApiError` (401) for any failure - the backend
 * deliberately does not say whether the email or the password was wrong. */
export function recruiterLogin(email: string, password: string): Promise<RecruiterSessionState> {
  return apiPost<RecruiterSessionState>("/auth/recruiter/login", { email, password })
}

/** Revokes the session server-side and clears the cookie. */
export function recruiterLogout(): Promise<RecruiterSessionState> {
  return apiPost<RecruiterSessionState>("/auth/recruiter/logout")
}

/** Whether this browser currently holds a live session. Returns a boolean only. */
export function getRecruiterSession(): Promise<RecruiterSessionState> {
  return apiGet<RecruiterSessionState>("/auth/recruiter/session")
}
