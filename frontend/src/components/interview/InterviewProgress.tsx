import { motion } from "motion/react"
import { transition } from "../../design/motion"
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion"

interface InterviewProgressProps {
  /** Areas of the role the interview has finished with. */
  assessed: number
  /** Areas in this role's plan, in total. */
  total: number
  /** Whether one of those areas is the subject of the question on screen. */
  active?: boolean
  className?: string
}

/**
 * How far through the role the conversation has got.
 *
 * Deliberately not "question 4 of 10". The interview has no fixed number of questions - it
 * asks as many as it needs per area, and follows up when an answer leaves something open - so
 * a question counter would be a number the product cannot honour. What is genuinely countable
 * is the areas of the job it has worked through, which is what this shows.
 *
 * Drawn as one tick per area while the count stays glanceable; past that a tick becomes a
 * hairline too thin to read and it collapses to a single bar. Both are the same measurement.
 */
const MAX_TICKS = 14

export function InterviewProgress({
  assessed,
  total,
  active = false,
  className = "",
}: InterviewProgressProps) {
  const reducedMotion = usePrefersReducedMotion()
  if (total <= 0) return null

  const label = `${assessed} of ${total} areas explored`
  const ratio = Math.min(Math.max(assessed / total, 0), 1)

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={assessed}
        aria-label={label}
        className="flex h-[3px] items-stretch gap-[3px]"
      >
        {total <= MAX_TICKS ? (
          Array.from({ length: total }, (_, i) => {
            const done = i < assessed
            const current = active && i === assessed
            return (
              <motion.span
                key={i}
                className={`min-w-[6px] flex-1 rounded-full ${
                  done ? "bg-sky-pale" : current ? "bg-white" : "bg-white/25"
                }`}
                initial={false}
                animate={{ opacity: done || current ? 1 : 0.9 }}
                transition={transition.state}
              />
            )
          })
        ) : (
          <span className="relative flex-1 overflow-hidden rounded-full bg-white/25">
            <motion.span
              className="absolute inset-y-0 left-0 w-full origin-left rounded-full bg-sky-pale"
              initial={reducedMotion ? false : { scaleX: 0 }}
              animate={{ scaleX: ratio }}
              transition={reducedMotion ? { duration: 0 } : transition.emphasis}
            />
          </span>
        )}
      </div>

      {/* The full phrase wraps to three lines in a phone's header and turns a quiet readout
          into the loudest thing up there. Same measurement, fewer words. */}
      <p className="type-stage-meta whitespace-nowrap text-sky-pale/70">
        <span className="hidden sm:inline">{label}</span>
        <span className="sm:hidden">
          {assessed}/{total} areas
        </span>
      </p>
    </div>
  )
}
