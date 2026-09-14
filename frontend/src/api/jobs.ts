import { apiGet, apiPost } from "./client"
import type { Job } from "../types"

export function createJob(jobDescription: string): Promise<Job> {
  return apiPost<Job>("/jobs", { job_description: jobDescription })
}

export function getJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${encodeURIComponent(jobId)}`)
}
