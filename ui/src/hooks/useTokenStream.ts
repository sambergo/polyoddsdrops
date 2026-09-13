import { useCallback, useEffect, useRef, useState } from 'react'
import type { Token, TokenRaw } from '../types'
import { parseToken } from '../types'

const NEW_HIGHLIGHT_MS = 120_000

interface TokenStreamState {
  tokens: Token[]
  connected: boolean
  error: string | null
  /** Set of token_ids that changed in the last update */
  changedIds: Set<string>
  /** Set of token_ids that became drops (crossed threshold) within the last 120s */
  newIds: Set<string>
}

function hasMetadata(token: Partial<TokenRaw>): boolean {
  return Boolean(token.question && token.event_title && token.outcome)
}

function mergeSnapshotWithNewerPrices(
  snapshot: TokenRaw,
  current: TokenRaw,
): TokenRaw {
  if (Number(current.updated_at) < Number(snapshot.updated_at)) return snapshot
  return {
    ...snapshot,
    mid_price: current.mid_price,
    best_bid: current.best_bid,
    best_ask: current.best_ask,
    spread: current.spread,
    oldest_price: current.oldest_price,
    newest_price: current.newest_price,
    price_change: current.price_change,
    pct_change: current.pct_change,
    elapsed_seconds: current.elapsed_seconds,
    observation_count: current.observation_count,
    updated_at: current.updated_at,
  }
}

