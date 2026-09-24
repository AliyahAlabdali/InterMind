import { AnimatePresence, motion } from "motion/react"
import { CornerDownRight } from "lucide-react"
import { transition } from "../design/motion"
import { INTERVIEWER_STATUS_LABEL } from "./types"
import type { InterviewerState } from "./types"

interface InterviewerStatusProps {
  state: InterviewerState
  /** Live speech amplitude 0..1 - the bars follow real audio, not a canned loop. */
  level?: number
  className?: string
}

const BAR_COUNT = 5

/**
 * What the interviewer is doing, in one word and one mark.
 *
 * Every state gets its own *shape*, not its own colour: bars that move with real speech, an
 * open ring while the floor is the candidate's, three considering dots, a turn arrow for a
 * follow-up. That is what makes the state legible to someone who cannot distinguish the
 * colours, and it is also why the mark still reads with all motion switched off.
 *
 * This is also the accessible announcement channel for the interviewer, which is otherwise a
 * decorative canvas: the live region means a screen-reader user is told the interview changed
 * hands.
 */
export function InterviewerStatus({ state, level = 0, className = "" }: InterviewerStatusProps) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <span className="flex h-4 w-6 items-center justify-center" aria-hidden="true">
        <StateMark state={state} level={level} />
      </span>

      {/* Only the label is announced. The mark beside it is the same information, drawn. */}
      <span role="status" className="relative block">
        <AnimatePresence mode="wait">
          <motion.span
            key={state}
            initial={{ opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -3 }}
            transition={transition.quick}
            className="type-stage-meta block whitespace-nowrap text-sky-pale"
          >
            {INTERVIEWER_STATUS_LABEL[state]}
          </motion.span>
        </AnimatePresence>
      </span>
    </div>
  )
}

function StateMark({ state, level }: { state: InterviewerState; level: number }) {
  if (state === "speaking") {
    return (
      <span className="flex items-end gap-[3px]">
        {Array.from({ length: BAR_COUNT }, (_, i) => {
          // Centre bars react most, which reads as a voice rather than a meter.
          const weight = 1 - Math.abs(i - (BAR_COUNT - 1) / 2) / BAR_COUNT
          return (
            <motion.span
              key={i}
              className="w-[2px] rounded-full bg-sky-pale"
              animate={{ height: 3 + level * 13 * weight }}
              transition={{ duration: 0.09, ease: "easeOut" }}
              style={{ height: 3 }}
            />
          )
        })}
      </span>
    )
  }

  if (state === "thinking") {
    return (
      <span className="flex items-center gap-1">
        {Array.from({ length: 3 }, (_, i) => (
          <span
            key={i}
            className="think-dot h-[5px] w-[5px] rounded-full bg-sky-pale"
            style={{ animationDelay: `${i * 180}ms` }}
          />
        ))}
      </span>
    )
  }

  if (state === "followUp") {
    return <CornerDownRight size={14} strokeWidth={2} className="text-sky-pale" />
  }

  if (state === "listening") {
    // An open ring: the aperture is held open and nothing is being said into it.
    return <span className="h-[11px] w-[11px] rounded-full border border-sky-pale" />
  }

  return <span className="h-[6px] w-[6px] rounded-full bg-sky-pale/70" />
}
