import { useEffect, useRef, useState } from "react"
import { LandingInstrument } from "./journey/LandingInstrument"
import { demandFrame } from "./journey/demandFrame"
import { clamp, journeyState, type JourneyAnchor } from "./journey/journeyState"
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion"
import { LG_QUERY, useMediaQuery } from "../hooks/useMediaQuery"
import type { InterviewerState } from "../interviewer/types"

/**
 * How InterMind works, in six steps, with the instrument tracking whichever step is being read.
 *
 * ## Hierarchy
 *
 * Short label first, explanation second. An earlier version made the full sentence the heading
 * and put a step counter above it, which turned a product explanation into an instruction
 * manual. The label is what the visitor navigates by; the sentence is what they read if they
 * want more. The index is a quiet ordinal, not a "Step 1 of 6" progress readout.
 *
 * Copy stays in words a recruiter already uses. The engineering is real but it is not the
 * landing page's job to describe it.
 */
interface Step {
  /** Two to four words. This is the primary label. */
  label: string
  body: string
  state: InterviewerState
}

const STEPS: Step[] = [
  {
    label: "Read the role",
    body: "InterMind reads the job description and works out the skills and experience the job actually calls for.",
    state: "thinking",
  },
  {
    label: "Plan the interview",
    body: "Those requirements become a plan for the conversation, shaped around this job rather than a generic list of questions.",
    state: "idle",
  },
  {
    label: "Ask questions",
    body: "InterMind chooses each question from the role and from what the candidate has already said.",
    state: "speaking",
  },
  {
    label: "Listen to the answer",
    body: "Every response is weighed before the system decides what should happen next.",
    state: "listening",
  },
  {
    label: "Follow up",
    body: "If an answer stops short, InterMind asks a more specific question about that same thing instead of moving on.",
    state: "followUp",
  },
  {
    label: "Build the report",
    body: "The interview becomes a clear summary of what the candidate showed, with their own words attached to it.",
    state: "evidence",
  },
]

