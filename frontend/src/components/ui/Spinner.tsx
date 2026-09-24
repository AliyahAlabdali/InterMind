interface SpinnerProps {
  label?: string
  /** Fills the space the content will occupy, so loading doesn't collapse the layout. */
  block?: boolean
}

/**
 * Loading, stated plainly. The label is the point: a bare spinner says "something is
 * happening", a labelled one says what, which is the difference between a wait and a fault.
 */
export function Spinner({ label = "Loading…", block = false }: SpinnerProps) {
  return (
    <div
      role="status"
      className={`flex items-center gap-3 text-fg-muted ${block ? "min-h-[12rem] py-10" : "py-6"}`}
    >
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-hair-strong border-t-space"
      />
      <span className="text-sm">{label}</span>
    </div>
  )
}

/** A shaped placeholder for content whose layout is known before its data is. */
export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-hidden="true" className="flex flex-col divide-y divide-hair">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-6 py-6">
          <span className="h-4 flex-1 animate-shimmer rounded-full" style={{ maxWidth: "18rem" }} />
          <span className="hidden h-3 w-24 animate-shimmer rounded-full sm:block" />
          <span className="h-3 w-16 animate-shimmer rounded-full" />
        </div>
      ))}
    </div>
  )
}
