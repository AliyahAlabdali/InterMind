/** Coalesced work with no idle loop. Visibility and cleanup are owned in one place. */
export function demandFrame(draw: () => void) {
  let frame = 0, disposed = false
  const cancel = () => { cancelAnimationFrame(frame); frame = 0 }
  const invalidate = () => {
    if (disposed || document.hidden || frame) return
    frame = requestAnimationFrame(() => { frame = 0; if (!disposed && !document.hidden) draw() })
  }
  const visibility = () => { if (document.hidden) cancel(); else invalidate() }
  document.addEventListener("visibilitychange", visibility)
  return { invalidate, cancel, dispose() { disposed = true; cancel(); document.removeEventListener("visibilitychange", visibility) } }
}
