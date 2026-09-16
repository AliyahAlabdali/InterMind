const STORAGE_PREFIX = "intermind:candidate-token:"

/**
 * Persists one interview's candidate access token (Milestone 4 access boundary - see
 * `app.api.auth` on the backend) for the rest of this browser tab's session -
 * `sessionStorage`, not `localStorage`, since this is meant to behave like a short-lived
 * credential, not a saved login. Wrapped in try/catch: storage can be unavailable (private
 * browsing, blocked site data) without that being fatal - the token still works for the
 * current page load via the URL, it just won't survive a refresh.
 */
export function storeCandidateToken(interviewId: string, token: string): void {
  try {
    sessionStorage.setItem(STORAGE_PREFIX + interviewId, token)
  } catch {
    // Ignored - see the function docstring.
  }
}

export function getStoredCandidateToken(interviewId: string): string | null {
  try {
    return sessionStorage.getItem(STORAGE_PREFIX + interviewId)
  } catch {
    return null
  }
}
