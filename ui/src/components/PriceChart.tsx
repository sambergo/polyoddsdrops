import type { PricePoint } from '../types'

interface PriceChartProps {
  points: PricePoint[]
}

export function PriceChart({ points }: PriceChartProps) {
  if (points.length < 2) {
    return <div className="price-chart-empty">Collecting data…</div>
  }

  const width = 400
  const height = 60
  const pad = 4

  const prices = points.map((p) => p.price)
  const minP = Math.min(...prices)
  const maxP = Math.max(...prices)
  const range = maxP - minP || 0.0001

  const innerW = width - pad * 2
  const innerH = height - pad * 2

  const coords = points.map((p, i) => {
    const x = pad + (i / (points.length - 1)) * innerW
    const y = pad + innerH - ((p.price - minP) / range) * innerH
    return [x, y] as const
  })

  const pathD = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ')

  const last = coords[coords.length - 1]
  const trending = points[points.length - 1].price >= points[0].price

  const color = trending ? 'var(--positive)' : 'var(--negative)'

  // Time span label
  const elapsed = points[points.length - 1].timestamp - points[0].timestamp
  const secs = Math.round(elapsed / 1000)
  const timeLabel = secs >= 60 ? `${Math.floor(secs / 60)}m ${secs % 60}s` : `${secs}s`

  return (
    <div className="price-chart">
      <svg viewBox={`0 0 ${width} ${height}`} className="price-chart-svg">
        <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
        <circle cx={last[0]} cy={last[1]} r="2.5" fill={color} />
      </svg>
      <div className="price-chart-labels">
        <span>{maxP.toFixed(4)}</span>
        <span className="price-chart-time">{points.length} pts / {timeLabel}</span>
        <span>{minP.toFixed(4)}</span>
      </div>
    </div>
  )
}
