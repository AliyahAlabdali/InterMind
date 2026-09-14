import type { SelectedTask } from "../../types"
import { Card } from "../ui/Card"
import { ProvenanceBadge } from "../ui/ProvenanceBadge"

export function TaskList({ tasks }: { tasks: SelectedTask[] }) {
  if (tasks.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Core Tasks
      </h3>
      <ul className="flex flex-col gap-3">
        {tasks.map((task) => (
          <li
            key={task.task}
            className="flex flex-wrap items-start justify-between gap-2 border-b border-ivory-200 pb-3 last:border-0 last:pb-0"
          >
            <span className="text-sm text-ink-soft">{task.task}</span>
            <ProvenanceBadge source={task.source} />
          </li>
        ))}
      </ul>
    </Card>
  )
}
