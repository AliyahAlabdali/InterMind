/**
 * The handful of route paths that more than one module needs to agree on.
 *
 * Route structure, and why it is what it is:
 *
 * - `/` is the public landing page and stays public.
 * - `/login` is recruiter sign-in. A flat top-level path rather than `/recruiter/login`,
 *   because the workspace's own routes are already flat (`/interviews`, `/candidates`,
 *   `/reports/:id`) and there is exactly one kind of account to sign in as - `/recruiter/*`
 *   would imply a sibling namespace that does not exist.
 * - The workspace keeps its existing URLs. Moving them under `/workspace` would be a churn of
 *   every nav link, redirect and test for no functional gain, and those URLs are already
 *   recruiter-only and gated.
 * - `/candidate/interviews/:id` is the candidate's own space, authenticated by the token in
 *   their invitation link and never by a recruiter session.
 */

/** Where a recruiter lands after signing in, and where `/login` sends someone already signed in. */
export const WORKSPACE_HOME = "/interviews"

/** Recruiter sign-in. */
export const LOGIN = "/login"

/** Recruiter registration. Flat, beside `/login`, for the same reason. */
export const SIGNUP = "/signup"

/** Public landing page. */
export const HOME = "/"
