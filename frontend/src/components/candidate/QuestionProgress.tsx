interface QuestionProgressProps {
  /** 0-indexed position, among asked questions, of the question currently being viewed. */
  viewingIndex: number
  /** How many questions have been asked so far (the active one included). */
  askedCount: number
  total: number
  /** Jump to a previously-asked step. Steps not yet reached are never selectable. */
  onSelect?: (index: number) => void
}

export function QuestionProgress({ viewingIndex, askedCount, total, onSelect }: QuestionProgressProps) {
  if (total <= 0) return null

  const activeIndex = Math.max(askedCount - 1, 0)

  return (
    <div>
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-ink-muted">
        {String(Math.min(viewingIndex + 1, total)).padStart(2, "0")} / {String(total).padStart(2, "0")}
      </p>
      <div className="flex flex-wrap gap-2" role="list" aria-label="Interview progress">
        {Array.from({ length: total }, (_, index) => {
          const isCompleted = index < activeIndex
          const isActive = index === activeIndex
          const isViewing = index === viewingIndex

          const isReachable = index <= activeIndex

          let dotClasses = "border-border-strong text-ink-muted"
          if (isCompleted) dotClasses = "border-periwinkle bg-periwinkle text-white"
          else if (isActive) dotClasses = "border-periwinkle text-periwinkle"

          const label = `Question ${index + 1}${isCompleted ? ", completed" : isActive ? ", current" : ", not yet reached"}`

          return (
            <button
              key={index}
              type="button"
              role="listitem"
              disabled={!isReachable || !onSelect}
              onClick={() => onSelect?.(index)}
              aria-current={isViewing ? "step" : undefined}
              aria-label={label}
              className={`flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors disabled:cursor-default ${dotClasses} ${
                isViewing ? "ring-2 ring-lavender ring-offset-2 ring-offset-ivory" : ""
              } ${isReachable && onSelect ? "cursor-pointer hover:border-periwinkle" : ""}`}
            >
              {isCompleted ? "✓" : String(index + 1).padStart(2, "0")}
            </button>
          )
        })}
      </div>
    </div>
  )
}
