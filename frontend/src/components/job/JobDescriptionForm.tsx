import { useState } from "react"
import type { FormEvent } from "react"
import { Button } from "../ui/Button"

interface JobDescriptionFormProps {
  onSubmit: (description: string) => void
  isSubmitting: boolean
}

export function JobDescriptionForm({ onSubmit, isSubmitting }: JobDescriptionFormProps) {
  const [description, setDescription] = useState("")

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = description.trim()
    if (!trimmed) return
    onSubmit(trimmed)
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <label htmlFor="job-description" className="text-sm font-medium text-ink-soft">
        Job description
      </label>
      <textarea
        id="job-description"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="Paste the full job description here — role, responsibilities, required skills…"
        rows={12}
        disabled={isSubmitting}
        className="w-full resize-y rounded-xl border border-ivory-200 bg-white px-4 py-3 text-sm text-ink shadow-soft outline-none transition-colors placeholder:text-ink-muted focus:border-lilac-dark disabled:bg-ivory-100"
      />
      <div className="flex justify-end">
        <Button type="submit" isLoading={isSubmitting} disabled={!description.trim()}>
          Create Job
        </Button>
      </div>
    </form>
  )
}
