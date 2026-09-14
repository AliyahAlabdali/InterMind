import type { ReactNode } from "react"

type Tone = "neutral" | "blush" | "sky" | "lilac" | "success" | "warning" | "danger"

interface BadgeProps {
  children: ReactNode
  tone?: Tone
  className?: string
}

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-ivory-100 text-ink-soft",
  blush: "bg-blush/60 text-ink",
  sky: "bg-sky/60 text-ink",
  lilac: "bg-lilac/60 text-ink",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
}

export function Badge({ children, tone = "neutral", className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </span>
  )
}
