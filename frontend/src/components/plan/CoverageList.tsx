import type { CoverageTarget } from "../../types"
import { formatCategory } from "../../lib/format"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"

const CATEGORY_TONE = {
  competency: "blush",
  technology: "sky",
  task: "lilac",
} as const

// Replaces the old "Generated Questions (N)" list: that implied a fixed, guaranteed script of
// exactly N questions asked in exactly that order. The interview is adaptive - it decides what
// to ask, when, and how many questions to ask based on the candidate's own answers (see the
// backend's app.agents.interview_graph) - so this shows what the interview *can* assess
// (its coverage), not a literal transcript. Every target starts "Not assessed" here because
// this is the plan, reviewed before any candidate has started; a completed candidate's own
// report shows what was actually asked and what evidence it produced.
export function CoverageList({ targets }: { targets: CoverageTarget[] }) {
  if (targets.length === 0) return null

  return (
    <Card>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Interview Coverage
      </h3>
      <p className="mb-4 text-xs text-ink-muted">
        The interview adapts to each candidate's answers. It decides what to ask next and when
        enough evidence has been gathered, so the exact questions asked and their number vary
        per candidate. This lists what the interview is prepared to assess.
      </p>
      <ul className="flex flex-col gap-3">
        {targets.map((target) => (
          <li
            key={target.id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-ivory-200 pb-3 last:border-0 last:pb-0"
          >
            <span className="text-sm font-medium text-ink">{target.target}</span>
            <div className="flex items-center gap-2">
              <Badge tone={CATEGORY_TONE[target.category]}>{formatCategory(target.category)}</Badge>
              <Badge tone={target.requirement_level === "required" ? "blush" : "neutral"}>
                {target.requirement_level === "required" ? "Required" : "Preferred"}
              </Badge>
              <Badge tone="neutral">Not assessed</Badge>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
