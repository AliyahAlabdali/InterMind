import { INTERVIEWER_POSE, type InterviewerPose } from "../../interviewer/types"
import { clamp } from "./journeyState"

export const PROCESS_STATES = ["thinking", "idle", "speaking", "listening", "followUp", "evidence"] as const
export function processPose(progress: number): InterviewerPose {
  const p = clamp(progress, 0, 5), index = Math.floor(p), mix = p - index
  const a = INTERVIEWER_POSE[PROCESS_STATES[index]], b = INTERVIEWER_POSE[PROCESS_STATES[Math.min(5, index + 1)]]
  return Object.fromEntries(Object.keys(a).map(key => {
    const k = key as keyof InterviewerPose
    return [k, a[k] + (b[k] - a[k]) * mix]
  })) as unknown as InterviewerPose
}
