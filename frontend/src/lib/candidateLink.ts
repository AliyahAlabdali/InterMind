/** Builds a candidate's interview URL from their stable, never-regenerated access token (see
 * `CandidateSessionSummary.candidate_access_token` / `InterviewState.candidate_access_token` on
 * the backend). The token travels in the link itself - the candidate has no login, so this is
 * the only way their client learns it. Never build this from a recruiter token: that would let
 * the candidate reach recruiter-only endpoints too. */
export function candidateLink(interviewId: string, accessToken: string): string {
  const params = new URLSearchParams({ token: accessToken })
  return `${window.location.origin}/candidate/interviews/${interviewId}?${params.toString()}`
}
