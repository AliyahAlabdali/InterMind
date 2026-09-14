interface ProgressBarProps {
  current: number
  total: number
}

export function ProgressBar({ current, total }: ProgressBarProps) {
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-ink-muted">
        <span>
          Question {Math.min(current + 1, total)} of {total}
        </span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-ivory-200">
        <div
          className="h-full rounded-full bg-gradient-to-r from-sky-dark via-lilac-dark to-blush-dark transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
