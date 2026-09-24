import { useEffect, useRef } from "react"
import { useDesktopMotion } from "./useDesktopMotion"
import { demandFrame } from "./demandFrame"
import { processPose, PROCESS_STATES } from "./processState"
import type { ProcessSceneHandle } from "./processScene"

/** Landing-only orchestration. The candidate's scene and component are never modified. */
export function LandingInstrument({ progress, className = "" }: { progress: number; className?: string }) {
  const enabled = useDesktopMotion()
  const host = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const current = useRef(progress)
  const invalidate = useRef<(() => void) | null>(null)
  useEffect(() => { current.current = progress; invalidate.current?.() }, [progress])
  useEffect(() => {
    const element = host.current, target = canvas.current
    if (!enabled || !element || !target) return
    let disposed = false, active = false, lost = false, loading = false
    let scene: ProcessSceneHandle | null = null
    const fallback = () => { delete element.dataset.ready }
    const work = demandFrame(() => {
      if (!active || lost || !scene) return
      try { if (scene.draw(processPose(current.current), current.current)) element.dataset.ready = "true" } catch { scene.dispose(); scene = null; fallback() }
    })
    invalidate.current = work.invalidate
    const load = async () => {
      if (loading || scene || disposed) return
      loading = true
      try {
        const { createProcessScene } = await import("./processScene")
        if (disposed) return
        scene = createProcessScene(target)
        await scene?.ready
        if (!disposed && !lost) work.invalidate()
      } catch { scene?.dispose(); scene = null; fallback() }
      finally { loading = false }
    }
    const gate = new IntersectionObserver(([entry]) => {
      active = entry.isIntersecting
      if (active) { void load(); work.invalidate() } else work.cancel()
    }, { rootMargin: "100px" })
    gate.observe(element)
    const resize = new ResizeObserver(work.invalidate); resize.observe(element)
    const contextLost = (event: Event) => { event.preventDefault(); lost = true; work.cancel(); fallback() }
    const contextRestored = () => {
      scene?.dispose(); scene = null; lost = false
      if (active) void load()
    }
    target.addEventListener("webglcontextlost", contextLost)
    target.addEventListener("webglcontextrestored", contextRestored)
    return () => {
      disposed = true; invalidate.current = null; work.dispose(); gate.disconnect(); resize.disconnect()
      target.removeEventListener("webglcontextlost", contextLost); target.removeEventListener("webglcontextrestored", contextRestored)
      scene?.dispose(); fallback()
    }
  }, [enabled])
  return <div ref={host} className={`landing-instrument relative ${className}`} aria-hidden="true" data-pose={progress.toFixed(4)}>
    <img className="instrument-poster absolute inset-0 h-full w-full" src={`/models/pose-${PROCESS_STATES[Math.round(progress)]}.webp`} width="352" height="352" alt="" loading="lazy" />
    {enabled && <canvas ref={canvas} className="absolute inset-0 h-full w-full" />}
  </div>
}
