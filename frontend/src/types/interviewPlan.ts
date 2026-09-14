import type { OccupationMatch } from "./occupation"

export type EvidenceSource = "jobspec" | "onet" | "both"

export type QuestionCategory = "competency" | "technology" | "task"

export interface CompetencyCoverage {
  name: string
  source: EvidenceSource
  onet_importance: number | null
  onet_level: number | null
}

export interface SelectedTechnology {
  name: string
  source: EvidenceSource
  hot: boolean
  in_demand: boolean
}

export interface SelectedTask {
  task: string
  source: EvidenceSource
}

export interface InterviewQuestion {
  id: string
  category: QuestionCategory
  text: string
  target: string
  grounding: string
}

export interface InterviewPlan {
  job_id: string
  occupation_match: OccupationMatch
  alternate_matches: OccupationMatch[]
  competencies: CompetencyCoverage[]
  technologies: SelectedTechnology[]
  tasks: SelectedTask[]
  questions: InterviewQuestion[]
}
