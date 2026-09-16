import type { ReactNode } from "react"
import { CandidateHeader } from "../components/layout/CandidateHeader"

export function CandidateLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-ivory">
      <CandidateHeader />
      <main className="mx-auto max-w-2xl px-5 pb-16 sm:px-8">{children}</main>
    </div>
  )
}
