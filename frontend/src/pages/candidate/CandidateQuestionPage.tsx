import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getInterview, submitAnswer } from "../../api/interviews"
import { getInterviewPlan } from "../../api/interviewPlans"
import { ApiError } from "../../api/client"
import { useAsyncData } from "../../hooks/useAsyncData"
import { useCandidateToken } from "../../hooks/useCandidateToken"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Button } from "../../components/ui/Button"
import { QuestionProgress } from "../../components/candidate/QuestionProgress"
import { QuestionCard } from "../../components/interview/QuestionCard"
import { AnswerForm } from "../../components/interview/AnswerForm"
import { PreviousAnswerCard } from "../../components/candidate/PreviousAnswerCard"
import type { InterviewState } from "../../types"

export function CandidateQuestionPage() {
  const { interviewId, questionId } = useParams<{ interviewId: string; questionId: string }>()
  const navigate = useNavigate()
  const token = useCandidateToken(interviewId)

  const interviewFetcher = useCallback(
    () => getInterview(interviewId!, token ?? ""),
    [interviewId, token],
  )
  const initial = useAsyncData(interviewFetcher, [interviewId, token])

  const [interview, setInterview] = useState<InterviewState | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (initial.data) setInterview(initial.data)
  }, [initial.data])

  const jobId = interview?.job_id
  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])
  const plan = useAsyncData(planFetcher, [jobId], Boolean(jobId))

  useEffect(() => {
    if (interview?.finished) {
      navigate(`/candidate/interviews/${interviewId}/complete`, { replace: true })
    }
  }, [interview?.finished, interviewId, navigate])

  const viewingIndex = interview ? interview.asked_question_ids.indexOf(questionId ?? "") : -1
  const isViewingCurrent = interview !== null && questionId === interview.current_question_id

  // Stale/unknown question id in the URL (e.g. a bookmarked link from an earlier turn that no
  // longer exists) - fall back to wherever the interview actually is.
  useEffect(() => {
    if (interview && viewingIndex === -1 && interview.current_question_id) {
      navigate(`/candidate/interviews/${interviewId}/question/${interview.current_question_id}`, {
        replace: true,
      })
    }
  }, [interview, viewingIndex, interviewId, navigate])

  const questionMeta = useMemo(() => {
    if (!plan.data || !questionId) return undefined
    // A follow-up's id is never in coverage_targets (it isn't a target of its own - see
    // app.agents.interview_graph) - falls through to `undefined`, same as before.
    return plan.data.coverage_targets.find((t) => t.id === questionId)
  }, [plan.data, questionId])

  const previousTurn = useMemo(() => {
    if (!interview || isViewingCurrent) return undefined
    const turnsForQuestion = interview.history.filter((turn) => turn.question_id === questionId)
    return turnsForQuestion[turnsForQuestion.length - 1]
  }, [interview, isViewingCurrent, questionId])

  async function handleSubmitAnswer(answer: string) {
    if (!interviewId || isSubmitting) return
    setIsSubmitting(true)
    setSubmitError(null)
    try {
      const updated = await submitAnswer(interviewId, answer, token ?? "")
      setInterview(updated)
      if (!updated.finished && updated.current_question_id) {
        navigate(`/candidate/interviews/${interviewId}/question/${updated.current_question_id}`)
      }
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

  const isFollowUp = isViewingCurrent && interview.current_question_is_follow_up

  return (
    <div className="flex flex-col gap-6 pt-6 animate-enter">
      <QuestionProgress
        viewingIndex={Math.max(viewingIndex, 0)}
        askedCount={interview.asked_question_ids.length}
        onSelect={(index) => {
          const targetId = interview.asked_question_ids[index]
          if (targetId) navigate(`/candidate/interviews/${interviewId}/question/${targetId}`)
        }}
      />

      {submitError && <ErrorBanner message={submitError} />}

      {isViewingCurrent ? (
        <>
          <QuestionCard
            questionText={interview.current_question_text ?? ""}
            category={questionMeta?.category}
            target={questionMeta?.target}
            isFollowUp={Boolean(isFollowUp)}
          />
          <AnswerForm
            onSubmit={handleSubmitAnswer}
            isSubmitting={isSubmitting}
            questionKey={`${interview.current_question_id ?? ""}-${interview.turn_index}`}
          />
        </>
      ) : (
        previousTurn && (
          <>
            <PreviousAnswerCard question={previousTurn.question} answer={previousTurn.answer} />
            <div className="flex justify-end">
              <Button
                variant="secondary"
                onClick={() =>
                  navigate(`/candidate/interviews/${interviewId}/question/${interview.current_question_id}`)
                }
              >
                Return to Current Question
              </Button>
            </div>
          </>
        )
      )}

      {viewingIndex > 0 && (
        <div className="flex justify-start">
          <Button
            variant="ghost"
            onClick={() => {
              const previousId = interview.asked_question_ids[viewingIndex - 1]
              if (previousId) navigate(`/candidate/interviews/${interviewId}/question/${previousId}`)
            }}
          >
            ← Previous
          </Button>
        </div>
      )}
    </div>
  )
}
