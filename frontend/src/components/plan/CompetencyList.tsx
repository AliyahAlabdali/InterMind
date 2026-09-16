import type { CompetencyCoverage } from "../../types"
import { Card } from "../ui/Card"

// Internal knowledge-source provenance (job description vs. O*NET) is intentionally not shown
// here - a recruiter needs to know what the interview will assess, not which internal system
// produced each item. Provenance stays on `competency.source` for debugging, auditability, and
// a possible future "Why is this included?" interaction - see ProvenanceBadge/formatSource.
export function CompetencyList({ competencies }: { competencies: CompetencyCoverage[] }) {
  if (competencies.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Competencies
      </h3>
      <ul className="flex flex-col gap-3">
        {competencies.map((competency) => (
          <li
            key={competency.name}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-ivory-200 pb-3 last:border-0 last:pb-0"
          >
            <span className="text-sm font-medium text-ink">{competency.name}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
