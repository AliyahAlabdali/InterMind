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
  /**
   * This candidate's own stable interview access token (see `app.api.auth` on the backend) -
   * the same one minted once when the interview was created, never regenerated. Lets the
   * recruiter recover the candidate's invitation link from this listing at any time (after
   * dismissing the creation dialog, after a page refresh) instead of only ever seeing it once.
   * Recruiter-only, like the rest of this type - never expose it anywhere a candidate could see.
   */
  candidate_access_token: string
}
