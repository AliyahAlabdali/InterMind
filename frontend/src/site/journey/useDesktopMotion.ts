import { useEffect, useState } from "react"
import { desktopEligible } from "./journeyState"

export function useDesktopMotion() {
  const [enabled, setEnabled] = useState(false)
  useEffect(() => {
    const query = matchMedia("(min-width: 1024px) and (min-height: 600px) and (prefers-reduced-motion: no-preference)")
    const update = () => setEnabled(query.matches && desktopEligible(innerWidth, innerHeight, matchMedia("(prefers-reduced-motion: reduce)").matches))
    update(); query.addEventListener("change", update)
    return () => query.removeEventListener("change", update)
  }, [])
  return enabled
}
