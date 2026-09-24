import type { ReactNode } from "react"

interface EmptyStateProps {
  title: string
  body: ReactNode
  action?: ReactNode
  /** Two or three short lines telling the user what will appear here and why. */
  hints?: string[]
}

/**
 * An empty page that explains itself.
 *
 * Left-aligned inside a hairline frame rather than centred in the middle of the viewport: a
 * centred block of large type in the middle of an empty page reads as an error screen, and it
 * also means the page's own composition disappears the moment there is no data. This keeps the
 * page's structure and fills the space where the content will be.
 */
export function EmptyState({ title, body, action, hints }: EmptyStateProps) {
  return (
    <div className="rounded-[20px] border border-dashed border-hair-strong px-6 py-10 sm:px-10 sm:py-12">
      <div className="max-w-xl">
        <h2 className="type-group text-fg">{title}</h2>
        <p className="type-copy mt-3 text-fg-soft">{body}</p>

        {hints && hints.length > 0 && (
          <ol className="mt-7 flex flex-col gap-3">
            {hints.map((hint, index) => (
              <li key={hint} className="flex items-baseline gap-3 text-sm text-fg-soft">
                <span
                  aria-hidden="true"
                  className="type-data inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-hair-strong text-[0.6875rem] text-fg-muted"
                >
                  {index + 1}
                </span>
                {hint}
              </li>
            ))}
          </ol>
        )}

        {action && <div className="mt-8">{action}</div>}
      </div>
    </div>
  )
}
