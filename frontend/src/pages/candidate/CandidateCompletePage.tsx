import { useCallback, useEffect } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getInterview } from "../../api/interviews"
import { useAsyncData } from "../../hooks/useAsyncData"
import { useCandidateToken } from "../../hooks/useCandidateToken"
import { CompletionScreen } from "../../components/interview/CompletionScreen"
import { Stage, StageMessage } from "../../components/interview/StageShell"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

export function CandidateCompletePage() {
  useDocumentTitle("Interview complete")
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

  // Both of these stay in the interview's room: this screen is reached the instant the last
  // answer is sent, and a white loading page in between would read as the session dropping.
  if (interview.isLoading || (interview.data && interview.data.status !== "completed")) {
    return (
      <Stage>
        <StageMessage title="One moment" body="Closing your interview." />
      </Stage>
    )
  }

  if (interview.error) {
    return (
      <Stage>
        <StageMessage
          title="We couldn't load this interview"
          body="The link may have expired, or InterMind may be unreachable right now."
          onRetry={interview.refetch}
        />
      </Stage>
    )
  }

  return <CompletionScreen />
}
