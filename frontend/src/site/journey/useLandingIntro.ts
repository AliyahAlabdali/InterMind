import { useCallback, useEffect, useRef, useState } from "react"

/**
 * The opening's phases, in the order they play.
 *
 * They are the beats of a short story about what InterMind does, not stages of a loading screen:
 * the name and what it is for, a machine turning into view, the interview waking up on it,
 * the candidate being listened to, the analysis assembling around it, and then the whole
 * composition settling into the place it occupies for the rest of the visit.
 */
export type IntroPhase = "brand" | "reveal" | "wake" | "listen" | "analyze" | "dock" | "settled"

/** Phases as an ordinal, so a consumer can ask "have we reached X yet" instead of listing phases. */
export const INTRO_STEP: Record<IntroPhase, number> = {
  brand: 0, reveal: 1, wake: 2, listen: 3, analyze: 4, dock: 5, settled: 6,
}

/**
 * The clock, in milliseconds from mount.
 *
 * Phases are start times, not durations, and the visuals deliberately overrun them: the name is
 * still legible while the machine is turning, and the screen lights before the turn has quite
 * finished. Overlapping is what keeps a sequence with six readable beats inside five seconds
 * rather than nine. The tagline holds for about two seconds, which is what it takes to read.
 */
const DESKTOP: ReadonlyArray<readonly [number, IntroPhase]> = [
  [1250, "reveal"], [2400, "wake"], [3050, "listen"], [3600, "analyze"], [4900, "dock"], [5720, "settled"],
]

/**
 * Phones, small windows, and anything else that never gets the 3D machine.
 *
 * There is no choreography to watch here, so there is nothing to pace: the name is shown long
 * enough to read and the page resolves. Running the desktop timeline would be five seconds of
 * waiting for a sequence that is not being drawn.
 */
const LIGHT: ReadonlyArray<readonly [number, IntroPhase]> = [[1500, "dock"], [2100, "settled"]]

let hasOpened = false

/** One finite opening per SPA session. A hash, restored position, or user intent wins. */
export function useLandingIntro() {
  const [phase, setPhase] = useState<IntroPhase>(() => hasOpened || location.hash || scrollY > 0 ? "settled" : "brand")
  const cancel = useRef<() => void>(() => {})
  const finish = useCallback(() => { cancel.current(); setPhase("settled") }, [])
  useEffect(() => {
    hasOpened = true
    if (phase === "settled") return
    const reduced = matchMedia("(prefers-reduced-motion: reduce)")
    const desktop = matchMedia("(min-width: 1024px) and (min-height: 600px)")
    const timers: number[] = []
    // Reduced motion keeps the name and drops the cinema: no turn, no flying cards, no wait.
    if (reduced.matches) timers.push(window.setTimeout(finish, 320))
    else for (const [ms, next] of desktop.matches ? DESKTOP : LIGHT)
      timers.push(window.setTimeout(() => setPhase(next), ms))
    const hide = () => { if (document.hidden) finish() }
    const events = ["wheel", "touchstart", "pointerdown", "keydown", "scroll", "resize"] as const
    events.forEach(name => window.addEventListener(name, finish, { passive: true, once: true }))
    document.addEventListener("visibilitychange", hide)
    reduced.addEventListener("change", finish)
    const cleanup = () => {
      timers.forEach(clearTimeout)
      events.forEach(name => window.removeEventListener(name, finish))
      document.removeEventListener("visibilitychange", hide); reduced.removeEventListener("change", finish)
    }
    cancel.current = cleanup
    return cleanup
    // The timeline starts once. Phase updates must not restart its deadlines.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finish])
  return { phase, step: INTRO_STEP[phase], finish }
}
