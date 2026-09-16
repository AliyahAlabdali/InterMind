import type { HTMLAttributes, ReactNode } from "react"

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
}

export function Card({ children, className = "", ...rest }: CardProps) {
  return (
    <div
      className={`rounded-[14px] border border-border bg-white p-6 ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
