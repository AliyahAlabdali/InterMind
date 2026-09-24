import type { IntroPhase } from "./journey/useLandingIntro"

/**
 * The opening's first beat: the name, and the one line that says what the product is for.
 *
 * It is a layer over the live Hero rather than a screen in front of it - the laptop beside it is
 * the page's own, already turning - so nothing here gates the page, and the whole thing is gone
 * the moment the visitor does anything at all.
 *
 * The brand holds, then lifts and clears out of the machine's way on its own clock rather than
 * on the phase, because the two overlap: the tagline is still being read while the turn starts.
 */
export function IntroSplash({ phase, onSkip }: { phase: IntroPhase; onSkip: () => void }) {
  if (phase === "settled") return null
  return <div className="landing-opening" data-phase={phase}>
    <div className="opening-brand" aria-hidden="true"><span>InterMind</span><p>Where the entire interview journey is driven by intelligence.</p></div>
    <button className="opening-skip" onClick={onSkip}>Skip intro</button>
  </div>
}
