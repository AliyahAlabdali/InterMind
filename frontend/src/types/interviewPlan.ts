import type { OccupationMatch } from "./occupation"

export type EvidenceSource = "jobspec" | "onet" | "both"

export type QuestionCategory = "competency" | "technology" | "task"

export type RequirementLevel = "required" | "preferred"

export type AssessmentStatus = "not_assessed"

export interface CompetencyCoverage {
  name: string
  source: EvidenceSource
  onet_importance: number | null
  onet_level: number | null
}

export interface SelectedTechnology {
  name: string
  source: EvidenceSource
  required: boolean | null
  hot: boolean
  in_demand: boolean
}

export interface SelectedTask {
  task: string
  source: EvidenceSource
}

// One thing the interview can assess - not a pre-written question. The actual question text is
// generated live, during each candidate's interview, once the adaptive interviewer actually
// reaches this target - see the backend's app.agents.interview_graph. `assessment_status` is
// always "not_assessed" here: this is the plan, reviewed before any candidate has started: real,
// per-candidate progress lives in that candidate's own interview/report, not on the plan.
export interface CoverageTarget {
  id: string
  target: string
  category: QuestionCategory
  requirement_level: RequirementLevel
  source: EvidenceSource
  priority: number
  grounding: string
  assessment_status: AssessmentStatus
}

export interface InterviewPlan {
  job_id: string
  role_title: string
  occupation_match: OccupationMatch
  alternate_matches: OccupationMatch[]
  onet_grounding_used: boolean
  onet_context: string
  competencies: CompetencyCoverage[]
  technologies: SelectedTechnology[]
  tasks: SelectedTask[]
  coverage_targets: CoverageTarget[]
}
