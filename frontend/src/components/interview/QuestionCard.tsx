import type { QuestionCategory } from "../../types"
import { formatCategory } from "../../lib/format"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"

const CATEGORY_TONE = {
  competency: "blush",
  technology: "sky",
  task: "lilac",
} as const

interface QuestionCardProps {
  questionText: string
  category?: QuestionCategory
  target?: string
  isFollowUp: boolean
}

export function QuestionCard({ questionText, category, target, isFollowUp }: QuestionCardProps) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {isFollowUp && <Badge tone="warning">Follow-up question</Badge>}
        {category && <Badge tone={CATEGORY_TONE[category]}>{formatCategory(category)}</Badge>}
        {target && <span className="text-xs text-ink-muted">Focus: {target}</span>}
      </div>
      <p className="text-lg font-medium leading-relaxed text-ink">{questionText}</p>
    </Card>
  )
}
