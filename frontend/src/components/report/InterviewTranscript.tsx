import { motion } from "motion/react"
import { rise } from "../../design/motion"
import type { CandidateAnswerTurn } from "../../types"

interface InterviewTranscriptProps {
  /** Every answered turn, in the order the interview produced them. */
  turns: CandidateAnswerTurn[]
  /**
   * Coverage-target ids from the plan. A turn whose `question_id` is one of these was a main
   * question; anything else carries a follow-up's own id, which is the same rule the backend
   * uses to attribute a turn (see `build_question_evaluations`). Empty when the plan could not
   * be loaded, in which case every turn is simply numbered.
   */
  targetIds: string[]
}

/**
 * The interview as it actually happened: each question in order, with the answer it got.
 *
 * Distinct from the evidence view above it. That one is per requirement and reports the answer
 * that settled each area, so a requirement explored over two turns appears once there. This is
 * the conversation, so both turns appear, in sequence.
 *
 * Nothing here is derived or synthesised: the turns come straight from the interview's own
 * history, and a target the interview never actually asked about (established from an answer to
 * something else) is filtered out before it reaches this component, because it was never put to
 * the candidate.
 */
export function InterviewTranscript({ turns, targetIds }: InterviewTranscriptProps) {
  const targets = new Set(targetIds)
  const canTellFollowUps = targets.size > 0
  const isFollowUp = (turn: CandidateAnswerTurn) =>
    canTellFollowUps && !targets.has(turn.question_id)

  // Positions count main questions only, so a follow-up never takes a number of its own.
  const rows = turns.map((turn, index) => ({
    turn,
    followUp: isFollowUp(turn),
    position: isFollowUp(turn)
      ? null
      : turns.slice(0, index + 1).filter((t) => !isFollowUp(t)).length,
  }))

  return (
    <ol className="flex flex-col">
      {rows.map(({ turn, followUp, position }, index) => (
        <motion.li
          key={`${turn.question_id}-${index}`}
          variants={rise}
          className="border-b border-hair py-6 first:pt-2 last:border-0"
        >
          <p className="type-data text-fg-muted">
            {followUp ? "Follow-up" : `Question ${position}`}
          </p>

          <div className="mt-3 flex flex-col gap-4">
            <div>
              <p className="type-data text-fg-muted">InterMind asked</p>
              <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-fg">{turn.question}</p>
            </div>
            <div>
              <p className="type-data text-fg-muted">They answered</p>
              {turn.answer.trim() ? (
                <p className="mt-1.5 whitespace-pre-line text-[0.9375rem] leading-relaxed text-fg-soft">
                  {turn.answer}
                </p>
              ) : (
                <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-fg-muted">
                  No answer was recorded for this question.
                </p>
              )}
            </div>
          </div>
        </motion.li>
      ))}
    </ol>
  )
}
