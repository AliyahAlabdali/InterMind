import type { ReactNode } from "react"

interface MarqueeProps {
  items: string[]
  /** Seconds for one full pass. Longer reads as drift; shorter reads as a ticker. */
  duration?: number
  /** Separator between items. The flow marquee uses an arrow, the vocabulary one a mark. */
  separator?: ReactNode
  className?: string
  itemClassName?: string
}

/**
 * A continuous horizontal run of the product's own vocabulary.
 *
 * Two identical copies of the content sit in one track, and the track translates by exactly
 * -50%, so the loop has no seam and no reset. The content is the interview's actual sequence
 * and the actual terms the report uses, which is the difference between this and a logo
 * carousel: it is the product saying what it does, moving.
 *
 * Under reduced motion the track stops. The first copy is still fully readable, so the words
 * are never lost, only the travel.
 */
export function Marquee({
  items,
  duration = 42,
  separator,
  className = "",
  itemClassName = "",
}: MarqueeProps) {
  const run = (
    <div className="flex shrink-0 items-center">
      {items.map((item) => (
        <span key={item} className="flex shrink-0 items-center">
          <span className={itemClassName}>{item}</span>
          <span aria-hidden="true" className="mx-6 shrink-0 opacity-45 sm:mx-10">
            {separator ?? "/"}
          </span>
        </span>
      ))}
    </div>
  )

  return (
    <div className={`marquee-mask overflow-hidden ${className}`}>
      {/* The duplicate run is presentational; a screen reader should hear the sequence once. */}
      <div className="marquee-track" style={{ ["--marquee-duration" as string]: `${duration}s` }}>
        {run}
        <div aria-hidden="true" className="flex shrink-0 items-center">
          {items.map((item) => (
            <span key={item} className="flex shrink-0 items-center">
              <span className={itemClassName}>{item}</span>
              <span className="mx-6 shrink-0 opacity-45 sm:mx-10">{separator ?? "/"}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
