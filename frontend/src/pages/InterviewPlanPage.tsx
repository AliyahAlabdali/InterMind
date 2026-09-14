import { useCallback, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getJob } from "../api/jobs"
import { getInterviewPlan } from "../api/interviewPlans"
import { startInterview } from "../api/interviews"
import { ApiError } from "../api/client"
import { useAsyncData } from "../hooks/useAsyncData"
import { Spinner } from "../components/ui/Spinner"
import { ErrorBanner } from "../components/ui/ErrorBanner"
import { Badge } from "../components/ui/Badge"
import { Button } from "../components/ui/Button"
import { OccupationMatchCard } from "../components/plan/OccupationMatchCard"
import { CompetencyList } from "../components/plan/CompetencyList"
import { TechnologyList } from "../components/plan/TechnologyList"
import { TaskList } from "../components/plan/TaskList"
import { QuestionList } from "../components/plan/QuestionList"
import { formatSeniority } from "../lib/format"

export function InterviewPlanPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [isStarting, setIsStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])

  const job = useAsyncData(jobFetcher, [jobId])
  const plan = useAsyncData(planFetcher, [jobId])

  async function handleStartInterview() {
    if (!jobId) return
    setIsStarting(true)
    setStartError(null)
    try {
      const interview = await startInterview(jobId)
      navigate(`/interviews/${interview.interview_id}`)
    } catch (err) {
      setStartError(
        err instanceof ApiError ? err.message : "Something went wrong starting the interview.",
      )
      setIsStarting(false)
    }
  }

  if (job.isLoading || plan.isLoading) {
    return <Spinner label="Loading interview plan…" />
  }

  if (job.error || plan.error) {
    return (
      <ErrorBanner
        message={job.error ?? plan.error ?? "Something went wrong."}
        onRetry={() => {
          job.refetch()
          plan.refetch()
        }}
      />
    )
  }

  if (!job.data || !plan.data) return null

  const spec = job.data.job_spec

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{spec.role_title}</h1>
          <div className="mt-2 flex items-center gap-2">
            <Badge tone="lilac">{formatSeniority(spec.seniority)}</Badge>
          </div>
        </div>
        <Button onClick={handleStartInterview} isLoading={isStarting}>
          Start Interview
        </Button>
      </div>

      {startError && <ErrorBanner message={startError} />}

      <OccupationMatchCard
        match={plan.data.occupation_match}
        alternates={plan.data.alternate_matches}
      />

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <CompetencyList competencies={plan.data.competencies} />
        <TechnologyList technologies={plan.data.technologies} />
      </div>

      <TaskList tasks={plan.data.tasks} />
      <QuestionList questions={plan.data.questions} />
    </div>
  )
}
