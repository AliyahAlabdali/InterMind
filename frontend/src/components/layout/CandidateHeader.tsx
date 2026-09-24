import { Logo } from "../../brand/Logo"

/**
 * Identity only. A candidate has nowhere else to go from here, so the header carries no
 * navigation - just enough to say whose interview this is.
 */
export function CandidateHeader() {
  return (
    <header className="border-b border-hair">
      <div className="shell flex min-h-[60px] items-center">
        <Logo size={24} animated tone="onDark" />
      </div>
    </header>
  )
}
