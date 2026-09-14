import { useState } from "react"
import type { FormEvent } from "react"
import { Button } from "../ui/Button"

interface AnswerFormProps {
  onSubmit: (answer: string) => void
  isSubmitting: boolean
  questionKey: string
}

export function AnswerForm({ onSubmit, isSubmitting, questionKey }: AnswerFormProps) {
  const [answer, setAnswer] = useState("")

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = answer.trim()
    if (!trimmed || isSubmitting) return
    onSubmit(trimmed)
    setAnswer("")
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3" key={questionKey}>
      <label htmlFor="answer" className="text-sm font-medium text-ink-soft">
        Your answer
      </label>
      <textarea
        id="answer"
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
        placeholder="Share your answer in as much detail as you can…"
        rows={8}
        disabled={isSubmitting}
        className="w-full resize-y rounded-xl border border-ivory-200 bg-white px-4 py-3 text-sm text-ink shadow-soft outline-none transition-colors placeholder:text-ink-muted focus:border-lilac-dark disabled:bg-ivory-100"
      />
      <div className="flex justify-end">
        <Button type="submit" isLoading={isSubmitting} disabled={!answer.trim()}>
          Submit Answer
        </Button>
      </div>
    </form>
  )
}
