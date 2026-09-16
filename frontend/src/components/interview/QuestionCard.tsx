import type { QuestionCategory } from "../../types"
import { Card } from "../ui/Card"

interface QuestionCardProps {
  questionText: string
  category?: QuestionCategory
  target?: string
  isFollowUp: boolean
}

export function QuestionCard({ questionText, target, isFollowUp }: QuestionCardProps) {
  return (
    <Card className="flex flex-col gap-3 animate-enter" key={questionText}>
      {isFollowUp ? (
        <p className="text-sm font-medium text-periwinkle">Let's explore that further.</p>
      ) : (
        target && (
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{target}</p>
        )
      )}
      <p className="text-xl font-medium leading-relaxed text-ink">{questionText}</p>
    </Card>
  )
}
