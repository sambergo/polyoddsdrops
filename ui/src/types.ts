export interface PricePoint {
  price: number
  timestamp: number
}

/** Raw token data from Redis (all fields are strings). */
export interface TokenRaw {
  token_id: string
  condition_id: string
  question: string
  outcome: string
  event_title: string
  event_slug: string
  sport: string
  league_label: string
  sport_label: string
  market_type: string
  line: string
  liquidity: string
  spread: string
  volume_24h: string
  mid_price: string
  best_bid: string
  best_ask: string
  oldest_price: string
  newest_price: string
  price_change: string
  pct_change: string
  elapsed_seconds: string
  observation_count: string
  game_start_time: string
  is_subscribed: string
  is_active: string
  priority: string
  first_seen: string
  updated_at: string
}

/** Parsed token with numeric fields. */
export interface Token {
  token_id: string
  condition_id: string
  question: string
  outcome: string
  event_title: string
  event_slug: string
  sport: string
  league_label: string
  sport_label: string
  market_type: string
  line: number | null
  liquidity: number | null
  spread: number | null
  volume_24h: number | null
  mid_price: number | null
  best_bid: number | null
  best_ask: number | null
  oldest_price: number | null
  newest_price: number | null
  price_change: number | null
  pct_change: number | null
  elapsed_seconds: number | null
  observation_count: number | null
  game_start_time: string
  is_subscribed: boolean
  is_active: boolean
  priority: number
  first_seen: number
  updated_at: number
}

function num(v: string | undefined): number | null {
  if (!v || v === '') return null
  const n = Number(v)
  return isNaN(n) ? null : n
}

export function parseToken(raw: TokenRaw): Token {
  return {
    token_id: raw.token_id,
    condition_id: raw.condition_id || '',
    question: raw.question || '',
    outcome: raw.outcome || '',
    event_title: raw.event_title || '',
    event_slug: raw.event_slug || '',
    sport: raw.sport || '',
    league_label: raw.league_label || '',
    sport_label: raw.sport_label || '',
    market_type: raw.market_type || '',
    line: num(raw.line),
    liquidity: num(raw.liquidity),
    spread: num(raw.spread),
    volume_24h: num(raw.volume_24h),
    mid_price: num(raw.mid_price),
    best_bid: num(raw.best_bid),
    best_ask: num(raw.best_ask),
    oldest_price: num(raw.oldest_price),
    newest_price: num(raw.newest_price),
    price_change: num(raw.price_change),
    pct_change: num(raw.pct_change),
    elapsed_seconds: num(raw.elapsed_seconds),
    observation_count: num(raw.observation_count),
    game_start_time: raw.game_start_time || '',
    is_subscribed: raw.is_subscribed === '1',
    is_active: raw.is_active === '1',
    priority: Number(raw.priority) || 0,
    first_seen: Number(raw.first_seen) || 0,
    updated_at: Number(raw.updated_at) || 0,
  }
}
