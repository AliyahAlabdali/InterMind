import type { CompetencyCoverage } from "../../types"
import { Card } from "../ui/Card"
import { ProvenanceBadge } from "../ui/ProvenanceBadge"

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
            <div className="flex items-center gap-2">
              {competency.onet_importance !== null && (
                <span className="text-xs text-ink-muted">
                  Importance {competency.onet_importance.toFixed(1)}
                </span>
              )}
              <ProvenanceBadge source={competency.source} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
