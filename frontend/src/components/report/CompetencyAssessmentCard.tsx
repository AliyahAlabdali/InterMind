import type { CompetencyAssessment } from "../../types"
import { formatCategory, formatEvidenceStrength } from "../../lib/format"
import { Badge } from "../ui/Badge"

const CATEGORY_TONE = {
  competency: "blush",
  technology: "sky",
  task: "lilac",
} as const

const EVIDENCE_STRENGTH_TONE = {
  strong: "success",
  moderate: "sky",
  limited: "warning",
  insufficient: "neutral",
  not_assessed: "neutral",
} as const

export function CompetencyAssessmentCard({ assessment }: { assessment: CompetencyAssessment }) {
  return (
    <div className="rounded-[10px] border border-border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ink">{assessment.name}</span>
          <Badge tone={CATEGORY_TONE[assessment.category]}>
            {formatCategory(assessment.category)}
          </Badge>
        </div>
        <Badge tone={EVIDENCE_STRENGTH_TONE[assessment.evidence_strength]}>
          {formatEvidenceStrength(assessment.evidence_strength)}
        </Badge>
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
