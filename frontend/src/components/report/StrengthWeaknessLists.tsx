interface StrengthWeaknessListsProps {
  strengths: string[]
  weaknesses: string[]
}

export function StrengthWeaknessLists({ strengths, weaknesses }: StrengthWeaknessListsProps) {
  if (strengths.length === 0 && weaknesses.length === 0) return null

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div className="rounded-[14px] border border-success/20 bg-success/5 p-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-success">
          Strengths
        </h3>
        <ul className="flex flex-col gap-2">
          {strengths.map((item, i) => (
            <li key={i} className="flex gap-2 text-sm text-ink-soft">
              <span className="text-success">+</span>
              <span>{item}</span>
            </li>
          ))}
          {strengths.length === 0 && <li className="text-sm text-ink-muted">None noted.</li>}
        </ul>
      </div>
      <div className="rounded-[14px] border border-warning/20 bg-warning/5 p-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-warning">
          Areas to Explore
        </h3>
        <ul className="flex flex-col gap-2">
          {weaknesses.map((item, i) => (
            <li key={i} className="flex gap-2 text-sm text-ink-soft">
              <span className="text-warning">•</span>
              <span>{item}</span>
            </li>
          ))}
          {weaknesses.length === 0 && <li className="text-sm text-ink-muted">None noted.</li>}
        </ul>
      </div>
    </div>
  )
}
