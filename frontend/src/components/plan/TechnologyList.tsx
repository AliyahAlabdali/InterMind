import type { SelectedTechnology } from "../../types"
import { Card } from "../ui/Card"

// Internal knowledge-source provenance (job description vs. O*NET) is intentionally not shown
// here - see CompetencyList's comment. `hot`/`in_demand` are also O*NET-derived market signals
// rather than JD content, so they're left off the default view for the same reason.
export function TechnologyList({ technologies }: { technologies: SelectedTechnology[] }) {
  if (technologies.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Technologies
      </h3>
      <ul className="flex flex-col gap-3">
        {technologies.map((tech) => (
          <li
            key={tech.name}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-ivory-200 pb-3 last:border-0 last:pb-0"
          >
            <span className="text-sm font-medium text-ink">{tech.name}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
