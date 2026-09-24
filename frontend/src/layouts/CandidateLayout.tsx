import type { ReactNode } from "react"
import { CandidateHeader } from "../components/layout/CandidateHeader"
import { NightAtmosphere } from "../components/ui/NightAtmosphere"

/**
 * The candidate's shell, before and after the interview itself.
 *
 * Holds no measure of its own: the pre-interview page is a two-column composition that needs
 * the full width, and the interview and completion screens bring their own full-bleed room.
 *
 * Runs in the room's own environment. A candidate who reads this page and then presses Begin
 * should not cross a light page on the way into an interview that is obsidian - the surface,
 * the atmosphere and the interviewer are already the ones they are about to sit with.
 */
export function CandidateLayout({ children }: { children: ReactNode }) {
  return (
    <div className="night-room relative flex min-h-screen flex-col">
      <NightAtmosphere />
      <CandidateHeader />
      <main className="relative flex-1">{children}</main>
    </div>
  )
}
