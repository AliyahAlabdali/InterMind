import { apiGet, apiPost } from "./client"
import type { CandidateInterviewPlan, InterviewPlan } from "../types"

// Both endpoints are recruiter-owner scoped on the backend (see app/api/auth.py). The two
// functions below carry the recruiter session cookie and are for workspace screens only.

export function createInterviewPlan(jobId: string): Promise<InterviewPlan> {
  return apiPost<InterviewPlan>(`/jobs/${encodeURIComponent(jobId)}/interview-plan`)
}

export function getInterviewPlan(jobId: string): Promise<InterviewPlan> {
  return apiGet<InterviewPlan>(`/jobs/${encodeURIComponent(jobId)}/interview-plan`)
}

/**
 * The same endpoint, read by the candidate taking the interview.
 *
 * `candidateToken` is this interview's own access token, exactly as `getInterview` uses it. The
 * backend answers a candidate with the reduced `CandidateInterviewPlan`, so this is a different
 * return type rather than the same one fetched differently.
 */
export function getCandidateInterviewPlan(
  jobId: string,
  candidateToken: string,
): Promise<CandidateInterviewPlan> {
  return apiGet<CandidateInterviewPlan>(
    `/jobs/${encodeURIComponent(jobId)}/interview-plan`,
    { token: candidateToken },
  )
}
