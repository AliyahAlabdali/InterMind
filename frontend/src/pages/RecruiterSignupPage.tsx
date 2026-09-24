import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { MIN_PASSWORD_LENGTH, getRecruiterSession, recruiterSignup } from "../api/auth"
import { ApiError } from "../api/client"
import { Logo } from "../brand/Logo"
import { Spinner } from "../components/ui/Spinner"
import { useDocumentTitle } from "../hooks/useDocumentTitle"
import { LOGIN, WORKSPACE_HOME } from "../app/routes"

/**
 * Recruiter registration.
 *
 * Email and password only. No company, no name, no job title: InterMind has nowhere to put
 * them and no use for them, and every extra field is one more thing to store and justify.
 *
 * The password is held only in the controlled inputs while it is being typed and is cleared on
 * success. It is never written to browser storage, never put in the URL, and never logged. The
 * length rule is shown before submitting so nobody discovers it by being rejected - but the
 * backend is what enforces it.
 *
 * Confirm-password is a typo guard, checked here only. Nothing about it reaches the server.
 */
export function RecruiterSignupPage() {
  useDocumentTitle("Create your workspace")

  const navigate = useNavigate()
  const [checking, setChecking] = useState(true)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Someone already signed in has no business on a registration form.
  useEffect(() => {
    let cancelled = false
    getRecruiterSession()
      .then((state) => {
        if (cancelled) return
        if (state.authenticated) navigate(WORKSPACE_HOME, { replace: true })
        else setChecking(false)
      })
      .catch(() => {
        if (!cancelled) setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [navigate])

  const mismatch = confirm.length > 0 && password !== confirm
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const canSubmit =
    Boolean(email.trim()) && password.length >= MIN_PASSWORD_LENGTH && password === confirm

  const onSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault()
      if (submitting || !canSubmit) return
      setSubmitting(true)
      setError(null)
      try {
        await recruiterSignup(email.trim(), password)
        setPassword("")
        setConfirm("")
        // Already signed in by the signup response - straight to the workspace, no second
        // round of typing the credentials that were just chosen.
        navigate(WORKSPACE_HOME, { replace: true })
      } catch (err) {
        if (err instanceof ApiError && (err.status === 409 || err.status === 422)) {
          // The backend's own wording: these describe the submitted input and are safe to show.
          setError(err.message)
        } else {
          setError("We couldn't create your account just now. Please try again.")
        }
        setSubmitting(false)
      }
    },
    [canSubmit, email, password, submitting, navigate],
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
        <div className="w-full max-w-sm pb-12">
          <h1 className="type-section text-balance text-fg">Create your workspace</h1>
          <p className="mt-3 text-[0.9375rem] leading-relaxed text-fg-soft">
            Start building adaptive AI interviews with InterMind.
          </p>

          <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-5" noValidate>
            <div className="flex flex-col gap-2">
              <label htmlFor="signup-email" className="text-sm font-medium text-fg">
                Email address
              </label>
              <input
                id="signup-email"
                name="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                autoFocus
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "signup-error" : undefined}
                className="min-h-[48px] w-full rounded-[12px] border border-hair-strong bg-raise px-4 text-[0.9375rem] text-fg outline-none transition-colors duration-200 focus:border-accent"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="signup-password" className="text-sm font-medium text-fg">
                Password
              </label>
              <input
                id="signup-password"
                name="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                required
                aria-invalid={tooShort ? true : undefined}
                aria-describedby="signup-password-hint"
                className="min-h-[48px] w-full rounded-[12px] border border-hair-strong bg-raise px-4 text-[0.9375rem] text-fg outline-none transition-colors duration-200 focus:border-accent"
              />
              {/* Stated up front rather than only on rejection. */}
              <p
                id="signup-password-hint"
                className={`text-sm ${tooShort ? "text-rose-300" : "text-fg-muted"}`}
              >
                At least {MIN_PASSWORD_LENGTH} characters. A passphrase is easier to remember and
                harder to guess.
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="signup-confirm" className="text-sm font-medium text-fg">
                Confirm password
              </label>
              <input
                id="signup-confirm"
                name="confirm-password"
                type="password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
                required
                aria-invalid={mismatch ? true : undefined}
                aria-describedby={mismatch ? "signup-confirm-error" : undefined}
                className="min-h-[48px] w-full rounded-[12px] border border-hair-strong bg-raise px-4 text-[0.9375rem] text-fg outline-none transition-colors duration-200 focus:border-accent"
              />
              {mismatch && (
                <p id="signup-confirm-error" role="alert" className="text-sm text-rose-300">
                  Both passwords must match.
                </p>
              )}
            </div>

            {error && (
              <p id="signup-error" role="alert" className="text-sm text-rose-300">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting || !canSubmit}
              className="mt-1 inline-flex min-h-[48px] items-center justify-center rounded-full bg-fg px-7 font-medium text-canvas transition-colors duration-200 hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? "Creating your workspace…" : "Create account"}
            </button>
            <span aria-live="polite" className="sr-only">
              {submitting ? "Creating your workspace" : ""}
            </span>
          </form>

          <p className="mt-8 text-sm text-fg-muted">
            Already have an account?{" "}
            <Link
              to={LOGIN}
              className="underline decoration-hair-strong underline-offset-2 transition-colors hover:text-fg"
            >
              Sign in
            </Link>
          </p>
        </div>
      </main>
    </div>
  )
}
