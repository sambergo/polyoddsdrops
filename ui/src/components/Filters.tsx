import { useEffect, useMemo, useRef, useState } from 'react'
import type { Token } from '../types'

interface ChipDropdownProps {
  label: string
  options: string[]
  excluded: Set<string>
  onChange: (excluded: Set<string>) => void
}

function ChipDropdown({ label, options, excluded, onChange }: ChipDropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const allSelected = excluded.size === 0
  const selectedCount = options.length - excluded.size

  useEffect(() => {
    if (!open) return
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  function toggleAll() {
    if (allSelected) return
    onChange(new Set())
  }

  function toggle(value: string) {
    const next = new Set(excluded)
    if (next.has(value)) {
      next.delete(value)
    } else {
      if (options.length - next.size <= 1) return
      next.add(value)
    }
    onChange(next)
  }

  if (options.length === 0) return null

  const summary = allSelected ? 'All' : `${selectedCount}/${options.length}`

  return (
    <div className="chip-dropdown" ref={ref}>
      <button
        className={`chip-dropdown-trigger ${!allSelected ? 'chip-dropdown-filtered' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <span className="chip-dropdown-label">{label}</span>
        <span className="chip-dropdown-value">{summary}</span>
        <span className="chip-dropdown-arrow">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="chip-dropdown-panel">
          <button
            className={`chip ${allSelected ? 'chip-active' : ''}`}
            onClick={toggleAll}
          >
            All
          </button>
          {options.map((opt) => (
            <button
              key={opt}
              className={`chip ${!excluded.has(opt) ? 'chip-active' : ''}`}
              onClick={() => toggle(opt)}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface FiltersProps {
  tokens: Token[]
  excludedSports: Set<string>
  onExcludedSportsChange: (v: Set<string>) => void
  excludedLeagues: Set<string>
  onExcludedLeaguesChange: (v: Set<string>) => void
  excludedMarketTypes: Set<string>
  onExcludedMarketTypesChange: (v: Set<string>) => void
  moversOnly: boolean
  onMoversOnlyChange: (v: boolean) => void
  threshold: number
  onThresholdChange: (v: number) => void
  showAdvanced: boolean
  onShowAdvancedChange: (v: boolean) => void
  minLiquidity: number
  onMinLiquidityChange: (v: number) => void
  maxSpread: number
  onMaxSpreadChange: (v: number) => void
  minVolume: number
  onMinVolumeChange: (v: number) => void
  minOdds: number
  onMinOddsChange: (v: number) => void
  maxOdds: number
  onMaxOddsChange: (v: number) => void
  showLive: boolean
  onShowLiveChange: (v: boolean) => void
  showHidden: boolean
  onShowHiddenChange: (v: boolean) => void
  hiddenCount: number
  onReset: () => void
}

function formatDollars(v: number): string {
  if (v >= 1000) return `$${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}K`
  return `$${v}`
}

export function Filters({
  tokens,
  excludedSports,
  onExcludedSportsChange,
  excludedLeagues,
  onExcludedLeaguesChange,
  excludedMarketTypes,
  onExcludedMarketTypesChange,
  moversOnly,
  onMoversOnlyChange,
  threshold,
  onThresholdChange,
  showAdvanced,
  onShowAdvancedChange,
  minLiquidity,
  onMinLiquidityChange,
  maxSpread,
  onMaxSpreadChange,
  minVolume,
  onMinVolumeChange,
  minOdds,
  onMinOddsChange,
  maxOdds,
  onMaxOddsChange,
  showLive,
  onShowLiveChange,
  showHidden,
  onShowHiddenChange,
  hiddenCount,
  onReset,
}: FiltersProps) {
  const sports = useMemo(
    () => [...new Set(tokens.map((t) => t.sport_label).filter(Boolean))].sort(),
    [tokens],
  )
  const leagues = useMemo(
    () => [...new Set(tokens.map((t) => t.league_label).filter(Boolean))].sort(),
    [tokens],
  )
  const marketTypes = useMemo(
    () => [...new Set(tokens.map((t) => t.market_type).filter(Boolean))].sort(),
    [tokens],
  )

  return (
    <div className="filters-container">
      <div className="filters">
        <ChipDropdown
          label="Sport"
          options={sports}
          excluded={excludedSports}
          onChange={onExcludedSportsChange}
        />
        <ChipDropdown
          label="League"
          options={leagues}
          excluded={excludedLeagues}
          onChange={onExcludedLeaguesChange}
        />
        <ChipDropdown
          label="Market"
          options={marketTypes}
          excluded={excludedMarketTypes}
          onChange={onExcludedMarketTypesChange}
        />

        <div className="filter-separator" />

        <label className="filter-toggle">
          <input
            type="checkbox"
            checked={moversOnly}
            onChange={(e) => onMoversOnlyChange(e.target.checked)}
          />
          <span>Drops only</span>
        </label>

        {moversOnly && (
          <div className="filter-slider-group">
            <input
              type="range"
              min={1}
              max={15}
              step={0.5}
              value={threshold}
              onChange={(e) => onThresholdChange(Number(e.target.value))}
              className="filter-range"
            />
            <span className="filter-range-value">{threshold}%</span>
          </div>
        )}

        <button
          className="filter-advanced-toggle"
          onClick={() => onShowAdvancedChange(!showAdvanced)}
        >
          {showAdvanced ? '▾' : '▸'} More filters
        </button>
      </div>

      {showAdvanced && (
        <div className="filters filters-advanced">
          <label className="filter-toggle">
            <input
              type="checkbox"
              checked={showLive}
              onChange={(e) => onShowLiveChange(e.target.checked)}
            />
            <span>Show live</span>
          </label>

          {hiddenCount > 0 && (
            <label className="filter-toggle">
              <input
                type="checkbox"
                checked={showHidden}
                onChange={(e) => onShowHiddenChange(e.target.checked)}
              />
              <span>Show hidden ({hiddenCount})</span>
            </label>
          )}

          <div className="filter-slider-group">
            <label className="filter-slider-label">Min liquidity</label>
            <input
              type="range"
              min={0}
              max={100000}
              step={1000}
              value={minLiquidity}
              onChange={(e) => onMinLiquidityChange(Number(e.target.value))}
              className="filter-range"
            />
            <span className="filter-range-value">{formatDollars(minLiquidity)}</span>
          </div>

          <div className="filter-slider-group">
            <label className="filter-slider-label">Max spread</label>
            <input
              type="range"
              min={0.01}
              max={0.50}
              step={0.01}
              value={maxSpread}
              onChange={(e) => onMaxSpreadChange(Number(e.target.value))}
              className="filter-range"
            />
            <span className="filter-range-value">{maxSpread.toFixed(2)}</span>
          </div>

          <div className="filter-slider-group">
            <label className="filter-slider-label">Min volume 24h</label>
            <input
              type="range"
              min={0}
              max={10000}
              step={100}
              value={minVolume}
              onChange={(e) => onMinVolumeChange(Number(e.target.value))}
              className="filter-range"
            />
            <span className="filter-range-value">{formatDollars(minVolume)}</span>
          </div>

          <div className="filter-slider-group">
            <label className="filter-slider-label">Min odds</label>
            <input
              type="range"
              min={1.01}
              max={5.0}
              step={0.1}
              value={minOdds}
              onChange={(e) => onMinOddsChange(Number(e.target.value))}
              className="filter-range"
            />
            <span className="filter-range-value">{minOdds.toFixed(1)}</span>
          </div>

          <div className="filter-slider-group">
            <label className="filter-slider-label">Max odds</label>
            <input
              type="range"
              min={2.0}
              max={20.0}
              step={0.5}
              value={maxOdds}
              onChange={(e) => onMaxOddsChange(Number(e.target.value))}
              className="filter-range"
            />
            <span className="filter-range-value">{maxOdds.toFixed(1)}</span>
          </div>

          <button className="filter-reset-btn" onClick={onReset}>
            Reset to default
          </button>
        </div>
      )}
    </div>
  )
}
