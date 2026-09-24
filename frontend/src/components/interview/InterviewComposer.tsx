import { useEffect, useLayoutEffect } from "react"
import type { RefObject } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ArrowRight, Mic, Square } from "lucide-react"
import { transition } from "../../design/motion"

interface InterviewComposerProps {
  value: string
  onChange: (value: string) => void
  /** Words currently being heard, not yet settled. Display only - never part of `value`. */
  interim: string
  onSubmit: () => void
  /** The interviewer has the floor: thinking about the last answer, or moving on. */
  locked: boolean
  isSubmitting: boolean
  voice: {
    isSupported: boolean
    isUnavailable: boolean
    isRecording: boolean
    notice: string | null
    toggle: () => void
  }
  textareaRef: RefObject<HTMLTextAreaElement | null>
}

const MAX_HEIGHT = 220

/**
 * Where the candidate answers.
 *
 * One surface holding both ways of answering, so speaking is not a mode hidden behind an icon:
 * the same box that shows typed words shows heard ones, and the same row carries both controls.
 * Whichever way the answer arrives, it ends up as text the candidate can still edit before
 * sending - the microphone dictates into the answer, it does not submit for them.
 *
 * The field grows with the answer up to a limit and then scrolls, because an interview answer
 * is a paragraph and a three-line box that never grows makes people write less than they mean
 * to.
 */
export function InterviewComposer({
  value,
  onChange,
  interim,
  onSubmit,
  locked,
  isSubmitting,
  voice,
  textareaRef,
}: InterviewComposerProps) {
  const canSend = Boolean((value + interim).trim()) && !locked

  // Grow to fit what has been written. Measured from `scrollHeight` after a reset to `auto`,
  // which is the only way to let the box shrink again when text is deleted.
  useLayoutEffect(() => {
    const field = textareaRef.current
    if (!field) return
    field.style.height = "auto"
    field.style.height = `${Math.min(field.scrollHeight, MAX_HEIGHT)}px`
  }, [value, interim, textareaRef])

  // Send from the keyboard without trapping Enter, which an answer of several paragraphs needs
  // for its own line breaks.
  useEffect(() => {
    const field = textareaRef.current
    if (!field) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        if (canSend) onSubmit()
      }
    }
    field.addEventListener("keydown", onKeyDown)
    return () => field.removeEventListener("keydown", onKeyDown)
  }, [canSend, onSubmit, textareaRef])

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (canSend) onSubmit()
      }}
      className={`rounded-[22px] border bg-white/[0.045] transition-[border-color,opacity,background-color] duration-300 focus-within:border-sky-pale/60 focus-within:bg-white/[0.06] focus-within:ring-2 focus-within:ring-sky-pale/15 ${
        locked ? "border-white/10 opacity-60" : "border-white/25"
      }`}
    >
      <div className="px-5 pt-4 sm:px-6 sm:pt-5">
        <label htmlFor="answer" className="sr-only">
          Your answer
        </label>
        <textarea
          id="answer"
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={voice.isRecording ? "Listening - just talk" : "Start typing your answer"}
          rows={2}
          disabled={locked}
          // Turned off deliberately: an interview answer is the candidate's own words, and a
          // browser correcting technical vocabulary mid-sentence is worse than a typo.
          spellCheck={false}
          className="block w-full resize-none bg-transparent text-[1.0625rem] leading-relaxed text-white outline-none placeholder:text-sky-pale/60 disabled:cursor-not-allowed"
          style={{ maxHeight: MAX_HEIGHT }}
        />

        {/* Heard but not yet settled. Kept visibly separate from the committed answer above,
            so the candidate can see what the microphone has and what it is still working on -
            and so nothing that is still changing can end up in the answer twice. */}
        <AnimatePresence>
          {interim && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={transition.quick}
              className="mt-1 text-[1.0625rem] leading-relaxed text-sky-pale/70"
            >
              {interim}
              <span className="hearing-caret" aria-hidden="true" />
            </motion.p>
          )}
        </AnimatePresence>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-white/8 px-3 py-3 sm:px-4">
        {voice.isSupported && !voice.isUnavailable ? (
          <button
            type="button"
            onClick={voice.toggle}
            disabled={locked}
            aria-pressed={voice.isRecording}
            aria-label={voice.isRecording ? "Stop the microphone" : "Answer by speaking instead"}
            className={`inline-flex min-h-[44px] items-center gap-2.5 rounded-full border px-4 text-sm transition-colors duration-200 disabled:opacity-40 ${
              voice.isRecording
                ? "border-sky-pale/55 bg-sky-pale/12 text-white"
                : "border-white/25 text-sky-pale hover:border-white/45 hover:text-white"
            }`}
          >
            {voice.isRecording ? (
              <>
                <Square size={13} fill="currentColor" aria-hidden="true" />
                <span className="think-dot h-1.5 w-1.5 rounded-full bg-sky-pale" aria-hidden="true" />
                Stop
              </>
            ) : (
              <>
                <Mic size={15} aria-hidden="true" />
                Speak
              </>
            )}
          </button>
        ) : (
          <p className="max-w-[22rem] px-1 text-xs leading-relaxed text-sky-pale/75">
            {voice.notice ?? "Answer by typing - that works everywhere."}
          </p>
        )}

        <div className="flex items-center gap-3">
          <kbd className="hidden text-[0.6875rem] tracking-wide text-sky-pale/65 sm:block">
            {isMac() ? "⌘" : "Ctrl"} + Enter
          </kbd>
          <button
            type="submit"
            disabled={!canSend || isSubmitting}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-white px-5 text-sm font-medium text-black transition-colors duration-200 hover:bg-sky-pale disabled:cursor-not-allowed disabled:bg-white/14 disabled:text-white/40"
          >
            Send answer
            <ArrowRight size={15} aria-hidden="true" />
          </button>
        </div>
      </div>
    </form>
  )
}

/** Only decides which modifier key to name in the hint. */
function isMac(): boolean {
  if (typeof navigator === "undefined") return false
  return /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent)
}
