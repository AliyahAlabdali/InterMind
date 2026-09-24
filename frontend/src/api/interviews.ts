import { apiGet, apiPost } from "./client"
import type { CandidateSessionSummary, InterviewReport, InterviewState } from "../types"

// Milestone 4 access boundary (see app.api.auth on the backend): starting a session, reading
// its report, and listing a job's candidates are all recruiter-only. These carry no credential
// of their own - the recruiter session cookie authenticates them, and the browser never holds
// the underlying recruiter secret.

/** Recruiter-only: mints the interview and its own `candidate_access_token` (see
 * `InterviewState`) - the recruiter's invite-link UI is responsible for passing that token on
 * to the candidate; it must never be logged or shown to anyone but the intended candidate. */
export function startInterview(
  jobId: string,
  candidateName: string,
  candidateEmail: string,
): Promise<InterviewState> {
  return apiPost<InterviewState>(
    "/interviews",
    { job_id: jobId, candidate_name: candidateName, candidate_email: candidateEmail },
  )
}

/** `candidateToken` is this interview's own access token (from `startInterview`'s response, or
 * carried in the candidate's link). A recruiter reaches the same endpoint via their session
 * cookie instead, by passing an empty token. */
export function getInterview(interviewId: string, candidateToken: string): Promise<InterviewState> {
  return apiGet<InterviewState>(`/interviews/${encodeURIComponent(interviewId)}`, {
    token: candidateToken,
  })
}

export function submitAnswer(
  interviewId: string,
  answer: string,
  candidateToken: string,
): Promise<InterviewState> {
  return apiPost<InterviewState>(
    `/interviews/${encodeURIComponent(interviewId)}/answers`,
    { answer },
    { token: candidateToken },
  )
}

/** Recruiter-only. */
export function getInterviewReport(interviewId: string): Promise<InterviewReport> {
  return apiGet<InterviewReport>(`/interviews/${encodeURIComponent(interviewId)}/report`)
}

/** Recruiter-only: every candidate session for one job/interview, with live status. */
export function listJobInterviews(jobId: string): Promise<CandidateSessionSummary[]> {
  return apiGet<CandidateSessionSummary[]>(`/jobs/${encodeURIComponent(jobId)}/interviews`)
}
