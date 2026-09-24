import { useCallback } from "react"
import { Link } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowUpRight, CheckCircle2, CornerDownRight, Dot, Sparkle } from "lucide-react"
import { listActivity } from "../../api/activity"
import { useAsyncData } from "../../hooks/useAsyncData"
import { rise, stagger } from "../../design/motion"
import type { ActivityEvent, ActivityType } from "../../types"

/**
 * What the adaptive interviews have actually been doing, newest first.
 *
 * Every line is a recorded backend event (`GET /activity`) - an interview that really started,
 * evidence the evaluator really recorded, a follow-up the graph really decided on. Nothing is
 * synthesised to make the feed look busy: an empty workspace shows an empty feed.
 *
 * Rendered on the deep panel, where it reads as the system's own voice rather than as another
 * list on the same white surface as everything above it. Each kind of event gets its own glyph
 * as well as its own tone, so the stream is scannable without relying on colour.
 */
const ICON: Record<ActivityType, typeof Dot> = {
  interview_started: Dot,
  evidence_detected: Sparkle,
  follow_up_generated: CornerDownRight,
  interview_completed: CheckCircle2,
}

const TONE: Record<ActivityType, string> = {
  interview_started: "text-fg-muted",
  evidence_detected: "text-accent",
  follow_up_generated: "text-accent",
  interview_completed: "text-fg",
}

function describe(event: ActivityEvent): string {
  switch (event.type) {
    case "interview_started":
      return "started an interview"
    case "evidence_detected":
      return event.target ? `showed evidence of ${event.target}` : "showed new evidence"
    case "follow_up_generated":
      return event.target ? `was asked to go deeper on ${event.target}` : "was asked a follow-up"
    case "interview_completed":
      return "finished their interview"
  }
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 60) return "just now"
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function ActivityStream() {
  const fetcher = useCallback(() => listActivity(12), [])
  const activity = useAsyncData(fetcher, [])

  if (activity.isLoading) {
    return (
      <div className="flex flex-col gap-4 py-6" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-3 max-w-md rounded-full bg-fg/10" style={{ width: "100%" }} />
        ))}
      </div>
    )
  }

  if (activity.error || !activity.data) {
    return <p className="py-6 text-sm text-fg-muted">Activity is unavailable right now.</p>
  }

  if (activity.data.length === 0) {
    return (
      <p className="max-w-lg py-6 text-sm leading-relaxed text-fg-muted">
        Nothing yet. This fills in on its own as candidates answer - every question asked, every
        piece of evidence recorded, every time the interview decides to go deeper.
      </p>
    )
  }

  return (
    <motion.ul variants={stagger(0.04)} initial="hidden" animate="visible" className="flex flex-col">
      {activity.data.map((event) => {
        const Icon = ICON[event.type]
        return (
          <motion.li key={event.id} variants={rise}>
            <Link
              to={`/interviews/${event.job_id}`}
              className="group/row flex min-h-[44px] flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-hair py-3 transition-colors duration-200 hover:border-hair-strong"
            >
              <Icon
                size={14}
                aria-hidden="true"
                className={`relative top-0.5 shrink-0 ${TONE[event.type]}`}
              />
              <span className="font-medium text-fg">{event.candidate_name}</span>
              <span className="text-fg-soft">{describe(event)}</span>
              <span className="type-data ml-auto shrink-0 text-fg-muted">
                {relativeTime(event.created_at)}
              </span>
              <ArrowUpRight
                size={13}
                aria-hidden="true"
                className="row-actions shrink-0 text-accent"
              />
            </Link>
          </motion.li>
        )
      })}
    </motion.ul>
  )
}
