import type { OccupationMatch } from "../../types"
import { Card } from "../ui/Card"
import { Badge } from "../ui/Badge"

interface OccupationMatchCardProps {
  match: OccupationMatch
  alternates: OccupationMatch[]
}

export function OccupationMatchCard({ match, alternates }: OccupationMatchCardProps) {
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Matched O*NET Occupation
        </h3>
        <Badge tone="lilac">{Math.round(match.score * 100)}% match</Badge>
      </div>
      <div>
        <p className="text-lg font-semibold text-ink">{match.title}</p>
        <p className="text-xs text-ink-muted">SOC {match.onet_soc_code}</p>
      </div>

      {alternates.length > 0 && (
        <div className="border-t border-ivory-200 pt-3">
          <p className="mb-2 text-xs font-medium text-ink-muted">Other candidates considered</p>
          <ul className="flex flex-col gap-1.5">
            {alternates.map((alt) => (
              <li
                key={alt.onet_soc_code}
                className="flex items-center justify-between text-sm text-ink-soft"
              >
                <span>{alt.title}</span>
                <span className="text-xs text-ink-muted">{Math.round(alt.score * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
