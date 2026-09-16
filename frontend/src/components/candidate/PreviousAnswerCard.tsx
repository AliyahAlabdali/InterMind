import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"

interface PreviousAnswerCardProps {
  question: string
  answer: string
}

export function PreviousAnswerCard({ question, answer }: PreviousAnswerCardProps) {
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <Badge tone="neutral" className="w-fit">
          Previously answered
        </Badge>
        <p className="text-lg font-medium leading-relaxed text-ink">{question}</p>
      </Card>
      <div>
        <p className="mb-2 text-sm font-medium text-ink-soft">Your answer</p>
        <div className="rounded-[10px] border border-border bg-ivory-100 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-ink-soft">
          {answer}
        </div>
      </div>
      <p className="text-xs text-ink-muted">
        This answer is locked. Later questions may have adapted based on it, so editing it here
        isn't supported.
      </p>
    </div>
  )
}
