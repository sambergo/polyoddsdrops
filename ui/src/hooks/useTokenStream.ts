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

  thresholdRef.current = dropThreshold

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

  const applyDelta = useCallback((delta: { updated?: TokenRaw[]; removed?: string[] }) => {
    const map = tokenMapRef.current
    if (delta.updated) {
      for (const t of delta.updated) {
        map.set(t.token_id, t)
      }
    }
    if (delta.removed) {
      for (const id of delta.removed) {
        map.delete(id)
      }
    }
    processTokens(Array.from(map.values()), false)
  }, [processTokens])

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
          processTokens(data, false)
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
          const delta = JSON.parse(e.data) as { updated?: TokenRaw[]; removed?: string[] }
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

    // Initial fetch then connect SSE
    fetch('/api/tokens')
      .then((r) => r.json())
      .then((data: TokenRaw[]) => {
        tokenMapRef.current = new Map(data.map((t) => [t.token_id, t]))
        processTokens(data, true)
        connect()
      })
      .catch(() => {
        setError('Failed to load initial data, retrying...')
        retryTimeout = setTimeout(connect, 3000)
      })

    return () => {
      es?.close()
      if (retryTimeout) clearTimeout(retryTimeout)
      clearErrorBannerTimeout()
    }
  }, [processTokens, applyDelta])

  return { tokens, connected, error, changedIds, newIds }
}
