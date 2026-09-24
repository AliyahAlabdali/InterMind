import { useId } from "react"
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion"

type LogoVariant = "inline" | "mark" | "stacked"
/** Which surface the lockup sits on. Inverts the figure so the mark holds on dark panels. */
type LogoTone = "onLight" | "onDark"

interface LogoProps {
  /** Height of the mark in pixels. The wordmark scales from it. */
  size?: number
  /** Kept for callers that predate `variant`. `false` renders the mark alone. */
  withWordmark?: boolean
  variant?: LogoVariant
  className?: string
  /** Animate the bubble dots. Off by default; always off under reduced motion. */
  animated?: boolean
  tone?: LogoTone
}

/**
 * The InterMind identity.
 *
 * ## Provenance
 *
 * The symbol is a vector trace of the supplied logo artwork, not a redrawing of it. The raster
 * was segmented into its layers by colour, each layer's contours were followed at 2x
 * supersample, simplified with Douglas-Peucker at ~0.5px tolerance and emitted as smooth
 * quadratics. Every coordinate below is measured from that file: the profile, the speech bubble,
 * the ribbon, the three dots and the gradient stops. Nothing here was drawn by eye.
 *
 * ## The three technical adaptations
 *
 * 1. Transparent background. The artwork sits on cream; that field is dropped, so the mark
 *    composites onto whatever is behind it.
 * 2. Light and dark surfaces. The head is a single fill, flipped by `tone`. The speech bubble
 *    is a concavity in that fill rather than a shape of its own, so it takes the colour of the
 *    surface behind and inverts for free. The ribbon gradient and the dots are unchanged, since
 *    both read on either surface.
 * 3. Scale. A 64-unit viewBox with no rasterisation, so navbar, favicon and presentation
 *    lockups are the same geometry.
 *
 * No aesthetic decisions were taken: proportions, silhouette, layering and colour all come from
 * the source file.
 */

/** Traced contours of the dark mass: head in profile, crown ring, and the bubble knocked out. */
const HEAD =
  "M30.26 6.56Q32.08 6.26 34.33 6.31Q36.57 6.35 38.43 6.73Q40.30 7.11 42.29 7.92Q44.28 8.72 45.80 9.74Q47.32 10.75 45.08 10.58Q42.84 10.41 41.31 10.46Q39.79 10.50 38.14 10.71Q36.49 10.92 34.62 11.39Q32.76 11.85 31.32 12.40Q29.88 12.95 28.28 13.84Q26.67 14.73 25.78 15.41Q24.89 16.08 23.83 17.19Q22.77 18.29 21.93 19.72Q21.08 21.16 20.66 22.81Q20.23 24.47 20.32 26.16Q20.40 27.85 21.08 29.50Q21.76 31.15 23.11 32.72Q24.47 34.29 25.95 35.22Q27.43 36.15 29.16 36.70Q30.90 37.25 32.72 37.38Q34.54 37.50 31.87 38.31Q29.21 39.11 26.75 39.53Q24.30 39.96 22.81 39.45Q21.33 38.94 20.23 38.31Q19.13 37.67 17.86 36.53Q16.59 35.39 15.83 34.33Q15.07 33.27 14.39 31.75Q13.71 30.22 13.38 28.87Q13.04 27.51 12.99 25.78Q12.95 24.04 13.16 22.69Q13.38 21.33 13.97 19.60Q14.56 17.86 15.24 16.63Q15.92 15.41 16.76 14.31Q17.61 13.21 18.71 12.15Q19.81 11.09 21.16 10.16Q22.52 9.23 24.00 8.51Q25.48 7.79 26.96 7.32Q28.44 6.86 30.26 6.56Z M52.02 18.29Q51.81 17.10 52.44 18.03Q53.08 18.96 53.59 20.44Q54.10 21.93 54.14 23.20Q54.18 24.47 53.97 25.19Q53.76 25.90 53.12 27.01Q52.49 28.11 51.30 29.46Q50.12 30.81 48.47 32.25Q46.81 33.69 45.25 34.71Q43.68 35.72 43.85 35.77Q44.02 35.81 46.35 34.79Q48.68 33.78 51.43 32.21Q54.18 30.65 54.48 31.70Q54.77 32.76 55.96 35.05Q57.14 37.33 57.14 37.88Q57.14 38.43 56.89 38.73Q56.63 39.03 55.58 39.24Q54.52 39.45 54.22 39.75Q53.93 40.04 54.10 41.19Q54.26 42.33 53.67 42.84Q53.08 43.34 53.33 43.64Q53.59 43.94 53.59 44.19Q53.59 44.44 52.99 45.12Q52.40 45.80 52.40 47.32Q52.40 48.85 51.94 49.57Q51.47 50.29 50.54 50.58Q49.61 50.88 46.22 50.62Q42.84 50.37 41.31 50.58Q39.79 50.79 38.94 51.30Q38.10 51.81 37.59 52.40Q37.08 52.99 36.61 53.88Q36.15 54.77 35.94 56.13Q35.72 57.48 35.56 57.44Q35.39 57.40 33.82 56.55Q32.25 55.70 30.77 54.56Q29.29 53.42 27.77 51.81Q26.24 50.20 25.40 48.89Q24.55 47.58 25.90 47.20Q27.26 46.81 29.76 45.80Q32.25 44.78 34.96 43.17Q37.67 41.57 39.11 40.21Q40.55 38.86 41.02 38.18Q41.48 37.50 41.86 36.49Q42.24 35.47 43.51 34.71Q44.78 33.95 45.67 33.10Q46.56 32.25 47.32 31.24Q48.08 30.22 48.55 29.29Q49.02 28.36 49.19 27.89Q49.35 27.43 49.44 26.24Q49.52 25.06 49.52 25.78Q49.52 26.50 49.65 26.50Q49.78 26.50 49.78 26.20Q49.78 25.90 49.90 25.90Q50.03 25.90 50.29 25.44Q50.54 24.97 51.13 23.41Q51.72 21.84 51.98 20.66Q52.23 19.47 52.02 18.29Z"