export function ProcessStage() {
  const sectionRef = useRef<HTMLElement>(null)
  const stepRefs = useRef<(HTMLDivElement | null)[]>([])
  const [travel, setTravel] = useState({ progress: 0, entry: 1, exit: 0 })
  const active = Math.round(travel.progress)
  const reducedMotion = usePrefersReducedMotion()
  // Decides which of the two compositions is *mounted*, not merely which is visible.
  const isDesktop = useMediaQuery(LG_QUERY)

  useEffect(() => {
    const section = sectionRef.current
    const nodes = stepRefs.current.filter(Boolean) as HTMLDivElement[]
    if (!section || !nodes.length) return
    let anchors: JourneyAnchor[] = [], first = 0, last = 0, results = 0
    const work = demandFrame(() => {
      const sample = journeyState(scrollY, anchors)
      if (!sample) return
      const progress = sample.from + (sample.to - sample.from) * sample.mix
      setTravel({ progress, entry: clamp((scrollY - first + innerHeight * .7) / (innerHeight * .55)), exit: clamp((scrollY - last) / Math.max(1, results - last)) })
    })
    const measure = () => {
      const y = scrollY
      anchors = nodes.flatMap((node, index) => {
        const r = node.getBoundingClientRect(), at = r.top + y + r.height / 2 - innerHeight / 2
        return [-.16, .16].map(hold => ({ at: at + r.height * hold, x: 0, y: 0, size: 352, pose: index, name: STEPS[index].state }))
      })
      first = anchors[0].at; last = anchors[anchors.length - 1].at
      results = (document.querySelector("#results")?.getBoundingClientRect().top ?? 0) + y - innerHeight * .55
      work.invalidate()
    }
    const observer = new ResizeObserver(measure); observer.observe(section)
    const fonts = () => measure()
    document.fonts?.addEventListener("loadingdone", fonts)
    window.addEventListener("scroll", work.invalidate, { passive: true })
    window.addEventListener("resize", measure); window.addEventListener("pageshow", measure)
    measure()
    return () => { observer.disconnect(); work.dispose(); document.fonts?.removeEventListener("loadingdone", fonts); window.removeEventListener("scroll", work.invalidate); window.removeEventListener("resize", measure); window.removeEventListener("pageshow", measure) }
  }, [isDesktop])

  const step = STEPS[active]
  const ordinal = String(active + 1).padStart(2, "0")

  return (
    <section ref={sectionRef} id="how-it-works" className="scroll-mt-20">
      <div className="mx-auto w-full max-w-[86rem] px-5 sm:px-8">
        <div className="max-w-2xl">
          <span className="type-meta text-accent">How it works</span>
          <h2 className="type-section mt-5 text-balance text-fg">
            From a job description to a written-up interview.
          </h2>
          <p className="type-body mt-5 text-fg-soft">
            Six steps, start to finish. You provide the role and send a link; InterMind does the
            rest and hands back something you can make a decision on.
          </p>
        </div>
      </div>

      <div className="mx-auto w-full max-w-[86rem] px-5 sm:px-8">
        <div className="grid grid-cols-1 gap-x-16 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
          {/* Desktop side column. Gated on the media query rather than `lg:hidden`, so exactly
              one interviewer exists in the document at any width. Hiding a duplicate with CSS
              would leave a second WebGL context alive and a canvas initialised at zero size. */}
          {isDesktop && (
            <div className="process-dock sticky top-0 flex h-screen items-center justify-center self-start">
              <div
                data-process-travel={JSON.stringify(travel)}
                style={reducedMotion ? undefined : { transform: `translate3d(${(1 - travel.entry) * 90 + Math.sin(travel.progress * Math.PI / 5) * 18}px, ${(1 - travel.entry) * -70 + travel.exit * 85}px, 0) scale(${.94 + travel.entry * .06 - travel.exit * .35})`, opacity: 1 - travel.exit }}
                className="flex w-full max-w-sm flex-col items-center"
              >
                <LandingInstrument progress={travel.progress} className="h-[22rem] w-[22rem]" />
                <div className="mt-6 flex w-full items-baseline justify-center gap-3 border-t border-hair pt-5">
                  <span className="type-meta text-fg-muted">{ordinal}</span>
                  <p className="type-sub text-fg">{step.label}</p>
                </div>
              </div>
            </div>
          )}

          <div>
            {STEPS.map((item, index) => {
              const isActive = index === active
              return (
                <div
                  id={`process-${["read", "plan", "ask", "listen", "follow", "report"][index]}`}
                  data-process-step={index}
                  key={item.label}
                  ref={(node) => {
                    stepRefs.current[index] = node
                  }}
                  className="process-step flex flex-col justify-center py-10 lg:min-h-[80vh] lg:py-10"
                >
                  {!isDesktop && <img src={`/models/pose-${item.state}.webp`} alt="" aria-hidden="true" loading="lazy" width="120" height="120" className="mb-4 h-28 w-28 self-start" />}
                  <div className="flex items-center gap-4">
                    <span
                      className={`type-meta shrink-0 transition-colors duration-500 ${
                        isActive ? "text-accent" : "text-fg-muted"
                      }`}
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div
                      className={`h-px flex-1 transition-colors duration-500 ${
                        isActive ? "bg-accent/45" : "bg-hair"
                      }`}
                    />
                  </div>

                  {/* Inactive steps recede through colour rather than opacity. The values are
                      near-black heading of the step you are reading against full-strength
                      grape for the others - a 20:1 / 6:1 step, which is a clear recession and
                      still leaves every line on screen readable. The previous /60 measured
                      2.0:1, so the five steps you were not reading sat below the AA floor the
                      whole time. Body copy no longer dims at all: at this size, anything light
                      enough to read as "inactive" is too light to read. */}
                  <h3
                    className={`type-section mt-6 transition-colors duration-500 ${
                      isActive ? "text-fg" : "text-fg-muted"
                    }`}
                  >
                    {item.label}
                  </h3>
                  <p
                    className={`type-body mt-4 transition-colors duration-500 ${
                      isActive ? "text-fg-soft" : "text-fg-muted"
                    }`}
                  >
                    {item.body}
                  </p>
                  {index === 3 && <div className="adaptive-example mt-7 border-l border-hair-strong pl-5"><span className="type-meta text-accent">An example answer</span><p className="mt-3 text-lg leading-relaxed text-fg-soft">“I versioned every migration.”</p><p className="mt-3 text-sm leading-relaxed text-fg-muted">The next question stays with the candidate’s experience.</p></div>}
                  {index === 4 && <div className="adaptive-example mt-7 border-l border-hair-strong pl-5"><span className="type-meta text-accent">A follow-up to that answer</span><p className="mt-3 text-lg leading-relaxed text-fg-soft">“What happened when a migration failed?”</p><p className="mt-3 text-sm leading-relaxed text-fg-muted">The answer changed what came next.</p></div>}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
