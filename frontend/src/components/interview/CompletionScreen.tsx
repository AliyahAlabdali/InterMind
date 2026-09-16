import { Card } from "../ui/Card"

export function CompletionScreen() {
  return (
    <Card className="flex flex-col items-center gap-4 py-14 text-center animate-enter">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-periwinkle to-lavender text-2xl text-white">
        ✓
      </span>
      <div>
        <h2 className="text-xl font-semibold text-ink" style={{ fontFamily: "var(--font-display)" }}>
          Interview complete
        </h2>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-soft">
          Thank you for completing your technical interview. Your responses have been submitted
          to the hiring team.
        </p>
      </div>
    </Card>
  )
}
