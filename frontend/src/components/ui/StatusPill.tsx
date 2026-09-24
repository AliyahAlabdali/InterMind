import type { InterviewStatus } from "../../types"

interface StatusPillProps {
  status: InterviewStatus
  className?: string
}

/**
 * An interview's status, told three ways at once: a word, a mark whose *shape* differs per
 * state, and only then a colour. Colour alone would leave the difference between "in progress"
 * and "completed" invisible to a viewer who cannot separate the two hues.
 *
 * Takes no tone. Every colour resolves from the surface it is rendered on, so the same markup
 * is indigo-and-green on a light page and pale-sky-and-mint inside the night room.
 */
const LABEL: Record<InterviewStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  completed: "Completed",
}

const TONE: Record<InterviewStatus, string> = {
  not_started: "text-fg-muted",
  in_progress: "text-accent",
  completed: "text-ok",
}

export function StatusPill({ status, className = "" }: StatusPillProps) {
  return (
    <span className={`inline-flex items-center gap-2 text-sm ${TONE[status]} ${className}`}>
      <Mark status={status} />
      {LABEL[status]}
    </span>
  )
}

function Mark({ status }: { status: InterviewStatus }) {
  // Hollow ring = waiting, pulsing dot = running, check = done. Each inherits the label's
  // colour, so the mark and the word can never drift apart.
  if (status === "not_started") {
    return (
      <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full border border-current" />
    )
  }

  if (status === "in_progress") {
    return <span aria-hidden="true" className="think-dot h-2 w-2 shrink-0 rounded-full bg-current" />
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 12 12" className="h-3 w-3 shrink-0">
      <path
        d="M2.5 6.4l2.2 2.2L9.5 3.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
