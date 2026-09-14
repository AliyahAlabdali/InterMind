import type { Recommendation } from "../../types"
import { formatRecommendation } from "../../lib/format"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"
import { ScoreGauge } from "../ui/ScoreGauge"

const RECOMMENDATION_TONE: Record<Recommendation, "success" | "sky" | "warning" | "danger"> = {
  strong_hire: "success",
  hire: "sky",
  consider: "warning",
  no_hire: "danger",
}

interface ReportHeaderProps {
  roleTitle: string | null
  overallScore: number
  recommendation: Recommendation
}

export function ReportHeader({ roleTitle, overallScore, recommendation }: ReportHeaderProps) {
  return (
    <Card className="flex flex-wrap items-center justify-between gap-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Interview Report
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">
          {roleTitle ?? "Candidate Evaluation"}
        </h1>
        <div className="mt-3">
          <Badge tone={RECOMMENDATION_TONE[recommendation]} className="text-sm">
            {formatRecommendation(recommendation)}
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
