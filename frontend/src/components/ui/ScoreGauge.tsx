interface ScoreGaugeProps {
  score: number | null
  size?: number
}

function toneForScore(score: number): { ring: string; text: string } {
  if (score >= 0.75) return { ring: "#2f8f6a", text: "text-success" }
  if (score >= 0.5) return { ring: "#b8863a", text: "text-warning" }
  return { ring: "#c1543f", text: "text-danger" }
}

export function ScoreGauge({ score, size = 96 }: ScoreGaugeProps) {
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const pct = score ?? 0
  const dash = circumference * pct
  const tone = score === null ? { ring: "#c8c3d4", text: "text-ink-muted" } : toneForScore(score)

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#ede9df"
          strokeWidth={8}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone.ring}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          className="transition-all duration-500 ease-out"
        />
      </svg>
      <div className={`absolute inset-0 flex items-center justify-center text-lg font-semibold ${tone.text}`}>
        {score === null ? "N/A" : `${Math.round(score * 100)}%`}
      </div>
    </div>
  )
}
