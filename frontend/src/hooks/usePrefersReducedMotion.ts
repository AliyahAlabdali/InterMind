import { useEffect, useState } from "react"

/** Single source of truth for reduced-motion checks, instead of each component re-querying
 * matchMedia on its own. Reactive: a viewer toggling the OS setting mid-session is respected. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  )

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)")
    const handler = () => setReduced(query.matches)
    query.addEventListener("change", handler)
    return () => query.removeEventListener("change", handler)
  }, [])

  return reduced
}
