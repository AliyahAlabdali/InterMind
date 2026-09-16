import { useCallback } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getJob } from "../../api/jobs"
import { getInterviewPlan } from "../../api/interviewPlans"
import { useAsyncData } from "../../hooks/useAsyncData"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Badge } from "../../components/ui/Badge"
import { Button } from "../../components/ui/Button"
import { PageHeader } from "../../components/ui/PageHeader"
import { OccupationMatchCard } from "../../components/plan/OccupationMatchCard"
import { CompetencyList } from "../../components/plan/CompetencyList"
import { TechnologyList } from "../../components/plan/TechnologyList"
import { TaskList } from "../../components/plan/TaskList"
import { QuestionList } from "../../components/plan/QuestionList"
import { formatSeniority } from "../../lib/format"

export function InterviewPlanPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()

  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])

  const job = useAsyncData(jobFetcher, [jobId])
  const plan = useAsyncData(planFetcher, [jobId])

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
  const competencyCount = new Set(plan.data.questions.map((q) => q.target)).size

  return (
    <div className="flex flex-col gap-6 animate-enter">
      <PageHeader
        eyebrow="Interview Plan"
        title={spec.role_title}
        actions={
          <Button onClick={() => navigate(`/recruiter/interviews/${jobId}`)}>
            View Candidates
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="lilac">{formatSeniority(spec.seniority)}</Badge>
        <span className="text-sm text-ink-muted">
          {plan.data.questions.length} Questions · {competencyCount} Focus Areas
        </span>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <CompetencyList competencies={plan.data.competencies} />
        <TechnologyList technologies={plan.data.technologies} />
      </div>

      <TaskList tasks={plan.data.tasks} />
      <QuestionList questions={plan.data.questions} />

      <OccupationMatchCard
        match={plan.data.occupation_match}
        alternates={plan.data.alternate_matches}
        onetGroundingUsed={plan.data.onet_grounding_used}
      />
    </div>
  )
}
