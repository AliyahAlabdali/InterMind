import { useNavigate } from "react-router-dom"
import { Card } from "../ui/Card"
import { Button } from "../ui/Button"

export function CompletionScreen({ interviewId }: { interviewId: string }) {
  const navigate = useNavigate()

  return (
    <Card className="flex flex-col items-center gap-4 py-12 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-sky to-lilac text-2xl">
        ✓
      </span>
      <div>
        <h2 className="text-xl font-semibold text-ink">Interview complete</h2>
        <p className="mt-2 max-w-md text-sm text-ink-soft">
          Thank you for completing the interview. Your responses have been recorded and will
          be reviewed by the hiring team.
        </p>
      </div>
      <Button onClick={() => navigate(`/interviews/${interviewId}/report`)}>View Report</Button>
    </Card>
  )
}