/** Traced contours of the orbiting ribbon, front and back passes as they appear in the source. */
const RIBBON =
  "M45.59 11.64Q48.68 11.34 52.06 11.64Q55.45 11.94 57.61 12.74Q59.77 13.54 61.04 14.73Q62.31 15.92 62.69 16.76Q63.07 17.61 63.11 18.88Q63.15 20.15 62.81 21.25Q62.48 22.35 61.88 23.32Q61.29 24.30 59.56 26.12Q57.82 27.94 56.17 29.12Q54.52 30.31 54.43 30.56Q54.35 30.81 54.26 30.69Q54.18 30.56 52.61 31.53Q51.05 32.51 48.42 33.74Q45.80 34.96 46.14 34.67Q46.48 34.37 46.35 34.29Q46.22 34.20 45.93 34.41Q45.63 34.62 47.87 32.76Q50.12 30.90 51.64 28.99Q53.16 27.09 53.12 27.34Q53.08 27.60 53.71 26.92Q54.35 26.24 55.62 23.92Q56.89 21.59 57.02 21.08Q57.14 20.57 57.02 19.98Q56.89 19.39 56.21 18.58Q55.53 17.78 54.81 17.27Q54.10 16.76 52.95 16.17Q51.81 15.58 51.30 15.49Q50.79 15.41 51.51 16.42Q52.23 17.44 51.98 17.27Q51.72 17.10 51.89 17.74Q52.06 18.37 52.06 19.30Q52.06 20.23 51.26 22.60Q50.46 24.97 50.20 25.44Q49.95 25.90 49.82 25.90Q49.69 25.90 49.69 26.20Q49.69 26.50 49.57 25.78Q49.44 25.06 49.35 26.24Q49.27 27.43 49.10 27.89Q48.93 28.36 49.10 27.09Q49.27 25.82 49.23 24.76Q49.19 23.70 48.85 22.56Q48.51 21.42 47.70 20.06Q46.90 18.71 45.59 17.57Q44.28 16.42 43.17 15.83Q42.07 15.24 40.80 14.81Q39.53 14.39 37.33 13.93Q35.13 13.46 36.87 13.21Q38.60 12.95 40.55 12.44Q42.50 11.94 45.59 11.64Z M9.69 25.95Q11.09 25.06 11.26 25.06Q11.43 25.06 11.47 25.23Q11.51 25.40 11.51 26.33Q11.51 27.26 10.46 28.53Q9.40 29.80 8.51 31.75Q7.62 33.69 7.66 35.64Q7.70 37.59 8.08 37.88Q8.47 38.18 10.54 39.03Q12.61 39.87 14.10 40.13Q15.58 40.38 17.69 40.42Q19.81 40.47 20.99 40.00Q22.18 39.53 21.97 39.37Q21.76 39.20 23.03 39.62Q24.30 40.04 25.14 39.96Q25.99 39.87 28.57 39.28Q31.15 38.69 32.80 38.18Q34.46 37.67 34.50 37.54Q34.54 37.42 34.24 37.42Q33.95 37.42 34.46 37.33Q34.96 37.25 35.30 37.29Q35.64 37.33 35.68 37.46Q35.72 37.59 35.51 38.94Q35.30 40.30 33.44 41.48Q31.58 42.67 29.67 43.56Q27.77 44.44 25.82 45.12Q23.87 45.80 21.21 46.39Q18.54 46.98 16.51 47.15Q14.48 47.32 12.49 47.24Q10.50 47.15 8.68 46.69Q6.86 46.22 5.80 45.71Q4.74 45.21 3.64 44.28Q2.54 43.34 1.86 42.16Q1.19 40.97 0.97 39.96Q0.76 38.94 0.97 37.29Q1.19 35.64 1.86 34.20Q2.54 32.76 3.51 31.49Q4.49 30.22 6.39 28.53Q8.30 26.84 9.69 25.95Z"

