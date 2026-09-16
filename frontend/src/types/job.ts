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
