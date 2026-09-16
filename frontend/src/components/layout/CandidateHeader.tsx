import { Logo } from "../../brand/Logo"

export function CandidateHeader() {
  return (
    <header className="px-5 py-6 sm:px-8">
      <div className="mx-auto max-w-2xl">
        <Logo size={26} />
      </div>
    </header>
  )
}
