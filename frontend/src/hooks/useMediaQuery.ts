import { useEffect, useState } from "react"

/**
 * Subscribe to a media query in JS.
 *
 * Used where a breakpoint has to decide what gets *mounted*, not merely what is visible. The
 * process section needs this: rendering a mobile copy and a desktop copy of the interviewer and
 * hiding one with `lg:hidden` would keep two WebGL contexts alive for the life of the page, and
 * the hidden canvas would initialise at zero size. Tailwind's responsive classes cannot express
 * "do not create this", so the breakpoint has to exist in JS too.
 *
 * Use CSS for everything else. This is for mounting decisions only.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined") return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    const list = window.matchMedia(query)
    const handler = () => setMatches(list.matches)
    // Sync once on mount as well: the query can differ from the initial state if the viewport
    // changed between render and effect, which happens on rotation and in devtools.
    handler()
    list.addEventListener("change", handler)
    return () => list.removeEventListener("change", handler)
  }, [query])

  return matches
}

/** The `lg` breakpoint, matching Tailwind's default. Kept here so the JS and CSS agree. */
export const LG_QUERY = "(min-width: 1024px)"
