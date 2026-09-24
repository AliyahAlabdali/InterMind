import { useEffect, useRef } from "react"
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion"
import type { InterviewerSceneHandle, InterviewerTone } from "./scene"
import { INTERVIEWER_POSE } from "./types"
import type { InterviewerState } from "./types"

interface InterviewerProps {
  state: InterviewerState
  /** Live speech amplitude 0..1 - drives the wave travelling up the contours while speaking. */
  level?: number
  /** Follow the pointer. On by default in the hero; off inside the interview, where the
   * candidate's attention belongs on the question rather than on a toy. */
  trackPointer?: boolean
  /** Which surface this is drawn on. The instrument relights itself for the dark interview
   *  stage; on white it stays the near-black filament figure the site uses. */
  tone?: InterviewerTone
  className?: string
}

/**
 * The InterMind interviewer. The same component renders in the landing hero and in the live
 * interview - that continuity is the point (brief §2): the presence you meet on the site is
 * literally the one that interviews you.
 */
export function Interviewer({
  state,
  level = 0,
  trackPointer = false,
  tone = "onLight",
  className = "",
}: InterviewerProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<InterviewerSceneHandle | null>(null)
  const reducedMotion = usePrefersReducedMotion()
  // Read by the async scene loader so the first pose reflects the state at load time, not the
  // state at the moment the import was kicked off.
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let cancelled = false

    // three.js is loaded on demand, not in the main bundle: most of the workspace never renders
    // an interviewer, and shouldn't pay ~700KB for one.
    void import("./scene").then(({ createInterviewerScene }) => {
      if (cancelled) return
      const scene = createInterviewerScene(canvas, { reducedMotion, tone })
      sceneRef.current = scene
      scene?.setPose(INTERVIEWER_POSE[stateRef.current])
    })

    return () => {
      cancelled = true
      sceneRef.current?.dispose()
      sceneRef.current = null
    }
    // `state` is deliberately not a dependency: rebuilding the WebGL context on every state
    // change would throw away the eased transition that makes states read as transitions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, tone])

  useEffect(() => {
    sceneRef.current?.setPose(INTERVIEWER_POSE[state])
    // Evidence is a moment, not a mode - it gets one convergence sweep on entry.
    if (state === "evidence") sceneRef.current?.pulse()
  }, [state])

  useEffect(() => {
    sceneRef.current?.setLevel(level)
  }, [level])

  // Stop rendering while the interviewer is scrolled off screen. On the landing page it would
  // otherwise keep drawing at full cost for the whole length of the page.
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const io = new IntersectionObserver(
      ([entry]) => sceneRef.current?.setActive(entry.isIntersecting),
      { rootMargin: "120px" },
    )
    io.observe(host)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!trackPointer || reducedMotion) return
    function handleMove(event: PointerEvent) {
      const x = (event.clientX / window.innerWidth) * 2 - 1
      const y = (event.clientY / window.innerHeight) * 2 - 1
      sceneRef.current?.setPointer(x, y)
    }
    window.addEventListener("pointermove", handleMove, { passive: true })
    return () => window.removeEventListener("pointermove", handleMove)
  }, [trackPointer, reducedMotion])

  return (
    <div ref={hostRef} className={`relative isolate ${className}`}>
      {/* Static fallback sits behind the canvas: if WebGL never initialises, this reads as a
          composed mark rather than an empty box. `isolate` on the host is load-bearing - it
          creates the stacking context that keeps a negative z-index child above the page
          background instead of behind it. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 flex items-center justify-center"
      >
        <span
          className={`block h-2/3 w-2/3 rounded-full blur-2xl ${
            tone === "onDark" ? "bg-space/55" : "bg-space/15"
          }`}
        />
      </div>
      <canvas ref={canvasRef} className="h-full w-full" aria-hidden="true" />
    </div>
  )
}
