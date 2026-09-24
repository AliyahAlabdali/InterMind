import { AlertCircle } from "lucide-react"

interface ErrorBannerProps {
  message: string
  onRetry?: () => void
}

/**
 * Something went wrong, in one line, with the way out next to it. Framed rather than tinted
 * red across its whole width: an operational hiccup on a list page is not an emergency, and a
 * full red field trains people to ignore the next one.
 */
export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-[14px] border border-bad/30 bg-bad/[0.06] px-5 py-4"
    >
      <p className="flex items-start gap-2.5 text-sm text-fg">
        <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-bad" />
        {message}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-[36px] items-center rounded-full border border-bad/30 px-3.5 text-sm font-medium text-bad transition-colors hover:bg-bad/10"
        >
          Try again
        </button>
      )}
    </div>
  )
}
