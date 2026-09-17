import { NavLink } from "react-router-dom"
import { Logo } from "../../brand/Logo"

// See RecruiterSidebar for why this is a single "Interviews" item, not "Dashboard" plus a
// second, redundant destination.
const NAV_ITEMS = [{ to: "/recruiter/dashboard", label: "Interviews" }]

export function RecruiterHeader() {
  return (
    <header className="flex items-center justify-between border-b border-border bg-white px-5 py-4 md:hidden">
      <a href="/recruiter/dashboard" aria-label="InterMind home">
        <Logo size={26} />
      </a>
      <nav aria-label="Recruiter navigation" className="flex items-center gap-4">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `text-sm font-medium ${isActive ? "text-ink" : "text-ink-soft"}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}
