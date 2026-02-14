import { useRef } from 'react'
import type { Token, PricePoint } from '../types'

const MAX_POINTS = 300

export function usePriceHistory(tokens: Token[]): Map<string, PricePoint[]> {
  const historyRef = useRef<Map<string, PricePoint[]>>(new Map())
  const lastUpdated = useRef<Map<string, number>>(new Map())

  const now = Date.now()

  for (const t of tokens) {
    if (t.mid_price == null) continue
    const prev = lastUpdated.current.get(t.token_id)
    if (prev === t.updated_at) continue

    lastUpdated.current.set(t.token_id, t.updated_at)

    let points = historyRef.current.get(t.token_id)
    if (!points) {
      points = []
      historyRef.current.set(t.token_id, points)
    }
    points.push({ price: t.mid_price, timestamp: now })
    if (points.length > MAX_POINTS) {
      points.splice(0, points.length - MAX_POINTS)
    }
  }

  // Clean up tokens no longer in the stream
  const currentIds = new Set(tokens.map((t) => t.token_id))
  for (const id of historyRef.current.keys()) {
    if (!currentIds.has(id)) {
      historyRef.current.delete(id)
      lastUpdated.current.delete(id)
    }
  }

  return historyRef.current
}
