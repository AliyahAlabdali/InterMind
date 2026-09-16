import type { InterviewStatus } from "./interview"
import type { Recommendation } from "./report"

/**
 * Recruiter-only view of one candidate's interview session - never returned to a candidate.
 * Backs the recruiter's candidate table for one interview/role.
 */
export interface CandidateSessionSummary {
  interview_id: string
  candidate_name: string
  candidate_email: string
  status: InterviewStatus
  overall_score: number | null
  recommendation: Recommendation | null
}
