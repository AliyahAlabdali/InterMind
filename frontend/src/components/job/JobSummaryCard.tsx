import type { Job } from "../../types"
import { formatDate, formatSeniority } from "../../lib/format"
import { Badge } from "../ui/Badge"
import { Card } from "../ui/Card"
import { Button } from "../ui/Button"

interface JobSummaryCardProps {
  job: Job
  onGeneratePlan: () => void
  isGeneratingPlan: boolean
}

export function JobSummaryCard({ job, onGeneratePlan, isGeneratingPlan }: JobSummaryCardProps) {
  const { job_spec: spec } = job

  return (
    <Card className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink">{spec.role_title}</h2>
          <p className="mt-1 text-xs text-ink-muted">Created {formatDate(job.created_at)}</p>
        </div>
        <Badge tone="lilac">{formatSeniority(spec.seniority)}</Badge>
      </div>

      {spec.summary && <p className="text-sm leading-relaxed text-ink-soft">{spec.summary}</p>}

      {spec.skills.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Skills
          </h3>
          <div className="flex flex-wrap gap-2">
            {spec.skills.map((skill) => (
              <Badge key={skill.name} tone={skill.required ? "sky" : "neutral"}>
                {skill.name}
                {!skill.required && " (nice to have)"}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {spec.competencies.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Competencies
          </h3>
          <div className="flex flex-wrap gap-2">
            {spec.competencies.map((competency) => (
              <Badge key={competency.name} tone="blush">
                {competency.name}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {spec.responsibilities.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Responsibilities
          </h3>
          <ul className="flex flex-col gap-1.5">
            {spec.responsibilities.map((responsibility) => (
              <li key={responsibility} className="text-sm text-ink-soft">
                {responsibility}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-end border-t border-border pt-4">
        <Button onClick={onGeneratePlan} isLoading={isGeneratingPlan}>
          Continue to Interview Plan
        </Button>
      </div>
    </Card>
  )
}
