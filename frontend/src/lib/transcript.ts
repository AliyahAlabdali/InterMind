import type { CandidateAnswerTurn } from "../types"

/**
 * How many questions were actually put to the candidate, and how many of those were follow-ups.
 *
 * A turn whose `question_id` is one of the plan's coverage-target ids was a main question;
 * anything else carries a follow-up's own id. That is the same rule the backend uses to
 * attribute a turn (see `build_question_evaluations`). With no target ids to compare against
 * (the plan could not be loaded) follow-ups cannot be told apart, so none are claimed.
 */
export function transcriptCounts(turns: CandidateAnswerTurn[], targetIds: string[]) {
  const targets = new Set(targetIds)
  const followUps = targets.size > 0 ? turns.filter((t) => !targets.has(t.question_id)).length : 0
  return { total: turns.length, followUps }
}
