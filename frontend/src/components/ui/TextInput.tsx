import type { InputHTMLAttributes, ReactNode, Ref } from "react"

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  /** Shown under the field. Use it to prevent an error rather than to report one. */
  hint?: ReactNode
  /** React 19 passes refs as an ordinary prop; declared so callers can focus the field. */
  ref?: Ref<HTMLInputElement>
}

export function TextInput({ label, hint, id, ref, className = "", ...rest }: TextInputProps) {
  const hintId = hint ? `${id}-hint` : undefined

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium text-fg">
        {label}
      </label>
      <input
        id={id}
        ref={ref}
        aria-describedby={hintId}
        className={`min-h-[44px] w-full rounded-[12px] border border-hair-strong bg-raise px-4 text-[0.9375rem] text-fg outline-none transition-colors duration-200 placeholder:text-fg-muted/70 focus:border-accent disabled:bg-raise disabled:text-fg-muted ${className}`}
        {...rest}
      />
      {hint && (
        <p id={hintId} className="type-data text-fg-muted">
          {hint}
        </p>
      )}
    </div>
  )
}
