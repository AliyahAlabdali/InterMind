import { useEffect, useState } from "react"
import { Navigate, useLocation } from "react-router-dom"
import { getRecruiterSession } from "../api/auth"
import { Spinner } from "../components/ui/Spinner"
import { LOGIN } from "./routes"

/**
 * Gate for recruiter-only routes.
 *
 * Redirects to sign-in rather than rendering a sign-in form in place, which is the change that
 * matters: a visitor who lands on a recruiter URL now ends up somewhere that is obviously a
 * sign-in page, at a URL that says so, and can navigate away to the product.
 *
 * The route they asked for is carried in `location.state` so signing in returns them to it
 * instead of dumping everyone on the workspace home - one line of router state, no
 * query-string round-trip and nothing to parse back out.
 *
 * Candidate routes never touch this. They authenticate with the token in their own invitation
 * link (`useCandidateToken`), and a candidate must never be asked to sign in as a recruiter.
 */
export function RequireRecruiter({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    getRecruiterSession()
      .then((state) => {
        if (!cancelled) setAuthenticated(state.authenticated)
      })
      .catch(() => {
        // An unreachable backend is not a session. Sign-in is the usable next step either way,
        // and it surfaces the real error there rather than behind a spinner.
        if (!cancelled) setAuthenticated(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (authenticated === null) {
    return (
      <div className="night-room flex min-h-screen items-center justify-center">
        <Spinner label="Checking your session…" block />
      </div>
    )
  }

  if (!authenticated) {
    return (
      <Navigate
        to={LOGIN}
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }

  return <>{children}</>
}
