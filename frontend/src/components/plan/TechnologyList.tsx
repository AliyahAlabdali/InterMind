import type { SelectedTechnology } from "../../types"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"
import { ProvenanceBadge } from "../ui/ProvenanceBadge"

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
            <span className="flex items-center gap-2 text-sm font-medium text-ink">
              {tech.name}
              {tech.hot && <Badge tone="danger">Hot</Badge>}
              {tech.in_demand && <Badge tone="warning">In demand</Badge>}
            </span>
            <ProvenanceBadge source={tech.source} />
          </li>
        ))}
      </ul>
    </Card>
  )
}
