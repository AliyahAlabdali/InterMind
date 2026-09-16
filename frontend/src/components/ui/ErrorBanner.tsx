interface ErrorBannerProps {
  message: string
  onRetry?: () => void
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-[10px] border border-danger/30 bg-danger/5 px-4 py-3 text-sm text-danger">
      <p>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 font-medium underline underline-offset-2 hover:text-ink"
        >
          Try again
        </button>
      )}
    </div>
  )
}
