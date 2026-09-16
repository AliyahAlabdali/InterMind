import { NavLink } from "react-router-dom"
import { Logo } from "../../brand/Logo"

const NAV_ITEMS = [
  { to: "/recruiter/dashboard", label: "Dashboard" },
  { to: "/recruiter/interviews/new", label: "New Interview" },
]

function linkClasses(isActive: boolean): string {
  const base = "rounded-[10px] px-3 py-2 text-sm font-medium transition-colors"
  if (isActive) return `${base} bg-ivory-100 text-ink`
  return `${base} text-ink-soft hover:bg-ivory-100 hover:text-ink`
}

export function RecruiterSidebar() {
  return (
    <aside className="hidden w-60 shrink-0 flex-col gap-8 border-r border-border bg-white px-5 py-6 md:flex">
      <a href="/recruiter/dashboard" aria-label="InterMind home">
        <Logo size={30} />
      </a>
      <nav aria-label="Recruiter navigation" className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => linkClasses(isActive)}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto text-xs text-ink-muted">
        <p className="font-medium text-ink-soft">Recruiter workspace</p>
        <p className="mt-1">Adaptive, evidence-based technical interviews.</p>
      </div>
    </aside>
  )
}
