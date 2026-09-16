import { apiGet, apiPost } from "./client"
import type { Job } from "../types"

// Note: job/plan endpoints are not part of the Milestone 4 access boundary (see app.api.auth
// on the backend) - only interview start/report/candidate-listing are. Left unauthenticated
// here to match; revisit alongside those endpoints if that scope changes.

export function createJob(jobDescription: string): Promise<Job> {
  return apiPost<Job>("/jobs", { job_description: jobDescription })
}

export function getJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${encodeURIComponent(jobId)}`)
}

export function listJobs(): Promise<Job[]> {
  return apiGet<Job[]>("/jobs")
}
