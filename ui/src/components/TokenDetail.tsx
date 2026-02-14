import { useState } from 'react'
import type { Token, PricePoint } from '../types'
import { PriceChart } from './PriceChart'

interface TokenDetailProps {
  token: Token
  priceHistory: PricePoint[]
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function polymarketUrl(slug: string): string {
  if (!slug) return ''
  return `https://polymarket.com/event/${slug}`
}

function CopyId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const truncated = value.length > 16 ? value.slice(0, 16) + '…' : value

  function handleCopy() {
    navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <span className="copy-id">
      <span className="mono">{truncated}</span>
      <button className="copy-btn" onClick={handleCopy} title="Copy to clipboard">
        {copied ? '✓' : '⧉'}
      </button>
    </span>
  )
}

export function TokenDetail({ token, priceHistory }: TokenDetailProps) {
  const url = polymarketUrl(token.event_slug)

  return (
    <div className="token-detail">
      <div className="detail-question">{token.question || '—'}</div>
      <div className="detail-grid">
        <div className="detail-section">
          <h4>Identity</h4>
          <dl>
            <dt>Token ID</dt>
            <dd><CopyId value={token.token_id} /></dd>
            <dt>Condition ID</dt>
            <dd>{token.condition_id ? <CopyId value={token.condition_id} /> : '—'}</dd>
          </dl>
        </div>

        <div className="detail-section">
          <h4>Classification</h4>
          <dl>
            <dt>Sport</dt>
            <dd>{token.sport_label || token.sport || '—'}</dd>
            <dt>League</dt>
            <dd>{token.league_label || '—'}</dd>
            <dt>Market Type</dt>
            <dd>
              {token.market_type || '—'}
              {token.line != null ? ` (${token.line})` : ''}
            </dd>
          </dl>
        </div>

        <div className="detail-section">
          <h4>Pricing</h4>
          <dl>
            <dt>Mid Price</dt>
            <dd>{token.mid_price?.toFixed(4) ?? '—'}</dd>
            <dt>Best Bid</dt>
            <dd>{token.best_bid?.toFixed(4) ?? '—'}</dd>
            <dt>Best Ask</dt>
            <dd>{token.best_ask?.toFixed(4) ?? '—'}</dd>
            <dt>Spread</dt>
            <dd>{token.spread?.toFixed(4) ?? '—'}</dd>
          </dl>
        </div>

        <div className="detail-section">
          <h4>Velocity</h4>
          <dl>
            <dt>Oldest Price</dt>
            <dd>{token.oldest_price?.toFixed(4) ?? '—'}</dd>
            <dt>Newest Price</dt>
            <dd>{token.newest_price?.toFixed(4) ?? '—'}</dd>
            <dt>Price Change</dt>
            <dd>{token.price_change?.toFixed(4) ?? '—'}</dd>
            <dt>Pct Change</dt>
            <dd>{token.pct_change != null ? `${(token.pct_change * 100).toFixed(2)}%` : '—'}</dd>
            <dt>Window</dt>
            <dd>
              {token.elapsed_seconds?.toFixed(0) ?? '—'}s / {token.observation_count ?? '—'} obs
            </dd>
          </dl>
        </div>

        <div className="detail-section">
          <h4>Market Quality</h4>
          <dl>
            <dt>Liquidity</dt>
            <dd>{token.liquidity != null ? `$${token.liquidity.toLocaleString()}` : '—'}</dd>
            <dt>Volume 24h</dt>
            <dd>{token.volume_24h != null ? `$${token.volume_24h.toLocaleString()}` : '—'}</dd>
            <dt>Priority</dt>
            <dd>{token.priority}</dd>
          </dl>
        </div>

        <div className="detail-section">
          <h4>Timing</h4>
          <dl>
            <dt>Game Start</dt>
            <dd>{formatTime(token.game_start_time)}</dd>
            <dt>Last Updated</dt>
            <dd>{new Date(token.updated_at * 1000).toLocaleTimeString()}</dd>
          </dl>
        </div>
      </div>

      <div className="detail-section detail-section-wide">
        <h4>Price History</h4>
        <PriceChart points={priceHistory} />
      </div>

      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer" className="polymarket-link">
          View on Polymarket
        </a>
      )}
    </div>
  )
}
