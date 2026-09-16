export type InterviewStatus = "not_started" | "in_progress" | "completed"

export interface CandidateAnswerTurn {
  question_id: string
  question: string
  answer: string
}

/**
 * Candidate-safe interview state - returned to both the recruiter (who generated the link) and
 * the candidate themselves. Deliberately carries no recruiter-only evaluation field (score,
 * decision, strengths, weaknesses, evidence) - only `current_question_is_follow_up`, enough to
 * show a natural "let's explore that further" transition without exposing why. See
 * `CandidateSessionSummary` for the recruiter-only view of a session.
 */
export interface InterviewState {
  interview_id: string
  job_id: string
  candidate_name: string
  candidate_email: string
  status: InterviewStatus
  finished: boolean
  turn_index: number
  current_question_id: string | null
  current_question_text: string | null
  current_question_is_follow_up: boolean
  asked_question_ids: string[]
  history: CandidateAnswerTurn[]
  /**
   * This interview's own access token (Milestone 4 access boundary - see `app.api.auth` on
   * the backend) - only ever populated in the response to starting an interview. The
   * candidate's client must send it back as `Authorization: Bearer <token>` on every later
   * call for this interview id; it is not a recruiter credential and must never be treated as
   * one.
   */
  candidate_access_token: string | null
}
