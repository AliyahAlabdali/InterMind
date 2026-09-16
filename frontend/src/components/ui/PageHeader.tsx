import type { ReactNode } from "react"

interface PageHeaderProps {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            {eyebrow}
          </p>
        )}
        <h1
          className="mt-1 text-2xl font-semibold tracking-tight text-ink"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {title}
        </h1>
        {description && (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-soft">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
    </div>
  )
}
