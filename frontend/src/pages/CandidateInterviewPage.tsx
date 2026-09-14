import { useCallback, useEffect, useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { getInterview, submitAnswer } from "../api/interviews"
import { getInterviewPlan } from "../api/interviewPlans"
import { getJob } from "../api/jobs"
import { ApiError } from "../api/client"
import { useAsyncData } from "../hooks/useAsyncData"
import { Spinner } from "../components/ui/Spinner"
import { ErrorBanner } from "../components/ui/ErrorBanner"
import { ProgressBar } from "../components/ui/ProgressBar"
import { QuestionCard } from "../components/interview/QuestionCard"
import { AnswerForm } from "../components/interview/AnswerForm"
import { CompletionScreen } from "../components/interview/CompletionScreen"
import type { InterviewState } from "../types"

export function CandidateInterviewPage() {
  const { interviewId } = useParams<{ interviewId: string }>()

  const interviewFetcher = useCallback(() => getInterview(interviewId!), [interviewId])
  const initial = useAsyncData(interviewFetcher, [interviewId])

  const [interview, setInterview] = useState<InterviewState | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (initial.data) setInterview(initial.data)
  }, [initial.data])

  const jobId = interview?.job_id
  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId], Boolean(jobId))
  const plan = useAsyncData(planFetcher, [jobId], Boolean(jobId))

  const currentQuestionMeta = useMemo(() => {
    if (!plan.data || !interview?.current_question_id) return undefined
    return plan.data.questions.find((q) => q.id === interview.current_question_id)
  }, [plan.data, interview?.current_question_id])

  async function handleSubmitAnswer(answer: string) {
    if (!interviewId || isSubmitting) return
    setIsSubmitting(true)
    setSubmitError(null)
    try {
      const updated = await submitAnswer(interviewId, answer)
      setInterview(updated)
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : "Something went wrong submitting your answer.",
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  if (initial.isLoading || !interview) {
    return <Spinner label="Loading interview…" />
  }

  if (initial.error) {
    return <ErrorBanner message={initial.error} onRetry={initial.refetch} />
  }

  const isFollowUp = interview.last_evaluation?.decision === "follow_up" && !interview.finished
  const totalQuestions = plan.data?.questions.length ?? interview.asked_question_ids.length
  const currentPosition = Math.max(interview.asked_question_ids.length - 1, 0)

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        {job.data && (
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            {job.data.job_spec.role_title}
          </p>
        )}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">
          Candidate Interview
        </h1>
      </div>

      {!interview.finished && <ProgressBar current={currentPosition} total={totalQuestions} />}

      {submitError && <ErrorBanner message={submitError} />}

      {interview.finished ? (
        <CompletionScreen interviewId={interview.interview_id} />
      ) : (
        <>
          <QuestionCard
            questionText={interview.current_question_text ?? ""}
            category={currentQuestionMeta?.category}
            target={currentQuestionMeta?.target}
            isFollowUp={isFollowUp}
          />
          <AnswerForm
            onSubmit={handleSubmitAnswer}
            isSubmitting={isSubmitting}
            questionKey={`${interview.current_question_id ?? ""}-${interview.turn_index}`}
          />
        </>
      )}
    </div>
  )
}
