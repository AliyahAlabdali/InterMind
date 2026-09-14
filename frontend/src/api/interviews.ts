import { apiGet, apiPost } from "./client"
import type { InterviewReport, InterviewState } from "../types"

export function startInterview(jobId: string): Promise<InterviewState> {
  return apiPost<InterviewState>("/interviews", { job_id: jobId })
}

export function getInterview(interviewId: string): Promise<InterviewState> {
  return apiGet<InterviewState>(`/interviews/${encodeURIComponent(interviewId)}`)
}

export function submitAnswer(interviewId: string, answer: string): Promise<InterviewState> {
  return apiPost<InterviewState>(`/interviews/${encodeURIComponent(interviewId)}/answers`, {
    answer,
  })
}

export function getInterviewReport(interviewId: string): Promise<InterviewReport> {
  return apiGet<InterviewReport>(`/interviews/${encodeURIComponent(interviewId)}/report`)
}
