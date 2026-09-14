import type { HTMLAttributes, ReactNode } from "react"

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

export function Card({ children, className = "", ...rest }: CardProps) {
  return (
    <div
      className={`rounded-2xl border border-ivory-200 bg-ivory-50 p-6 shadow-soft ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
