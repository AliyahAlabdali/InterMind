import type { QuestionEvaluationSummary } from "../../types"
import { formatCategory, formatPercent } from "../../lib/format"
import { Badge } from "../ui/Badge"

const DECISION_LABEL = {
  advance: "Advanced",
  follow_up: "Follow-up asked",
} as const

export function QuestionEvaluationCard({ item }: { item: QuestionEvaluationSummary }) {
  return (
    <div className="rounded-xl border border-ivory-200 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge tone="neutral">{formatCategory(item.category)}</Badge>
        <span className="text-xs text-ink-muted">Target: {item.target}</span>
        {item.decision && <Badge tone="lilac">{DECISION_LABEL[item.decision]}</Badge>}
        <span className="ml-auto text-sm font-semibold text-ink">{formatPercent(item.score)}</span>
      </div>
      <p className="text-sm font-medium text-ink">{item.question}</p>
      <p className="mt-2 rounded-lg bg-ivory-100 px-3 py-2 text-sm text-ink-soft">
        {item.candidate_answer}
      </p>

      {(item.strengths.length > 0 || item.weaknesses.length > 0) && (
        <div className="mt-2 flex flex-col gap-1 text-xs">
          {item.strengths.map((s, i) => (
            <p key={`s-${i}`} className="text-success">
              + {s}
            </p>
          ))}
          {item.weaknesses.map((w, i) => (
            <p key={`w-${i}`} className="text-danger">
              − {w}
            </p>
          ))}
        </div>
      )}

      {item.evidence.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {item.evidence.map((e, i) => (
            <li key={i} className="text-xs italic text-ink-muted">
              “{e}”
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
