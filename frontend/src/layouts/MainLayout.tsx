import type { ReactNode } from "react"
import { Header } from "../components/layout/Header"

export function MainLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-ivory">
      <Header />
      <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>
    </div>
  )
}
