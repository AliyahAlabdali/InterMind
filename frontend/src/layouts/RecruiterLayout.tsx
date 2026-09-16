import type { ReactNode } from "react"
import { RecruiterSidebar } from "../components/layout/RecruiterSidebar"
import { RecruiterHeader } from "../components/layout/RecruiterHeader"

export function RecruiterLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-ivory">
      <RecruiterSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <RecruiterHeader />
        <main className="mx-auto w-full max-w-4xl flex-1 px-5 py-8 sm:px-8 sm:py-10">
          {children}
        </main>
      </div>
    </div>
  )
}
