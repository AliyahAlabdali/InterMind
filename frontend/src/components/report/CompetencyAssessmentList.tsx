import type { CompetencyAssessment } from "../../types"
import { Card } from "../ui/Card"
import { CompetencyAssessmentCard } from "./CompetencyAssessmentCard"

export function CompetencyAssessmentList({
  assessments,
}: {
  assessments: CompetencyAssessment[]
}) {
  if (assessments.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Competency Assessments
      </h3>
      <div className="flex flex-col gap-3">
        {assessments.map((assessment) => (
          <CompetencyAssessmentCard key={`${assessment.category}-${assessment.name}`} assessment={assessment} />
        ))}
      </div>
    </Card>
  )
}
