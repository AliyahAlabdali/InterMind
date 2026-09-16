import type { InterviewStatus } from "../../types"
import { Badge } from "./Badge"

const STATUS_CONFIG: Record<InterviewStatus, { label: string; tone: "neutral" | "sky" | "success" }> = {
  not_started: { label: "Not started", tone: "neutral" },
  in_progress: { label: "In progress", tone: "sky" },
  completed: { label: "Completed", tone: "success" },
}

export function StatusBadge({ status }: { status: InterviewStatus }) {
  const config = STATUS_CONFIG[status]
  return <Badge tone={config.tone}>{config.label}</Badge>
}
