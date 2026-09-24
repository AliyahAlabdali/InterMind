import type { CoverageTarget, InterviewState } from "../types"

export interface CoverageSummary {
  total: number
  assessed: number
  remaining: number
  /** 0..1 - share of the plan's targets the interview has moved past. */
  ratio: number
  assessedIds: Set<string>
  /** The target currently being explored, if the interview is mid-question. */
  activeId: string | null
}

/**
 * Derive how far an interview has got through its plan's coverage targets.
 *
 * Counted from `history` - the turns that actually produced evidence - rather than from
 * `asked_question_ids`. The distinction matters because a target can be assessed without ever
 * being asked: when an answer to one question also establishes another target, the graph
 * records a `cross_target` turn for it (see `app/services/cross_target_evidence.py`) and closes
 * it out. Those targets never enter `asked_question_ids`, so counting asked questions reported
 * an interview as less complete than it was - the report said every required area was reached
 * while this indicator was still showing one of three.
 *
 * A history turn carries the target's own id in `question_id` for both kinds of evidence, so
 * intersecting with the plan's ids is all that is needed. It also filters out follow-up turns,
 * whose ids are synthesized per follow-up and are never targets of their own - the target they
 * belong to is already counted from the turn that first answered it.
 *
 * On the target currently on screen: it counts once it has an answered turn, and never merely
 * for being displayed. So a question that has been asked but not yet answered does not count,
 * while a target being pressed further by a follow-up does - it has already been explored, and
 * the follow-up is InterMind going deeper rather than starting over. `activeId` remains the
 * target of the question on screen, for callers that want to show where the interview is.
 *
 * Deliberately *not* a percentage of a score: until an interview completes there is no score,
 * and showing one would be inventing data. Coverage is the honest progress metric, and it also
 * happens to be the one that reinforces that InterMind is target-driven rather than a fixed
 * questionnaire (brief §17).
 */
export function summarizeCoverage(
  // Only `id` is read, so this accepts the reduced `CandidateInterviewPlan` targets the
  // candidate screen receives as well as the recruiter's full `CoverageTarget`.
  targets: Pick<CoverageTarget, "id">[],
  interview: Pick<InterviewState, "history" | "current_question_id"> | null,
): CoverageSummary {
  const total = targets.length
  if (!interview) {
    return { total, assessed: 0, remaining: total, ratio: 0, assessedIds: new Set(), activeId: null }
  }

  const targetIds = new Set(targets.map((target) => target.id))
  const assessedIds = new Set(
    (interview.history ?? [])
      .map((turn) => turn.question_id)
      .filter((id) => targetIds.has(id)),
  )
  const assessed = assessedIds.size

  const activeId =
    interview.current_question_id && targetIds.has(interview.current_question_id)
      ? interview.current_question_id
      : null

  return {
    total,
    assessed,
    remaining: Math.max(total - assessed, 0),
    ratio: total > 0 ? assessed / total : 0,
    assessedIds,
    activeId,
  }
}
