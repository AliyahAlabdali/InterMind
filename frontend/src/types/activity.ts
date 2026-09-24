/** What kind of transition an activity event records. Mirrors `app.domain.activity.ActivityType`. */
export type ActivityType =
  | "interview_started"
  | "evidence_detected"
  | "follow_up_generated"
  | "interview_completed"

/**
 * One recorded moment from a real interview (see `app.domain.activity`). Every event in the
 * workspace feed comes from here - the frontend never synthesises activity.
 */
export interface ActivityEvent {
  id: string
  type: ActivityType
  interview_id: string
  job_id: string
  candidate_name: string
  /** The coverage target the event concerns, where it has one. */
  target: string | null
  created_at: string
}
