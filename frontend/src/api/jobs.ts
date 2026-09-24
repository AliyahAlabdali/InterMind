import { apiGet, apiPost } from "./client"
import type { Job } from "../types"

/**
 * Creating and listing jobs are recruiter-only and owner-scoped on the backend (see
 * `app/api/routes/jobs.py`): one is a write that spends an LLM call, the other returns only the
 * signed-in recruiter's own roles. Reading a single job is deliberately public and answers with
 * a reduced shape that carries no `job_description`, because the candidate's interview screen
 * needs it to name the role they are interviewing for and a candidate holds only their own
 * interview's token.
 *
 * Neither carries a credential: the recruiter session cookie authenticates them.
 */

export function createJob(jobDescription: string): Promise<Job> {
  return apiPost<Job>("/jobs", { job_description: jobDescription })
}

/** Unauthenticated on purpose - also called by the candidate interview. */
export function getJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${encodeURIComponent(jobId)}`)
}

export function listJobs(): Promise<Job[]> {
  return apiGet<Job[]>("/jobs")
}
