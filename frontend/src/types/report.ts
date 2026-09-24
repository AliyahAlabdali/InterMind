import type { AnswerEvidenceType, EvaluationDecision } from "./evaluation"
import type { QuestionCategory } from "./interviewPlan"

export type Recommendation = "strong_hire" | "hire" | "consider" | "no_hire"

export type EvidenceStrength = "not_assessed" | "insufficient" | "limited" | "moderate" | "strong"

/** How a target's evidence was gathered - "direct" means a question was asked specifically
 * about it; "cross_target" means the candidate volunteered meaningful evidence for it while
 * answering a different question. Orthogonal to evidence_type/evidence_strength, which
 * describe what the evidence shows, not how it was gathered. */
export type AssessmentMethod = "direct" | "cross_target"

export interface QuestionEvaluationSummary {
  question_id: string
  question: string
  category: QuestionCategory
  target: string
  candidate_answer: string
  score: number | null
  evidence_strength: EvidenceStrength
  evidence_type: AnswerEvidenceType | null
  evidence_label: string
  decision: EvaluationDecision | null
  evidence: string[]
  strengths: string[]
  weaknesses: string[]
  assessment_method: AssessmentMethod
}

export interface CompetencyAssessment {
  name: string
  category: QuestionCategory
  score: number | null
  evidence_strength: EvidenceStrength
  evidence_type: AnswerEvidenceType | null
  evidence_label: string
  evidence: string[]
  strengths: string[]
  weaknesses: string[]
  assessment_method: AssessmentMethod
}

/** Why the adaptive interview stopped. "sufficient_evidence" means every required target got a
 * turn; "budget_exhausted" means the interview's safety cap on total questions was hit first,
 * leaving one or more required targets in `unassessed_required_targets`. Never implies the
 * interview assessed every target in the plan, only that no required one was skipped. */
export type CompletionReason = "sufficient_evidence" | "budget_exhausted"

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
  /** Required coverage targets the interview never reached - distinct from a target that was
   * asked about but produced weak evidence (that appears in `competencies` instead). Never a
   * negative signal about the candidate: the interview simply ended before reaching it. */
  unassessed_required_targets: string[]
  /** Fixed, deterministic clarification of what overall_score/recommendation mean - always
   * present, meant to sit next to the score so it's never misread as "the candidate satisfies
   * X% of the role's requirements". */
  score_basis_note: string
  completion_reason: CompletionReason
}
