import type { InputHTMLAttributes } from "react"

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
}

export function TextInput({ label, id, className = "", ...rest }: TextInputProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink-soft">
        {label}
      </label>
      <input
        id={id}
        className={`w-full rounded-[10px] border border-border bg-white px-4 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-periwinkle disabled:bg-ivory-100 ${className}`}
        {...rest}
      />
    </div>
  )
}
