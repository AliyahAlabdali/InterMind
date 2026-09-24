import type { EvidenceKind } from "../../lib/evidence"

/**
 * An evidence state, drawn as a shape.
 *
 * The glyph carries the meaning and colour only reinforces it: filled for demonstrated,
 * half-filled for partial, ringed for a claim, a rule through it for an explicit lack, a cross
 * for a contradiction, and a dashed outline for "nothing was established". In a red/amber/green
 * scheme an unassessed requirement always ends up looking like a failed one, which is the exact
 * misreading this report must not produce.
 */
const TONE: Record<EvidenceKind, string> = {
  demonstrated: "text-ok",
  partial: "text-accent",
  claimed: "text-warn",
  lack: "text-fg-muted",
  contradictory: "text-bad",
  none: "text-fg-muted",
}

export function EvidenceMark({ kind, className = "" }: { kind: EvidenceKind; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 14 14"
      className={`h-3.5 w-3.5 shrink-0 ${TONE[kind]} ${className}`}
      fill="none"
    >
      {kind === "demonstrated" && <rect x="2" y="2" width="10" height="10" rx="2" fill="currentColor" />}

      {kind === "partial" && (
        <>
          <rect x="2.6" y="2.6" width="8.8" height="8.8" rx="1.8" stroke="currentColor" strokeWidth="1.2" />
          <path d="M7 3.4v7.2H4.4a1 1 0 0 1-1-1V4.4a1 1 0 0 1 1-1H7Z" fill="currentColor" />
        </>
      )}

      {kind === "claimed" && (
        <>
          <rect x="2.6" y="2.6" width="8.8" height="8.8" rx="1.8" stroke="currentColor" strokeWidth="1.2" />
          <circle cx="7" cy="7" r="1.6" fill="currentColor" />
        </>
      )}

      {kind === "lack" && (
        <>
          <rect x="2.6" y="2.6" width="8.8" height="8.8" rx="1.8" stroke="currentColor" strokeWidth="1.2" />
          <path d="M4.8 7h4.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </>
      )}

      {kind === "contradictory" && (
        <>
          <rect x="2.6" y="2.6" width="8.8" height="8.8" rx="1.8" stroke="currentColor" strokeWidth="1.2" />
          <path d="M5 5l4 4M9 5l-4 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </>
      )}

      {kind === "none" && (
        <rect
          x="2.6"
          y="2.6"
          width="8.8"
          height="8.8"
          rx="1.8"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeDasharray="2.4 2"
        />
      )}
    </svg>
  )
}
