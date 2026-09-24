import { useEffect } from "react"
import type { ReactNode } from "react"
import { useLocation } from "react-router-dom"
import { WorkspaceNav } from "./WorkspaceNav"
import { NightAtmosphere } from "../components/ui/NightAtmosphere"

/**
 * The recruiter shell.
 *
 * Holds no measure of its own. Pages compose themselves from full-width bands and each one uses
 * `.shell` to line its content up with every other page.
 *
 * The shell carries the world. `.night-room` redefines the shared surface tokens - `fg`,
 * `fg-soft`, `hair`, `canvas`, `accent` - so the navigation, the buttons and every shared
 * component render in the interview room's palette without a single conditional in their
 * markup. The light values those tokens carry by default are kept as the fallback for anything
 * rendered outside a room, but no route uses them: the whole product is one continuous surface,
 * and moving from the list of roles into a role, a report or an interview never crosses a seam.
 *
 * The navigation sits outside the page transition on purpose: it persists across every
 * workspace route, which is what lets its active marker slide between links rather than
 * re-render.
 */
export function WorkspaceLayout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()

  // Arriving part-way down a new page is disorienting, and alongside a fade it reads as a
  // rendering fault rather than as retained scroll.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="night-room relative flex min-h-screen flex-col">
      <NightAtmosphere />
      <WorkspaceNav onDark />
      <main id="main" className="relative flex-1">
        <div key={pathname} className="animate-fade">
          {children}
        </div>
      </main>
    </div>
  )
}
