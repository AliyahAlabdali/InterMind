import { useCallback } from "react"
import { useNavigate } from "react-router-dom"
import { listJobInterviews } from "../../api/interviews"
import { useAsyncData } from "../../hooks/useAsyncData"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"
import { formatDate, formatSeniority } from "../../lib/format"
import type { Job } from "../../types"

export function InterviewCard({ job }: { job: Job }) {
  const navigate = useNavigate()
  const fetcher = useCallback(() => listJobInterviews(job.id), [job.id])
  const candidates = useAsyncData(fetcher, [job.id])

  const counts = candidates.data
    ? {
        total: candidates.data.length,
        completed: candidates.data.filter((c) => c.status === "completed").length,
        inProgress: candidates.data.filter((c) => c.status === "in_progress").length,
        notStarted: candidates.data.filter((c) => c.status === "not_started").length,
      }
    : null

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/recruiter/interviews/${job.id}`)}
      onKeyDown={(event) => {
        if (event.key === "Enter") navigate(`/recruiter/interviews/${job.id}`)
      }}
      className="flex cursor-pointer flex-wrap items-center justify-between gap-4 transition-colors hover:border-border-strong"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="truncate text-sm font-semibold text-ink">{job.job_spec.role_title}</h3>
          <Badge tone="lilac">{formatSeniority(job.job_spec.seniority)}</Badge>
        </div>
        <p className="mt-1 text-xs text-ink-muted">Created {formatDate(job.created_at)}</p>
      </div>
      <div className="shrink-0 text-right text-xs text-ink-muted">
        {counts === null ? (
          <span className="inline-block h-4 w-32 animate-pulse rounded bg-ivory-100" />
        ) : counts.total === 0 ? (
          <span>No candidates yet</span>
        ) : (
          <span>
            {counts.total} candidate{counts.total === 1 ? "" : "s"} · {counts.completed}{" "}
            completed · {counts.inProgress} in progress · {counts.notStarted} not started
          </span>
        )}
      </div>
    </Card>
  )
}
