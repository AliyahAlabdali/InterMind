import type { SelectedTechnology } from "../../types"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"

// Internal knowledge-source provenance (job description vs. O*NET) is intentionally not shown
// here - see CompetencyList's comment. `hot`/`in_demand` are also O*NET-derived market signals
// rather than JD content, so they're left off the default view for the same reason.
//
// Whether a given technology actually gets asked about (and in what order) is decided live,
// adaptively, during each candidate's own interview - see CoverageList for the plan-level
// coverage summary, and a completed candidate's report for what was actually assessed.
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
            {tech.required !== null && (
              <Badge tone={tech.required ? "blush" : "neutral"}>
                {tech.required ? "Required" : "Preferred"}
              </Badge>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}
