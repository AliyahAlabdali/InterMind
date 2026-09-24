export type PresenceState = "idle" | "live" | "working"

interface PresenceMarkProps {
  state: PresenceState
  /** Pixel size of the glyph. 14-18 in rows, 22-28 as a section marker. */
  size?: number
  className?: string
}

/**
 * The system, present but not speaking.
 *
 * This is the interviewer's geometry - arcs carried around a nucleus - reduced to a glyph, so
 * that the thing you glance at on a list page and the instrument you meet in the interview room
 * are recognisably the same object. It replaces the single pulsing dot the workspace used to
 * signal a running interview with, which said "something is loading" rather than "an interview
 * is happening".
 *
 * Deliberately SVG and CSS. The instrument's WebGL context belongs to the interview and must
 * never be created a second time just to decorate a row.
 *
 * Three states, and each one only ever appears when it is true:
 *   idle     the system is available and nothing is running
 *   live     an interview is in progress right now
 *   working  a request the user is waiting on is in flight
 */
export function PresenceMark({ state, size = 16, className = "" }: PresenceMarkProps) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      className={`presence-${state} shrink-0 ${className}`}
    >
      {/* Two crossing arcs rather than concentric circles: the instrument's axes never sit
          coaxially, and that asymmetry is most of what makes it read as an instrument. */}
      <ellipse
        className="presence-ring presence-ring-outer"
        cx="12"
        cy="12"
        rx="9.2"
        ry="5.4"
        stroke="currentColor"
        strokeWidth="1.1"
        opacity={state === "idle" ? 0.4 : 0.55}
        transform="rotate(-24 12 12)"
      />
      <ellipse
        className="presence-ring"
        cx="12"
        cy="12"
        rx="5.6"
        ry="9"
        stroke="currentColor"
        strokeWidth="1.1"
        opacity={state === "idle" ? 0.45 : 0.7}
        transform="rotate(16 12 12)"
      />
      <circle cx="12" cy="12" r={state === "idle" ? 1.7 : 2.1} fill="currentColor" />
    </svg>
  )
}
