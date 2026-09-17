import { NavLink } from "react-router-dom"
import { Logo } from "../../brand/Logo"

// A single, unambiguous "New Interview" action lives in the dashboard page body (see
// DashboardPage) - keeping it out of the nav too avoids two competing primary CTAs for the
// same action.
//
// Only one destination exists today (the interview list, at /recruiter/dashboard) - "Job
// Analysis" is reachable only from within a specific interview (see InterviewCandidatesPage)
// and deliberately stays contextual rather than becoming a second top-level item, and there is
// no settings page to link to yet. Labelled "Interviews" (matching the page's own heading)
// rather than the more generic "Dashboard", since that's what it actually shows - a fake
// second nav item pointing at the same page would not be a real IA improvement.
const NAV_ITEMS = [{ to: "/recruiter/dashboard", label: "Interviews" }]

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
