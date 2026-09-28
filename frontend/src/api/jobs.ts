import { apiGet, apiPost } from "./client"
import type { Job, PublicJob } from "../types"

/**
 * Creating and listing jobs are recruiter-only and owner-scoped on the backend (see
 * `backend/app/api/routes/jobs.py`): one is a write that spends an LLM call, the other returns only the
 * signed-in recruiter's own roles.
 *
 * Reading a single job comes in two shapes, because two very different callers need one:
 * `getJob` is the public, unauthenticated read used by the candidate landing screen, and now
 * returns only the role title; `getJobDetail` is the owner-scoped read used by the recruiter
 * workspace, and returns the whole job. The workspace used to call the public one, which is
 * why minimising it required adding the other rather than simply dropping fields.
 *
 * Neither carries a credential: the recruiter session cookie authenticates them.
 */

export function createJob(jobDescription: string): Promise<Job> {
  return apiPost<Job>("/jobs", { job_description: jobDescription })
}

/**
 * Unauthenticated on purpose - this is what the candidate's interview screen calls before any
 * interview token exists. Returns the role title only; anything richer belongs behind
 * `getJobDetail`.
 */
export function getJob(jobId: string): Promise<PublicJob> {
  return apiGet<PublicJob>(`/jobs/${encodeURIComponent(jobId)}`)
}

/** The whole job, for the recruiter who owns it. 404s for anyone else's job. */
export function getJobDetail(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${encodeURIComponent(jobId)}/detail`)
}

export function listJobs(): Promise<Job[]> {
  return apiGet<Job[]>("/jobs")
}
