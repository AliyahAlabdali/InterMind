import { useEffect, useRef, useState } from "react"

/**
 * The portrait Hero's own entrance, kept deliberately separate from the branding opening.
 *
 * ## Why this is its own state machine
 *
 * The opening used to drive both things. One phase attribute said what the splash was doing
 * *and* where the composition was, which meant the machine had to be staged inside the splash to
 * be staged at all - so on a phone it rose into a frame it did not belong to, sat below the fold
 * while the wordmark held, and then arrived a second time when the Hero took over. Two different
 * events were sharing one clock.
 *
 * They are different events. The opening is branding: a name, a line, and then it gets out of
 * the way. This is the product revealing itself in the place it actually lives. Separating them
 * means the splash can be short and wordmark-only, and the Hero can perform its own reveal on
 * arrival without a phase vocabulary designed for something else leaking into it.
 *
 * ## Stages
 *
 * Deliberately named for what is on screen rather than for the opening's beats, so nothing here
 * has to stay in step with the splash's story:
 *
 * - `hidden`  - below the frame, not yet arrived.
 * - `machine` - the laptop rising into its resting position, screen lighting on the way.
 * - `panels`  - transcript in from the left, competency from the right.
 * - `channel` - the live waveform up through the hinge, last.
 * - `settled` - the resting Hero, pixel-identical to what it is with no entrance at all.
 */
export type RevealStage = "hidden" | "machine" | "panels" | "channel" | "settled"

/**
 * Milliseconds from the hand-off, as start times.
 *
 * `machine` is almost immediate: the whole point is that the rise has visibly begun by the time
 * the splash has finished clearing, rather than the visitor meeting a still composition and then
 * watching it move. The cards follow once the machine is substantially in place - they annotate
 * something, so they cannot arrive before the thing they annotate.
 */
const STAGES: ReadonlyArray<readonly [number, RevealStage]> = [
  [40, "machine"], [620, "panels"], [1060, "channel"], [1620, "settled"],
]

/**
 * One reveal per SPA session, like the opening.
 *
 * A module-level flag rather than component state, because the point is that returning to the
 * landing page later does not replay it - and because an effect that re-ran would otherwise
 * restage the Hero under the visitor on every viewport change. iOS fires `resize` constantly as
 * the address bar collapses, so "does not replay" is a hard requirement, not a nicety.
 */
let hasRevealed = false

/**
 * Returns the current stage, or `null` when this viewport has no reveal to perform.
 *
 * `null` is the signal to render nothing extra at all: no attribute, no transitions, no staged
 * transforms. Desktop and reduced motion both take that path, which is what keeps them exactly
 * as they were rather than as a special case of an animation.
 */
export function useHeroReveal({ active, enabled }: { active: boolean; enabled: boolean }): RevealStage | null {
  const [stage, setStage] = useState<RevealStage>(() => (enabled && !hasRevealed ? "hidden" : "settled"))
  const started = useRef(false)

  useEffect(() => {
    if (!enabled || hasRevealed || !active || started.current) return
    started.current = true
    hasRevealed = true
    const timers = STAGES.map(([ms, next]) => window.setTimeout(() => setStage(next), ms))
    return () => timers.forEach(clearTimeout)
  }, [active, enabled])

  return enabled ? stage : null
}

/** Test seam: the module flag is what makes the reveal finite, so a test has to be able to clear it. */
export function resetHeroReveal() {
  hasRevealed = false
}
