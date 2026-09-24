import { apiGet } from "./client"
import type { ActivityEvent } from "../types"

/** Recruiter-only: the real event log behind the workspace activity stream. */
export function listActivity(limit = 20): Promise<ActivityEvent[]> {
  return apiGet<ActivityEvent[]>(`/activity?limit=${encodeURIComponent(String(limit))}`)
}
