import type { QuestionEvaluationSummary } from "../../types"
import { formatCategory } from "../../lib/format"
import { Badge } from "../ui/Badge"

const DECISION_LABEL = {
  advance: "Advanced",
  follow_up: "Follow-up asked",
} as const

const EVIDENCE_STRENGTH_TONE = {
  strong: "success",
  moderate: "sky",
  limited: "warning",
  insufficient: "neutral",
  not_assessed: "neutral",
} as const

interface QuestionEvaluationCardProps {
  item: QuestionEvaluationSummary
  index: number
}

// Rendered as "Question N" plus one clear "{Target} · {Category} · {Evidence label}" line -
// see CompetencyAssessmentCard's comment for why separate, unlabeled badges next to each other
// (e.g. a decision badge immediately followed by an evidence badge) read as one run-on string
// at a glance. `evidence_label` is the backend's evidence-type-aware label, more precise than
// the score-only `evidence_strength` band (see app.domain.evaluation.evidence_label).
export function QuestionEvaluationCard({ item, index }: QuestionEvaluationCardProps) {
  return (
    <div className="rounded-[10px] border border-border p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Question {index + 1}
        </span>
        {item.decision && <Badge tone="lilac">{DECISION_LABEL[item.decision]}</Badge>}
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
        <span className="font-medium text-ink">{item.target}</span>
        <span aria-hidden="true">·</span>
        {formatCategory(item.category)}
        <span aria-hidden="true">·</span>
        <Badge tone={EVIDENCE_STRENGTH_TONE[item.evidence_strength]}>{item.evidence_label}</Badge>
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
            <p key={`w-${i}`} className="text-warning">
              • {w}
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