/** Bubble dots, centres and radii measured from the artwork. */
const DOTS = [{cx: 27.53, cy: 25.65, r: 2.24}, {cx: 34.57, cy: 25.64, r: 2.26}, {cx: 41.57, cy: 25.66, r: 2.24}]

/** Gradient axis and stops sampled along the ribbon's own principal axis. */
const RIBBON_GRADIENT = {
  x1: 62.27,
  y1: 15.8,
  x2: 2.89,
  y2: 44.63,
  stops: ["#92a9f9", "#87b7f7", "#a691f2"],
}

const DOT_COLOUR = "#8ea6f5"
const FIGURE_ON_LIGHT = "#272e39"
const FIGURE_ON_DARK = "#FEFCFD"

function Mark({ size, animated, tone }: { size: number; animated: boolean; tone: LogoTone }) {
  // Unique per instance: two lockups on one page would otherwise share one gradient id.
  const gradientId = `intermind-ribbon-${useId()}`
  const figure = tone === "onDark" ? FIGURE_ON_DARK : FIGURE_ON_LIGHT

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label="InterMind"
      className="shrink-0"
    >
      <defs>
        <linearGradient
          id={gradientId}
          x1={RIBBON_GRADIENT.x1}
          y1={RIBBON_GRADIENT.y1}
          x2={RIBBON_GRADIENT.x2}
          y2={RIBBON_GRADIENT.y2}
          gradientUnits="userSpaceOnUse"
        >
          {RIBBON_GRADIENT.stops.map((colour, i) => (
            <stop key={colour + i} offset={i / (RIBBON_GRADIENT.stops.length - 1)} stopColor={colour} />
          ))}
        </linearGradient>
      </defs>

      <path d={HEAD} fill={figure} fillRule="evenodd" />
      <path d={RIBBON} fill={`url(#${gradientId})`} fillRule="evenodd" />
      {DOTS.map((dot, i) => (
        <circle key={dot.cx} cx={dot.cx} cy={dot.cy} r={dot.r} fill={DOT_COLOUR}>
          {animated && (
            // The three dots of a reply being composed, a beat apart.
            <animate
              attributeName="opacity"
              values="1;0.35;1"
              dur="1.8s"
              begin={`${i * 0.22}s`}
              repeatCount="indefinite"
              calcMode="spline"
              keySplines="0.16 1 0.3 1;0.16 1 0.3 1"
              keyTimes="0;0.5;1"
            />
          )}
        </circle>
      ))}
    </svg>
  )
}

/** Serif, single weight, single colour, matching the artwork's wordmark. */
function Wordmark({ fontSize, tone }: { fontSize: number; tone: LogoTone }) {
  return (
    <span
      className={`font-semibold leading-none tracking-[-0.015em] ${
        tone === "onDark" ? "text-white" : "text-black"
      }`}
      style={{ fontFamily: "var(--font-wordmark)", fontSize }}
    >
      InterMind
    </span>
  )
}

export function Logo({
  size = 32,
  withWordmark = true,
  variant,
  className = "",
  animated = false,
  tone = "onLight",
}: LogoProps) {
  const reducedMotion = usePrefersReducedMotion()
  const canAnimate = animated && !reducedMotion
  const resolved: LogoVariant = variant ?? (withWordmark ? "inline" : "mark")

  if (resolved === "mark") {
    return (
      <span className={`inline-flex ${className}`}>
        <Mark size={size} animated={canAnimate} tone={tone} />
      </span>
    )
  }

  if (resolved === "stacked") {
    return (
      <span className={`inline-flex flex-col items-center gap-4 ${className}`}>
        <Mark size={size} animated={canAnimate} tone={tone} />
        <span className="flex flex-col items-center gap-2.5">
          <Wordmark fontSize={size * 0.8} tone={tone} />
          <span className={`type-meta ${tone === "onDark" ? "text-sky-pale/80" : "text-grape"}`}>
            Autonomous interviewing
          </span>
        </span>
      </span>
    )
  }

  // Inline lockup. The mark-to-wordmark ratio and gap follow the artwork's proportions.
  return (
    <span className={`inline-flex items-center ${className}`} style={{ gap: size * 0.2 }}>
      <Mark size={size} animated={canAnimate} tone={tone} />
      <Wordmark fontSize={size * 0.62} tone={tone} />
    </span>
  )
}
