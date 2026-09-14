import type { AnswerEvaluation } from "./evaluation"

export type InterviewStatus = "not_started" | "in_progress" | "completed"

export interface InterviewState {
  interview_id: string
  job_id: string
  status: InterviewStatus
  finished: boolean
  turn_index: number
  current_question_id: string | null
  current_question_text: string | null
  asked_question_ids: string[]
  last_evaluation: AnswerEvaluation | null
}
