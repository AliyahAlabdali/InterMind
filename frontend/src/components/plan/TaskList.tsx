import type { SelectedTask } from "../../types"
import { Card } from "../ui/Card"

// Internal knowledge-source provenance is intentionally not shown here - see CompetencyList's
// comment. Every task rendered here has already been filtered, upstream in
// InterviewPlannerService, for relevance to this job description - see the module docstring in
// app/services/interview_planner.py - so what's left to show is "responsibilities this
// interview covers", not "which system suggested it".
export function TaskList({ tasks }: { tasks: SelectedTask[] }) {
  if (tasks.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Core Tasks / Responsibilities
      </h3>
      <ul className="flex flex-col gap-3">
        {tasks.map((task) => (
          <li
            key={task.task}
            className="border-b border-ivory-200 pb-3 last:border-0 last:pb-0"
          >
            <span className="text-sm text-ink-soft">{task.task}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
