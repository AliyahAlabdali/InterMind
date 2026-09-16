import { useCallback, useEffect } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getInterview } from "../../api/interviews"
import { getInterviewPlan } from "../../api/interviewPlans"
import { getJob } from "../../api/jobs"
import { useAsyncData } from "../../hooks/useAsyncData"
import { useCandidateToken } from "../../hooks/useCandidateToken"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Button } from "../../components/ui/Button"
import { Card } from "../../components/ui/Card"

export function CandidateLandingPage() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()
  const token = useCandidateToken(interviewId)

  const interviewFetcher = useCallback(
    () => getInterview(interviewId!, token ?? ""),
    [interviewId, token],
  )
  const interview = useAsyncData(interviewFetcher, [interviewId, token])

  const jobId = interview.data?.job_id
  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId], Boolean(jobId))
  const plan = useAsyncData(planFetcher, [jobId], Boolean(jobId))

  useEffect(() => {
    if (interview.data?.status === "completed") {
      navigate(`/candidate/interviews/${interviewId}/complete`, { replace: true })
    }
  }, [interview.data?.status, interviewId, navigate])

  if (interview.isLoading || (interview.data?.status === "completed")) {
    return <Spinner label="Loading your interview…" />
  }

  if (interview.error) {
    return <ErrorBanner message={interview.error} onRetry={interview.refetch} />
  }

  if (!interview.data) return null

  const isResuming = interview.data.status === "in_progress"

  return (
    <div className="flex flex-col items-center gap-8 pt-10 text-center animate-enter sm:pt-16">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          {job.data?.job_spec.role_title ?? "Technical Interview"}
        </p>
        <h1
          className="mt-2 text-3xl font-semibold tracking-tight text-ink"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Technical Interview
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-ink-soft">
          An adaptive interview designed around your role. InterMind will ask questions one at a
          time and may go deeper on a topic based on what you share.
        </p>
      </div>

      {plan.data && (
        <Card className="w-fit px-6 py-3">
          <span className="text-sm font-medium text-ink">{plan.data.questions.length} questions</span>
        </Card>
      )}

      <Button
        onClick={() =>
          // The token is already persisted for this tab by useCandidateToken (sessionStorage),
          // so it doesn't need to keep riding in the URL for internal navigation.
          navigate(`/candidate/interviews/${interviewId}/question/${interview.data!.current_question_id}`)
        }
      >
        {isResuming ? "Continue Interview" : "Begin Interview"}
      </Button>
    </div>
  )
}
