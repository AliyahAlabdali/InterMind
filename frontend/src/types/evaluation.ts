export type EvaluationDecision = "advance" | "follow_up"

export interface AnswerEvaluation {
  score: number
  decision: EvaluationDecision
  strengths: string[]
  weaknesses: string[]
  evidence: string[]
  follow_up_needed: boolean
  follow_up_question: string | null
}
