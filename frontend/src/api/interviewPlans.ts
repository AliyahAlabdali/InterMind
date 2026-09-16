import { apiGet, apiPost } from "./client"
import type { InterviewPlan } from "../types"

// Note: like job endpoints (see api/jobs.ts), interview-plan endpoints are not part of the
// Milestone 4 access boundary (see app.api.auth on the backend) and are left unauthenticated
// here to match. Resource-level protection for these is Milestone 6-B work.

export function createInterviewPlan(jobId: string): Promise<InterviewPlan> {
  return apiPost<InterviewPlan>(`/jobs/${encodeURIComponent(jobId)}/interview-plan`)
}

export function getInterviewPlan(jobId: string): Promise<InterviewPlan> {
  return apiGet<InterviewPlan>(`/jobs/${encodeURIComponent(jobId)}/interview-plan`)
}
