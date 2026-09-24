import { useEffect, useRef } from "react"
import { AnimatePresence, motion } from "motion/react"
import { X } from "lucide-react"
import { transition } from "../../design/motion"
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion"
import type { CandidateAnswerTurn } from "../../types"

interface TranscriptPanelProps {
  turns: CandidateAnswerTurn[]
  open: boolean
  onClose: () => void
}

/**
 * The record of what has been said so far.
 *
 * Written as an interview transcript, not as a chat log: a speaker label, then what they said,
 * ruled off between turns. No bubbles, no avatars, no alignment games - those are the grammar
 * of a messaging app, and they would make the interview look like a conversation with a bot
 * rather than a record someone might later read back.
 *
 * It opens over the stage instead of living beside it, because the transcript is for looking
 * something up, and the moment it competes for space with the question it stops being
 * secondary.
 */
export function TranscriptPanel({ turns, open, onClose }: TranscriptPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const reducedMotion = usePrefersReducedMotion()

  // Escape closes, and focus starts inside the panel rather than staying behind it on the
  // trigger - otherwise a keyboard user opens the transcript and then tabs through the whole
  // interview before reaching it.
  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== "Tab") return

      // Keep Tab inside the panel while it is over the interview: the controls behind it are
      // not reachable by pointer either, so they must not be reachable by keyboard.
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'button, [href], textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50">
          <motion.button
            type="button"
            aria-label="Close the transcript"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={transition.quick}
            className="absolute inset-0 h-full w-full cursor-default bg-black/70"
          />

          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Interview transcript"
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 24, y: 24 }}
            animate={{ opacity: 1, x: 0, y: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 24, y: 24 }}
            transition={transition.state}
            className="absolute inset-x-0 bottom-0 flex max-h-[82dvh] flex-col border-t border-white/12 bg-black sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[min(32rem,92vw)] sm:border-l sm:border-t-0"
          >
            <div className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
              <div>
                <h2 className="type-stage-meta text-sky-pale/70">Transcript</h2>
                <p className="mt-2 text-lg font-medium text-white">
                  {turns.length === 1 ? "1 answer so far" : `${turns.length} answers so far`}
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                aria-label="Close the transcript"
                className="-mr-2 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-sky-pale transition-colors hover:bg-white/10 hover:text-white"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="stage-scroll flex-1 overflow-y-auto overscroll-contain px-6 py-6">
              <ol className="flex flex-col gap-8">
                {turns.map((turn, index) => (
                  <li
                    key={`${turn.question_id}-${index}`}
                    className="border-t border-white/8 pt-6 first:border-0 first:pt-0"
                  >
                    <p className="type-stage-meta text-sky-pale/70">Interviewer</p>
                    <p className="mt-2 leading-relaxed text-white/90">{turn.question}</p>

                    <p className="type-stage-meta mt-5 text-sky-pale/70">You</p>
                    <p className="mt-2 whitespace-pre-wrap leading-relaxed text-sky-pale/80">
                      {turn.answer}
                    </p>
                  </li>
                ))}
              </ol>

              <p className="mt-10 border-t border-white/8 pt-5 text-xs leading-relaxed text-sky-pale/70">
                Answers can't be changed once sent. What gets asked next is chosen from what you
                already said, so an earlier answer is part of the interview from then on.
              </p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
