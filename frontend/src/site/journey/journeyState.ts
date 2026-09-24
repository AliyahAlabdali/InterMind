export interface JourneyAnchor {
  at: number
  x: number
  y: number
  size: number
  pose: number
  name: string
}
export interface JourneyState {
  x: number; y: number; size: number
  from: number; to: number; mix: number; name: string
}
export const clamp = (n: number, min = 0, max = 1) => Math.max(min, Math.min(max, n))
const ease = (n: number) => n * n * (3 - 2 * n)
export function desktopEligible(width: number, height: number, reduced: boolean) {
  return width >= 1024 && height >= 600 && !reduced
}

/** Pure position mapping: jumps and reversal require no previous state or animation clock. */
export function journeyState(scroll: number, anchors: readonly JourneyAnchor[]): JourneyState | null {
  if (!anchors.length || !Number.isFinite(scroll)) return null
  let index = anchors.findIndex(a => a.at > scroll) - 1
  if (index === -2) index = anchors.length - 1
  if (index < 0) index = 0
  const a = anchors[index], b = anchors[Math.min(index + 1, anchors.length - 1)]
  const progress = a === b ? 0 : clamp((scroll - a.at) / Math.max(1, b.at - a.at))
  const mix = ease(progress)
  const lerp = (start: number, end: number) => start + (end - start) * mix
  // Travel is direct, while explicit identical-pose anchors author real periods of stillness.
  return { x: lerp(a.x, b.x), y: a.y + (b.y - a.y) * progress, size: lerp(a.size, b.size),
    from: a.pose, to: b.pose, mix, name: progress < .5 ? a.name : b.name }
}
