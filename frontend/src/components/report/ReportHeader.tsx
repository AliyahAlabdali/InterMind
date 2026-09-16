import type { EvidenceStrength, Recommendation } from "../../types"
import { formatEvidenceStrength, formatRecommendation } from "../../lib/format"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"
import { ScoreGauge } from "../ui/ScoreGauge"

const RECOMMENDATION_TONE: Record<Recommendation, "success" | "sky" | "warning" | "danger"> = {
  strong_hire: "success",
  hire: "sky",
  consider: "warning",
  no_hire: "danger",
}

const EVIDENCE_STRENGTH_TONE: Record<EvidenceStrength, "success" | "sky" | "warning" | "neutral"> = {
  strong: "success",
  moderate: "sky",
  limited: "warning",
  insufficient: "neutral",
  not_assessed: "neutral",
}

interface ReportHeaderProps {
  roleTitle: string | null
  overallScore: number
  overallEvidenceStrength: EvidenceStrength
  recommendation: Recommendation
}

export function ReportHeader({
  roleTitle,
  overallScore,
  overallEvidenceStrength,
  recommendation,
}: ReportHeaderProps) {
  return (
    <Card className="flex flex-wrap items-center justify-between gap-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Interview Report
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">
          {roleTitle ?? "Candidate Evaluation"}
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge tone={RECOMMENDATION_TONE[recommendation]} className="text-sm">
            {formatRecommendation(recommendation)}
          </Badge>
          <Badge tone={EVIDENCE_STRENGTH_TONE[overallEvidenceStrength]}>
            {formatEvidenceStrength(overallEvidenceStrength)}
          </Badge>
        </div>
      </div>
      <div className="flex flex-col items-center gap-1">
        <ScoreGauge score={overallScore} size={104} />
        <span className="text-xs font-medium text-ink-muted">Overall Score</span>
      </div>
    </Card>
  )
}
