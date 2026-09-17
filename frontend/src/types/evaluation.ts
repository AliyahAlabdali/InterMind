export type EvaluationDecision = "advance" | "follow_up"

export type AnswerEvidenceType =
  | "demonstrated"
  | "partial"
  | "claimed_unverified"
  | "explicit_lack"
  | "contradictory"
  | "insufficient"

export interface AnswerEvaluation {
  score: number
  evidence_type: AnswerEvidenceType
  decision: EvaluationDecision
  strengths: string[]
  weaknesses: string[]
  evidence: string[]
  follow_up_needed: boolean
  follow_up_question: string | null
}
