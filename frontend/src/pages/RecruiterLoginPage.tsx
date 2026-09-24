import { useCallback, useEffect, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { getRecruiterSession, recruiterLogin } from "../api/auth"
import { ApiError } from "../api/client"
import { Logo } from "../brand/Logo"
import { Spinner } from "../components/ui/Spinner"
import { useDocumentTitle } from "../hooks/useDocumentTitle"
import { SIGNUP, WORKSPACE_HOME } from "../app/routes"

/**
 * Recruiter sign-in.
 *
 * Its own route rather than a wall thrown up in front of the workspace: a public visitor should
 * reach the product, not an authentication screen they have no way past. The landing page links
 * here; nothing else redirects to it except a recruiter-only route the visitor asked for.
 *
 * Nothing about how authentication is implemented appears on screen. The previous version told
 * every visitor it was "a development access mechanism", which is true, belongs in
 * `docs/recruiter-auth.md`, and is not something a product says to the person signing in.
 *
 * The password lives only in the controlled input while it is being typed and is cleared on
 * success. It is never written to browser storage, never put in the URL, and never logged.
 */
export function RecruiterLoginPage() {
  useDocumentTitle("Sign in")

  const navigate = useNavigate()
  const location = useLocation()
  /** Where the recruiter was heading before they were asked to sign in. */
  const intended = (location.state as { from?: string } | null)?.from ?? WORKSPACE_HOME

  const [checking, setChecking] = useState(true)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Someone already signed in has no business looking at a sign-in form.
  useEffect(() => {
    let cancelled = false
    getRecruiterSession()
      .then((state) => {
        if (cancelled) return
        if (state.authenticated) navigate(intended, { replace: true })
        else setChecking(false)
      })
      .catch(() => {
        if (!cancelled) setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [intended, navigate])

  const onSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault()
      if (submitting || !email.trim() || !password) return
      setSubmitting(true)
      setError(null)
      try {
        await recruiterLogin(email.trim(), password)
        setPassword("")
        navigate(intended, { replace: true })
      } catch (err) {
        // One message for both failures. Saying which half was wrong would turn this form into
        // a way to discover which addresses exist.
        setError(
          err instanceof ApiError && err.status === 401
            ? "Incorrect email or password."
            : "We couldn't sign you in just now. Please try again.",
        )
        setSubmitting(false)
      }
    },
    [email, password, submitting, intended, navigate],
  )

  if (checking) {
    return (
      <div className="night-room flex min-h-screen items-center justify-center">
        <Spinner label="Checking your session…" block />
      </div>
    )
  }

  return (
    <div className="night-room flex min-h-screen flex-col px-5 py-8">
      <header>
        <Link to="/" aria-label="InterMind home" className="inline-flex min-h-[44px] items-center">
          <Logo size={24} tone="onDark" />
        </Link>
      </header>

      <main id="main" className="flex flex-1 items-center justify-center">
        <div className="w-full max-w-sm pb-16">
          <h1 className="type-section text-balance text-fg">Welcome back</h1>
          <p className="mt-3 text-[0.9375rem] leading-relaxed text-fg-soft">
            Sign in to your InterMind workspace.
          </p>

          <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-5" noValidate>
            <div className="flex flex-col gap-2">
              <label htmlFor="recruiter-email" className="text-sm font-medium text-fg">
                Email address
              </label>
              <input
                id="recruiter-email"
                name="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="username"
                autoFocus
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "recruiter-signin-error" : undefined}
                className="min-h-[48px] w-full rounded-[12px] border border-hair-strong bg-raise px-4 text-[0.9375rem] text-fg outline-none transition-colors duration-200 focus:border-accent"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="recruiter-password" className="text-sm font-medium text-fg">
                Password
              </label>
              <input
                id="recruiter-password"
                name="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "recruiter-signin-error" : undefined}
                className="min-h-[48px] w-full rounded-[12px] border border-hair-strong bg-raise px-4 text-[0.9375rem] text-fg outline-none transition-colors duration-200 focus:border-accent"
              />
            </div>

            {error && (
              <p id="recruiter-signin-error" role="alert" className="text-sm text-rose-300">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || !email.trim() || !password}
              className="mt-1 inline-flex min-h-[48px] items-center justify-center rounded-full bg-fg px-7 font-medium text-canvas transition-colors duration-200 hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
            {/* Announced without stealing focus from the form. */}
            <span aria-live="polite" className="sr-only">
              {submitting ? "Signing in" : ""}
            </span>
          </form>

          <p className="mt-8 text-sm text-fg-muted">
            New to InterMind?{" "}
            <Link
              to={SIGNUP}
              className="underline decoration-hair-strong underline-offset-2 transition-colors hover:text-fg"
            >
              Create an account
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
