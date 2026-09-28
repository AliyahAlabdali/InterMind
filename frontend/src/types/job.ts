export type Seniority =
  | "intern"
  | "junior"
  | "mid"
  | "senior"
  | "lead"
  | "principal"
  | "unknown"

export interface Skill {
  name: string
  required: boolean
}

export interface Competency {
  name: string
  description: string | null
}

export interface JobSpec {
  role_title: string
  seniority: Seniority
  skills: Skill[]
  competencies: Competency[]
  responsibilities: string[]
  summary: string | null
}

export interface Job {
  id: string
  job_description: string
  job_spec: JobSpec
  created_at: string
}

/**
 * What `GET /jobs/{id}` returns to an unauthenticated caller: the role's name, and nothing
 * else. Deliberately not a subset of `Job` - the backend returns a flat `role_title` rather
 * than a nested `job_spec`, so that a public response has no object for a future field to be
 * added to by accident. See `PublicJobResponse` in `backend/app/api/schemas.py`.
 */
export interface PublicJob {
  id: string
  role_title: string
}