export function useTokenStream(dropThreshold: number): TokenStreamState {
  const [tokens, setTokens] = useState<Token[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [changedIds, setChangedIds] = useState<Set<string>>(new Set())
  const [newIds, setNewIds] = useState<Set<string>>(new Set())
  const prevMap = useRef<Map<string, string>>(new Map())
  const prevPctChange = useRef<Map<string, number>>(new Map())
  const newDropIds = useRef<Map<string, number>>(new Map())
  const thresholdRef = useRef(dropThreshold)

  useEffect(() => {
    thresholdRef.current = dropThreshold
  }, [dropThreshold])

  const computeNewIds = useCallback(() => {
    const now = Date.now()
    for (const [id, ts] of newDropIds.current) {
      if (now - ts >= NEW_HIGHLIGHT_MS) newDropIds.current.delete(id)
    }
    setNewIds(new Set(newDropIds.current.keys()))
  }, [])

  const processTokens = useCallback((rawTokens: TokenRaw[], isInitial: boolean) => {
    const parsed = rawTokens.map(parseToken)
    const changed = new Set<string>()
    const threshold = thresholdRef.current

    for (const t of parsed) {
      const prevUpdated = prevMap.current.get(t.token_id)
      const curUpdated = String(t.updated_at)
      if (prevUpdated !== curUpdated) {
        changed.add(t.token_id)
      }
      prevMap.current.set(t.token_id, curUpdated)

      // Drop detection: pct_change > 0 means price dropped
      const currentPct = t.pct_change ?? 0
      const prevPct = prevPctChange.current.get(t.token_id)

      if (!isInitial) {
        const wasBelow = prevPct === undefined || prevPct <= 0 || prevPct < threshold
        const isDrop = currentPct > 0 && currentPct >= threshold
        if (isDrop && wasBelow) {
          newDropIds.current.set(t.token_id, Date.now())
        }
      }

      prevPctChange.current.set(t.token_id, currentPct)
    }

    // Remove stale entries
    const currentIds = new Set(parsed.map((t) => t.token_id))
    for (const id of prevMap.current.keys()) {
      if (!currentIds.has(id)) prevMap.current.delete(id)
    }
    for (const id of prevPctChange.current.keys()) {
      if (!currentIds.has(id)) prevPctChange.current.delete(id)
    }

    setTokens(parsed)
    setChangedIds(changed)
    computeNewIds()
  }, [computeNewIds])

  // Periodically expire drop highlights
  useEffect(() => {
    const id = setInterval(computeNewIds, 10_000)
    return () => clearInterval(id)
  }, [computeNewIds])

  // Ref to hold the latest full token map for merging deltas
  const tokenMapRef = useRef<Map<string, TokenRaw>>(new Map())
  const snapshotRefreshRef = useRef<Promise<void> | null>(null)
  const lastSnapshotRefreshRef = useRef(0)

  const refreshSnapshot = useCallback(() => {
    const now = Date.now()
    if (snapshotRefreshRef.current || now - lastSnapshotRefreshRef.current < 5000) {
      return
    }
    lastSnapshotRefreshRef.current = now
    snapshotRefreshRef.current = fetch('/api/tokens')
      .then((response) => {
        if (!response.ok) throw new Error(`Snapshot request failed: ${response.status}`)
        return response.json() as Promise<TokenRaw[]>
      })
      .then((snapshot) => {
        const merged = new Map(snapshot.map((token) => [token.token_id, token]))
        for (const [tokenId, current] of tokenMapRef.current) {
          const fromSnapshot = merged.get(tokenId)
          if (!fromSnapshot) merged.set(tokenId, current)
          else merged.set(tokenId, mergeSnapshotWithNewerPrices(fromSnapshot, current))
        }
        tokenMapRef.current = merged
        processTokens(Array.from(merged.values()), true)
      })
      .catch(() => {
        // A later delta retries after the short cooldown.
      })
      .finally(() => {
        snapshotRefreshRef.current = null
      })
  }, [processTokens])

  const applyDelta = useCallback((delta: { updated?: (Partial<TokenRaw> & Pick<TokenRaw, 'token_id'>)[]; removed?: string[] }) => {
    const map = tokenMapRef.current
    let needsSnapshotRefresh = false
    if (delta.updated) {
      for (const t of delta.updated) {
        const existing = map.get(t.token_id)
        if ((!existing || !hasMetadata(existing)) && !hasMetadata(t)) {
          needsSnapshotRefresh = true
          if (!existing) continue
        }
        if (!existing) {
          map.set(t.token_id, t as TokenRaw)
          continue
        }
        if (
          t.updated_at !== undefined &&
          Number(t.updated_at) < Number(existing.updated_at)
        ) {
          continue
        }
        map.set(t.token_id, { ...existing, ...t })
      }
    }
    if (delta.removed) {
      for (const id of delta.removed) {
        map.delete(id)
      }
    }
    processTokens(Array.from(map.values()), false)
    if (needsSnapshotRefresh) refreshSnapshot()
  }, [processTokens, refreshSnapshot])

  useEffect(() => {
    let es: EventSource | null = null
    let retryTimeout: ReturnType<typeof setTimeout> | null = null
    let errorBannerTimeout: ReturnType<typeof setTimeout> | null = null

    function clearErrorBannerTimeout() {
      if (errorBannerTimeout) {
        clearTimeout(errorBannerTimeout)
        errorBannerTimeout = null
      }
    }

    function connect() {
      es = new EventSource('/api/tokens/stream')

      // Full state on first SSE message
      es.addEventListener('tokens', (e) => {
        try {
          const data = JSON.parse(e.data) as TokenRaw[]
          tokenMapRef.current = new Map(data.map((t) => [t.token_id, t]))
          processTokens(data, true)
          if (data.some((token) => !hasMetadata(token))) refreshSnapshot()
          clearErrorBannerTimeout()
          setConnected(true)
          setError(null)
        } catch {
          setError('Failed to parse SSE data')
        }
      })

      // Delta updates (only changed/removed tokens)
      es.addEventListener('delta', (e) => {
        try {
          const delta = JSON.parse(e.data) as {
            updated?: (Partial<TokenRaw> & Pick<TokenRaw, 'token_id'>)[]
            removed?: string[]
          }
          applyDelta(delta)
          clearErrorBannerTimeout()
          setConnected(true)
          setError(null)
        } catch {
          setError('Failed to parse SSE delta')
        }
      })

      es.addEventListener('error', () => {
        setConnected(false)
        // Only show error banner after 8s grace period — transient network
        // changes (ERR_NETWORK_CHANGED) reconnect quickly and shouldn't flash UI
        errorBannerTimeout = setTimeout(() => {
          setError('Connection lost, retrying...')
        }, 8000)
        es?.close()
        retryTimeout = setTimeout(connect, 3000)
      })
    }

    // The SSE endpoint sends one full snapshot followed by delta batches.
    connect()

    return () => {
      es?.close()
      if (retryTimeout) clearTimeout(retryTimeout)
      clearErrorBannerTimeout()
    }
  }, [processTokens, applyDelta, refreshSnapshot])

  return { tokens, connected, error, changedIds, newIds }
}
