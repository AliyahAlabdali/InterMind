import type { CompetencyAssessment } from "../../types"
import { formatCategory } from "../../lib/format"
import { Badge } from "../ui/Badge"

const EVIDENCE_STRENGTH_TONE = {
  strong: "success",
  moderate: "sky",
  limited: "warning",
  insufficient: "neutral",
  not_assessed: "neutral",
} as const

// Rendered as one clear "{Category} · {Evidence label}" line rather than two separate,
// unlabeled badges sitting side by side - a real report review found the latter unreadable at
// a glance (e.g. two adjacent badges reading as one run-on string like "PythonTechnology" or
// "AdvancedInsufficient evidence"). `evidence_label` is the backend's evidence-type-aware label
// (see app.domain.evaluation.evidence_label) - more precise than the score-only
// `evidence_strength` band, since it can say "No evidence" vs "Insufficient evidence" vs
// "Unverified claim" instead of collapsing all of them into one generic phrase.
export function CompetencyAssessmentCard({ assessment }: { assessment: CompetencyAssessment }) {
  return (
    <div className="rounded-[10px] border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{assessment.name}</span>
        <span className="flex items-center gap-1.5 text-xs text-ink-muted">
          {formatCategory(assessment.category)}
          <span aria-hidden="true">·</span>
          <Badge tone={EVIDENCE_STRENGTH_TONE[assessment.evidence_strength]}>
            {assessment.evidence_label}
          </Badge>
        </span>
      </div>

      {(assessment.strengths.length > 0 || assessment.weaknesses.length > 0) && (
        <div className="mt-3 flex flex-col gap-1 text-xs">
          {assessment.strengths.map((item, i) => (
            <p key={`s-${i}`} className="text-success">
              + {item}
            </p>
          ))}
          {assessment.weaknesses.map((item, i) => (
            <p key={`w-${i}`} className="text-warning">
              • {item}
            </p>
          ))}
        </div>
      )}

      {assessment.evidence.length > 0 && (
        <div className="mt-3 border-t border-border pt-2">
          <p className="mb-1 text-xs font-medium text-ink-muted">Evidence</p>
          <ul className="flex flex-col gap-1">
            {assessment.evidence.map((item, i) => (
              <li key={i} className="text-xs italic text-ink-muted">
                “{item}”
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
