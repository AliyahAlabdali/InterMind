import { useEffect } from "react"
import { useSearchParams } from "react-router-dom"
import { getStoredCandidateToken, storeCandidateToken } from "../lib/candidateAccess"

/**
 * Resolves the candidate access token for `interviewId` (Milestone 4 access boundary - see
 * `app.api.auth` on the backend): prefers a `?token=` query param (present on the link the
 * recruiter generated), persisting it to `sessionStorage` for this tab so it survives
 * navigating to a sub-route/refreshing without that param still in the URL; falls back to
 * whatever was already stored otherwise. Returns `null` only when neither source has it (e.g.
 * a stale/bookmarked link missing the token) - callers still attempt the API call and let the
 * resulting 401 surface through the normal error UI, rather than guessing.
 */
export function useCandidateToken(interviewId: string | undefined): string | null {
  const [searchParams] = useSearchParams()
  const urlToken = searchParams.get("token")

  useEffect(() => {
    if (interviewId && urlToken) {
      storeCandidateToken(interviewId, urlToken)
    }
  }, [interviewId, urlToken])

  if (!interviewId) return null
  return urlToken ?? getStoredCandidateToken(interviewId)
}
