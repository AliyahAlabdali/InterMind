import { useEffect, useRef } from "react"

/**
 * A thin, honest progress hairline for the longer pages: it tracks how far down the page you
 * have actually scrolled, nothing more.
 *
 * The scroll handler used to read `scrollHeight` on every event. That is a forced synchronous
 * layout, fired at scroll frequency, immediately before writing a transform to the same frame -
 * a read/write/read cycle that makes the browser re-layout the document on every scroll tick.
 * On a long page with 3D on it, that was measurable.
 *
 * Now the scrollable distance is cached and only recomputed when the document can actually have
 * changed size, and the write is batched into one rAF so reads and writes never interleave.
 */
export function ScrollMeter() {
  const barRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let maxScroll = 0
    let frame = 0

    function measure() {
      maxScroll = document.documentElement.scrollHeight - window.innerHeight
      write()
    }

    function write() {
      frame = 0
      const progress = maxScroll > 0 ? Math.min(Math.max(window.scrollY / maxScroll, 0), 1) : 0
      if (barRef.current) barRef.current.style.transform = `scaleX(${progress})`
    }

    function onScroll() {
      // Coalesce: several scroll events can land inside one frame, and only the last matters.
      if (frame === 0) frame = requestAnimationFrame(write)
    }

    measure()
    window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", measure)
    // Lazy images, font swaps and revealed sections all change page height without a resize.
    const observer = new ResizeObserver(measure)
    observer.observe(document.documentElement)

    return () => {
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", measure)
      observer.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div
      ref={barRef}
      aria-hidden="true"
      className="scroll-meter fixed left-0 top-0 z-50 h-[2px] w-full origin-left bg-accent/70"
      style={{ transform: "scaleX(0)" }}
    />
  )
}
