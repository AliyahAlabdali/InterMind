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
 * Phones and small windows, which get the flat composition rather than the 3D machine.
 *
 * This used to be `[[1500, "dock"], [2100, "settled"]]` - two beats, on the reasoning that with
 * no machine turning there was no choreography to pace. That was wrong in practice: it left a
 * phone staring at an opaque panel for a second and a half with only a wordmark on it, which
 * reads as a loading screen rather than as an opening.
 *
 * The flat composition plays the same beats the model does - the screen lighting, the answer
 * being heard, the analysis arriving - so there is something to watch here after all. The phases
 * are the desktop ones at roughly half the running time, because a phone visitor is closer to
 * the screen, has less of it, and is far more likely to be mid-task.
 */
const MOBILE: ReadonlyArray<readonly [number, IntroPhase]> = [
  [520, "reveal"], [1020, "wake"], [1480, "listen"], [1900, "analyze"], [2400, "dock"], [3020, "settled"],
]

/** How far the page must actually travel before a scroll counts as "get on with it". */
const SCROLL_INTENT_PX = 24

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
    // Reduced motion keeps the name and drops the cinema: no turn, no flying cards. It still
    // holds long enough to be read - at 320ms the brand was gone before the eye reached it, so
    // the opening registered as a black flash rather than as a deliberately quiet version of
    // itself. The brand is painted outright rather than animated in; see landing.css.
    if (reduced.matches) timers.push(window.setTimeout(finish, 1100))
    else for (const [ms, next] of desktop.matches ? DESKTOP : MOBILE)
      timers.push(window.setTimeout(() => setPhase(next), ms))
    const hide = () => { if (document.hidden) finish() }
    // Intent, and only intent. `resize` and a bare `scroll` used to be in this list and were
    // what made the opening invisible on an iPhone: Safari fires both by itself while the
    // address bar settles during load, so the sequence ended before its first frame - on a
    // phone, every time, with no user action at all. A wheel, a touch, a pointer or a key is
    // unambiguous; travel down the page is handled separately below.
    const events = ["wheel", "touchstart", "pointerdown", "keydown"] as const
    events.forEach(name => window.addEventListener(name, finish, { passive: true, once: true }))
    // Scrolling counts once the page has actually moved. The threshold is what separates a
    // visitor leaving from the viewport resizing under a collapsing browser chrome.
    const origin = scrollY
    const onScroll = () => { if (Math.abs(scrollY - origin) > SCROLL_INTENT_PX) finish() }
    window.addEventListener("scroll", onScroll, { passive: true })
    document.addEventListener("visibilitychange", hide)
    reduced.addEventListener("change", finish)
    const cleanup = () => {
      timers.forEach(clearTimeout)
      events.forEach(name => window.removeEventListener(name, finish))
      window.removeEventListener("scroll", onScroll)
      document.removeEventListener("visibilitychange", hide); reduced.removeEventListener("change", finish)
    }
    cancel.current = cleanup
    return cleanup
    // The timeline starts once. Phase updates must not restart its deadlines.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finish])
  return { phase, step: INTRO_STEP[phase], finish }
}
