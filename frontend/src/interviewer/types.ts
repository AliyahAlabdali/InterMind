/**
 * The interviewer's visual states (brief §2). These are product states, not decoration: each
 * one corresponds to something the backend or the candidate is actually doing right now, and
 * the same vocabulary drives the avatar, the status line and the input affordances.
 */
export type InterviewerState =
  /** Waiting. The cage rests loosely spherical, axes precessing slowly. */
  | "idle"
  /** The candidate has the floor. The cage opens wide and evens out, receptive. */
  | "listening"
  /** Delivering a question aloud. A wave travels through the rings on the speech envelope. */
  | "speaking"
  /** The answer is with the evaluator. The cage compresses and the axes tumble. */
  | "thinking"
  /** Evidence was recorded. Everything resolves into one exact, ordered configuration. */
  | "evidence"
  /** The evaluator decided to go deeper. The axes converge into one investigating cone. */
  | "followUp"

/**
 * The status line beside the interviewer, in the candidate's language.
 *
 * These describe what the person across the table is doing, never what the system is doing to
 * them: "Thinking", not "Analyzing response"; "Noted", not "Evidence detected". The candidate
 * has no reason to learn how the interview is scored while they are sitting in it.
 */
export const INTERVIEWER_STATUS_LABEL: Record<InterviewerState, string> = {
  idle: "Ready",
  speaking: "Speaking",
  listening: "Listening",
  thinking: "Thinking",
  evidence: "Noted",
  followUp: "Going deeper",
}

/**
 * Per-state targets for the aperture. The scene eases toward these rather than snapping, which
 * keeps state changes readable as transitions instead of cuts.
 *
 * The property that matters most here: no two states differ only in speed. Each one is a
 * different *configuration* of the same instrument, which is what lets the reduced-motion path
 * drop continuous movement and still carry all six meanings.
 *
 * - `open`    the radius of the cage
 * - `tilt`    how widely the ring axes spread, from near-coplanar to fully spherical
 * - `spin`    precession rate of the individual axes
 * - `scatter` how far the nucleus shards disperse from the centre
 * - `order`   regularity. 1 is an even, deliberate distribution; 0 is scattered axes
 * - `charge`  accent intensity, from quiet ink to full maroon
 * - `focus`   converges every axis onto a single heading
 */
export interface InterviewerPose {
  open: number
  tilt: number
  spin: number
  scatter: number
  order: number
  charge: number
  focus: number
}

export const INTERVIEWER_POSE: Record<InterviewerState, InterviewerPose> = {
  /** Calm and stable: a loose spherical cage, slow precession, nucleus held. */
  idle: { open: 0.4, tilt: 0.92, spin: 0.1, scatter: 0.3, order: 0.55, charge: 0.28, focus: 0 },
  /** Opens outward. The widest, most even cage in the set: receptive and still. */
  listening: {
    open: 0.82,
    tilt: 1.3,
    spin: 0.03,
    scatter: 0.18,
    order: 0.85,
    charge: 0.45,
    focus: 0,
  },
  /** Communicating: mid-open, carrying the speech wave through the rings. */
  speaking: {
    open: 0.58,
    tilt: 1.02,
    spin: 0.07,
    scatter: 0.4,
    order: 0.6,
    charge: 0.75,
    focus: 0,
  },
  /** Reorganising: the cage compresses and the axes tumble out of agreement. */
  thinking: {
    open: 0.3,
    tilt: 0.55,
    spin: 0.34,
    scatter: 0.62,
    order: 0.3,
    charge: 0.5,
    focus: 0,
  },
  /** Synthesis: every axis evenly distributed, nucleus condensed, one sweep around the set. */
  evidence: { open: 0.66, tilt: 1.16, spin: 0.01, scatter: 0.04, order: 1, charge: 1, focus: 0 },
  /** Investigative: the axes converge on one heading, turning the cage into a directed cone. */
  followUp: {
    open: 0.38,
    tilt: 0.72,
    spin: 0.13,
    scatter: 0.34,
    order: 0.5,
    charge: 0.86,
    focus: 1,
  },
}
