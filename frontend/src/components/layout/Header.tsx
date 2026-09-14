import { Link } from "react-router-dom"

export function Header() {
  return (
    <header className="border-b border-ivory-200 bg-ivory-50/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <Link to="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky to-lilac text-sm font-semibold text-ink">
            IM
          </span>
          <span className="text-lg font-semibold tracking-tight text-ink">InterMind</span>
        </Link>
        <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          AI-Powered Interviewing
        </span>
      </div>
    </header>
  )
}
