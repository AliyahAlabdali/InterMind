import type { EvaluationDecision } from "./evaluation"
import type { QuestionCategory } from "./interviewPlan"

export type Recommendation = "strong_hire" | "hire" | "consider" | "no_hire"

export type EvidenceStrength = "not_assessed" | "insufficient" | "limited" | "moderate" | "strong"

export interface QuestionEvaluationSummary {
  question_id: string
  question: string
  category: QuestionCategory
  target: string
  candidate_answer: string
  score: number | null
  evidence_strength: EvidenceStrength
  decision: EvaluationDecision | null
  evidence: string[]
  strengths: string[]
  weaknesses: string[]
}

export interface CompetencyAssessment {
  name: string
  category: QuestionCategory
  score: number | null
  evidence_strength: EvidenceStrength
  evidence: string[]
  strengths: string[]
  weaknesses: string[]
}

export interface InterviewReport {
  interview_id: string
  job_id: string
  overall_score: number
  overall_evidence_strength: EvidenceStrength
  recommendation: Recommendation
  summary: string
  strengths: string[]
  weaknesses: string[]
  competencies: CompetencyAssessment[]
  question_evaluations: QuestionEvaluationSummary[]
}
