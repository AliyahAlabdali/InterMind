import { useCallback, useEffect } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getInterview } from "../../api/interviews"
import { useAsyncData } from "../../hooks/useAsyncData"
import { useCandidateToken } from "../../hooks/useCandidateToken"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { CompletionScreen } from "../../components/interview/CompletionScreen"

export function CandidateCompletePage() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()
  const token = useCandidateToken(interviewId)

  const interviewFetcher = useCallback(
    () => getInterview(interviewId!, token ?? ""),
    [interviewId, token],
  )
  const interview = useAsyncData(interviewFetcher, [interviewId, token])

  useEffect(() => {
    if (interview.data && interview.data.status !== "completed") {
      navigate(`/candidate/interviews/${interviewId}`, { replace: true })
    }
  }, [interview.data, interviewId, navigate])

  if (interview.isLoading || (interview.data && interview.data.status !== "completed")) {
    return <Spinner label="Loading…" />
  }
  if (interview.error) return <ErrorBanner message={interview.error} onRetry={interview.refetch} />

  return (
    <div className="pt-10">
      <CompletionScreen />
    </div>
  )
}
