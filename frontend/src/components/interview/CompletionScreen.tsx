import { motion } from "motion/react"
import { Interviewer } from "../../interviewer/Interviewer"
import { rise, stagger } from "../../design/motion"
import { Stage } from "./StageShell"

/**
 * The last thing the candidate sees.
 *
 * Stays in the interview's own room rather than handing back to the light product surface: the
 * interview has just ended, and dropping someone onto a white page the instant they send their
 * final answer reads as the session being cut off rather than closed.
 *
 * The interviewer resolves - `evidence` is its one composed, fully-ordered configuration - and
 * then holds. It is the only place that pose is used in the candidate's flow, which is what
 * makes it mean "that's done" rather than being another idle state.
 *
 * Deliberately no score, no summary and no link to anything. What the interview concluded is
 * the hiring team's to read, not the candidate's, and saying so plainly is better than a screen
 * that implies there is more to see here.
 */
export function CompletionScreen() {
  return (
    <Stage>
      <motion.div
        variants={stagger(0.12)}
        initial="hidden"
        animate="visible"
        className="relative z-10 mx-auto flex flex-1 max-w-xl flex-col items-center justify-center gap-9 px-6 py-20 text-center"
      >
        <motion.div variants={rise} className="relative">
          <span
            aria-hidden="true"
            className="stage-veil pointer-events-none absolute inset-[-28%] -z-10 rounded-full"
          />
          <Interviewer state="evidence" tone="onDark" className="h-40 w-40 sm:h-52 sm:w-52" />
        </motion.div>

        <motion.div variants={rise}>
          <h1 className="type-question text-balance text-white">That's the interview.</h1>
          <p className="mx-auto mt-5 max-w-md leading-relaxed text-sky-pale/75">
            Thank you for your time. Your answers have gone to the hiring team, along with what
            InterMind took from them. There's nothing else to do here.
          </p>
        </motion.div>
      </motion.div>
    </Stage>
  )
}
