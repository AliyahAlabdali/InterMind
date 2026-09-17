interface QuestionProgressProps {
  /** 0-indexed position, among asked questions, of the question currently being viewed. */
  viewingIndex: number
  /** How many questions have been asked so far (the active one included). */
  askedCount: number
  /** Jump to a previously-asked step. */
  onSelect?: (index: number) => void
}

// The interview is adaptive - it decides how many questions to ask as it goes, so there is no
// fixed total to show a "N of M" count against or to pre-render not-yet-reached steps for (see
// the backend's app.agents.interview_graph). This only ever shows steps that have actually
// happened - every dot rendered is reachable.
export function QuestionProgress({ viewingIndex, askedCount, onSelect }: QuestionProgressProps) {
  if (askedCount <= 0) return null

  const activeIndex = Math.max(askedCount - 1, 0)

  return (
    <div>
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-ink-muted">
        Question {String(viewingIndex + 1).padStart(2, "0")}
      </p>
      <div className="flex flex-wrap gap-2" role="list" aria-label="Interview progress">
        {Array.from({ length: askedCount }, (_, index) => {
          const isCompleted = index < activeIndex
          const isActive = index === activeIndex
          const isViewing = index === viewingIndex

          let dotClasses = "border-border-strong text-ink-muted"
          if (isCompleted) dotClasses = "border-periwinkle bg-periwinkle text-white"
          else if (isActive) dotClasses = "border-periwinkle text-periwinkle"

          const label = `Question ${index + 1}${isCompleted ? ", completed" : isActive ? ", current" : ""}`

          return (
            <button
              key={index}
              type="button"
              role="listitem"
              disabled={!onSelect}
              onClick={() => onSelect?.(index)}
              aria-current={isViewing ? "step" : undefined}
              aria-label={label}
              className={`flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors disabled:cursor-default ${dotClasses} ${
                isViewing ? "ring-2 ring-lavender ring-offset-2 ring-offset-ivory" : ""
              } ${onSelect ? "cursor-pointer hover:border-periwinkle" : ""}`}
            >
              {isCompleted ? "✓" : String(index + 1).padStart(2, "0")}
            </button>
          )
        })}
      </div>
    </div>
  )
}
