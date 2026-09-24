/** Past this many requirements a tick becomes a hairline too thin to read. */
const MAX_TICKS = 16

interface CoverageRailProps {
  /** Requirements the interview has finished with. */
  assessed: number
  /** Requirements in this role's plan, in total. */
  total: number
  /** Whether one of them is the subject of the question on screen right now. */
  active?: boolean
  /** Shown after the rail. Omit where the row already says it. */
  label?: string
  className?: string
}

/**
 * How far an interview has got, in the product's one progress language.
 *
 * The workspace used to draw this four different ways - a percentage hairline on the dashboard,
 * an n-of-m hairline on candidate rows, ticks on the coverage map, ticks in the interview room -
 * for a single concept. This is the interview room's representation, brought out to every page
 * that talks about coverage: one tick per requirement, so the number you see is the thing being
 * counted rather than a percentage standing in for it.
 *
 * Takes no tone. The accent, the hairline and the text all resolve from the surface it is
 * rendered on, so the same markup draws indigo-on-white in the light world and pale-sky-on-
 * obsidian inside `.night-room`.
 *
 * Never a percentage of a score. Until an interview completes there is no score, and a bar that
 * looked like one would be inventing data.
 */
export function CoverageRail({
  assessed,
  total,
  active = false,
  label,
  className = "",
}: CoverageRailProps) {
  if (total <= 0) return null

  const ratio = Math.min(Math.max(assessed / total, 0), 1)
  const readout = label ?? `${assessed} of ${total} areas`

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <span
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={assessed}
        aria-label={`${assessed} of ${total} areas explored`}
        className="flex h-[5px] min-w-0 flex-1 items-stretch gap-[2px]"
      >
        {total <= MAX_TICKS ? (
          Array.from({ length: total }, (_, i) => (
            <span
              key={i}
              className={`min-w-[3px] flex-1 rounded-full ${
                i < assessed
                  ? "bg-accent"
                  : active && i === assessed
                    ? "bg-fg"
                    : "bg-fg/15"
              }`}
            />
          ))
        ) : (
          <span className="relative flex-1 overflow-hidden rounded-full bg-fg/15">
            <span
              className="absolute inset-y-0 left-0 rounded-full bg-accent"
              style={{ width: `${Math.max(ratio * 100, 2)}%` }}
            />
          </span>
        )}
      </span>

      <span className="type-data shrink-0 text-fg-muted">{readout}</span>
    </div>
  )
}
