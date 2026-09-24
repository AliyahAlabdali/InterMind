import type { Transition, Variants } from "motion/react"

/**
 * One motion vocabulary for the whole product, mirroring the CSS tokens in index.css.
 *
 * The rule this encodes (brief §21): motion communicates product state, hierarchy, interaction
 * or narrative - or it doesn't ship. Nothing here loops forever except the interviewer's own
 * idle breathing, which *is* the product telling you the system is alive and waiting.
 */

/** Settle curve - fast out, long calm tail. Never springy, never bouncy. */
export const EASE_SETTLE = [0.16, 1, 0.3, 1] as const

export const DURATION = {
  quick: 0.15,
  state: 0.32,
  emphasis: 0.52,
} as const

export const transition = {
  quick: { duration: DURATION.quick, ease: EASE_SETTLE },
  state: { duration: DURATION.state, ease: EASE_SETTLE },
  emphasis: { duration: DURATION.emphasis, ease: EASE_SETTLE },
} satisfies Record<string, Transition>

/** Content arriving: a short rise into place. The workhorse. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: transition.state },
  exit: { opacity: 0, y: -8, transition: transition.quick },
}

/** Same, but sized for a whole section rather than a line of text. */
export const riseSection: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: transition.emphasis },
}

export const fade: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: transition.state },
  exit: { opacity: 0, transition: transition.quick },
}

/**
 * Parent wrapper that walks its children in, one after another. `stagger` is deliberately
 * small: this should read as a single composed reveal, not as items queueing up.
 */
export function stagger(gap = 0.06, delay = 0): Variants {
  return {
    hidden: {},
    visible: { transition: { staggerChildren: gap, delayChildren: delay } },
  }
}

/**
 * The adaptive transition: a new question replacing the previous one. Enters from below and
 * leaves upward, so the movement itself says "this came after, and because of, that".
 */
export const questionSwap: Variants = {
  hidden: { opacity: 0, y: 14, filter: "blur(4px)" },
  visible: { opacity: 1, y: 0, filter: "blur(0px)", transition: transition.emphasis },
  exit: { opacity: 0, y: -14, filter: "blur(4px)", transition: transition.state },
}

/** A target flipping to "assessed", or evidence landing. One beat, then still. */
export const evidenceLand: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1, transition: transition.emphasis },
}
