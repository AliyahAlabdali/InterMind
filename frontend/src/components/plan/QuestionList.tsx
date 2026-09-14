import type { InterviewQuestion } from "../../types"
import { formatCategory } from "../../lib/format"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"

const CATEGORY_TONE = {
  competency: "blush",
  technology: "sky",
  task: "lilac",
} as const

export function QuestionList({ questions }: { questions: InterviewQuestion[] }) {
  if (questions.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Generated Questions ({questions.length})
      </h3>
      <ol className="flex flex-col gap-4">
        {questions.map((question, index) => (
          <li key={question.id} className="border-b border-ivory-200 pb-4 last:border-0 last:pb-0">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-ink-muted">Q{index + 1}</span>
              <Badge tone={CATEGORY_TONE[question.category]}>
                {formatCategory(question.category)}
              </Badge>
              <span className="text-xs text-ink-muted">Target: {question.target}</span>
            </div>
            <p className="text-sm font-medium text-ink">{question.text}</p>
            <p className="mt-1 text-xs italic text-ink-muted">{question.grounding}</p>
          </li>
        ))}
      </ol>
    </Card>
  )
}
