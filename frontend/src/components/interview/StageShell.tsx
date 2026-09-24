import { useEffect } from "react"
import type { ReactNode } from "react"
import { Interviewer } from "../../interviewer/Interviewer"
import { StageAtmosphere } from "./StageAtmosphere"

/**
 * The room the interview happens in.
 *
 * Shared by every screen the candidate sees once the interview has started - the live stage,
 * its loading and failure states, and the screen that closes it. They are one continuous
 * moment, and the candidate should never be dropped back onto a white page in the middle of it.
 */
export function Stage({ children }: { children: ReactNode }) {
  // The interview is the one route that inverts, and `body` carries the product's ivory. Left
  // alone it shows through as a pale band under a short stage, and as a flash of white when a
  // phone rubber-bands past the end of the page.
  useEffect(() => {
    const previous = document.body.style.backgroundColor
    document.body.style.backgroundColor = "#000505"
    return () => {
      document.body.style.backgroundColor = previous
    }
  }, [])

  return (
    <div className="stage-room relative flex min-h-[100dvh] flex-col bg-black text-white">
      <StageAtmosphere />
      {children}
    </div>
  )
}

interface StageMessageProps {
  title: string
  body: string
  onRetry?: () => void
}

/**
 * Everything that is not a question: setting up, failing to open, and finishing.
 *
 * Drawn as the same room rather than as a spinner on a white page, and the interviewer is
 * present in all of them. A candidate who has been told they are about to meet an interviewer
 * reads a bare screen with a spinner on it as the product being broken.
 */
export function StageMessage({ title, body, onRetry }: StageMessageProps) {
  return (
    <div className="relative z-10 flex flex-1 flex-col items-center justify-center gap-7 px-6 py-20 text-center">
      <div className="relative">
        <span
          aria-hidden="true"
          className="stage-veil pointer-events-none absolute inset-[-25%] -z-10 rounded-full"
        />
        <Interviewer state="idle" tone="onDark" className="h-36 w-36 sm:h-44 sm:w-44" />
      </div>

      <div role="status" className="flex flex-col items-center gap-3">
        <h1 className="type-sub text-white">{title}</h1>
        <p className="max-w-sm leading-relaxed text-sky-pale/75">{body}</p>
      </div>

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-[44px] items-center rounded-full bg-white px-6 text-sm font-medium text-black transition-colors duration-200 hover:bg-sky-pale"
        >
          Try again
        </button>
      )}
    </div>
  )
}
