import type { QuestionEvaluationSummary } from "../../types"
import { Card } from "../ui/Card"
import { QuestionEvaluationCard } from "./QuestionEvaluationCard"

export function QuestionEvaluationList({ items }: { items: QuestionEvaluationSummary[] }) {
  if (items.length === 0) return null

  return (
    <Card>
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        Question-by-Question Evidence
      </h3>
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <QuestionEvaluationCard key={item.question_id} item={item} />
        ))}
      </div>
    </Card>
  )
}
