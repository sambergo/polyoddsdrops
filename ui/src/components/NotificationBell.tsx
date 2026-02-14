import { useEffect, useRef, useState } from 'react'

interface NotificationBellProps {
  enabled: boolean
  threshold: number
  soundEnabled: boolean
  permission: NotificationPermission
  onEnabledChange: (v: boolean) => void
  onThresholdChange: (v: number) => void
  onSoundEnabledChange: (v: boolean) => void
  onRequestPermission: () => void
}

export function NotificationBell({
  enabled,
  threshold,
  soundEnabled,
  permission,
  onEnabledChange,
  onThresholdChange,
  onSoundEnabledChange,
  onRequestPermission,
}: NotificationBellProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  return (
    <div className="notification-bell-wrapper" ref={ref}>
      <button
        className={`notification-bell ${enabled ? 'notification-bell-active' : ''}`}
        onClick={() => setOpen(!open)}
        title="Notification settings"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 13a2 2 0 0 0 4 0" />
          <path d="M13 6c0-2.8-2.2-5-5-5S3 3.2 3 6c0 4-1.5 5-1.5 5h13S13 10 13 6z" />
        </svg>
      </button>
      {open && (
        <div className="notification-panel">
          <div className="notification-panel-header">
            <span>Notifications</span>
            <button className="notification-panel-close" onClick={() => setOpen(false)}>&times;</button>
          </div>
          <label className="filter-toggle">
            <input type="checkbox" checked={enabled} onChange={(e) => onEnabledChange(e.target.checked)} />
            Enable
          </label>
          <div className="filter-slider-group">
            <span className="filter-slider-label">Threshold</span>
            <input
              type="range"
              className="filter-range"
              min={1}
              max={20}
              step={1}
              value={threshold}
              onChange={(e) => onThresholdChange(Number(e.target.value))}
            />
            <span className="filter-range-value">{threshold}%</span>
          </div>
          <label className="filter-toggle">
            <input type="checkbox" checked={soundEnabled} onChange={(e) => onSoundEnabledChange(e.target.checked)} />
            Sound
          </label>
          {permission === 'default' && (
            <button className="notification-permission-btn" onClick={onRequestPermission}>
              Request permission
            </button>
          )}
          {permission === 'denied' && (
            <span className="notification-denied">Notifications blocked by browser</span>
          )}
        </div>
      )}
    </div>
  )
}
