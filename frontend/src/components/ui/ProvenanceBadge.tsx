import type { EvidenceSource } from "../../types"
import { formatSource } from "../../lib/format"
import { Badge } from "./Badge"

const TONE_BY_SOURCE: Record<EvidenceSource, "sky" | "lilac" | "blush"> = {
  jobspec: "sky",
  onet: "lilac",
  both: "blush",
}

export function ProvenanceBadge({ source }: { source: EvidenceSource }) {
  return <Badge tone={TONE_BY_SOURCE[source]}>{formatSource(source)}</Badge>
}
