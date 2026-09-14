interface SpinnerProps {
  label?: string
}

export function Spinner({ label = "Loading…" }: SpinnerProps) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-ink-muted">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-ink-muted border-t-lilac-dark" />
      <span className="text-sm">{label}</span>
    </div>
  )
}
