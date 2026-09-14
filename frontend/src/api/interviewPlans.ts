import { apiGet, apiPost } from "./client"
import type { InterviewPlan } from "../types"

export function createInterviewPlan(jobId: string): Promise<InterviewPlan> {
  return apiPost<InterviewPlan>(`/jobs/${encodeURIComponent(jobId)}/interview-plan`)
}

export function getInterviewPlan(jobId: string): Promise<InterviewPlan> {
  return apiGet<InterviewPlan>(`/jobs/${encodeURIComponent(jobId)}/interview-plan`)
}
