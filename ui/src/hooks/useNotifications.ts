import { useCallback, useEffect, useState } from 'react'
import type { Token } from '../types'

const STORAGE_KEY = 'polydrop-notifications'

interface NotificationSettings {
  enabled: boolean
  threshold: number
  soundEnabled: boolean
}

interface NotificationState extends NotificationSettings {
  permission: NotificationPermission
  setEnabled: (v: boolean) => void
  setThreshold: (v: number) => void
  setSoundEnabled: (v: boolean) => void
  requestPermission: () => Promise<void>
  notify: (token: Token) => void
}

function loadSettings(): NotificationSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        enabled: Boolean(parsed.enabled),
        threshold: typeof parsed.threshold === 'number' ? parsed.threshold : 7,
        soundEnabled: Boolean(parsed.soundEnabled),
      }
    }
  } catch { /* ignore */ }
  return { enabled: false, threshold: 7, soundEnabled: true }
}

function saveSettings(s: NotificationSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}

export function useNotifications(): NotificationState {
  const [settings, setSettings] = useState<NotificationSettings>(loadSettings)
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== 'undefined' ? Notification.permission : 'default',
  )

  useEffect(() => {
    saveSettings(settings)
  }, [settings])

  const setEnabled = useCallback((v: boolean) => {
    setSettings((s) => ({ ...s, enabled: v }))
  }, [])

  const setThreshold = useCallback((v: number) => {
    setSettings((s) => ({ ...s, threshold: v }))
  }, [])

  const setSoundEnabled = useCallback((v: boolean) => {
    setSettings((s) => ({ ...s, soundEnabled: v }))
  }, [])

  const requestPermission = useCallback(async () => {
    if (typeof Notification === 'undefined') return
    const result = await Notification.requestPermission()
    setPermission(result)
  }, [])

  const notify = useCallback((token: Token) => {
    if (!settings.enabled || permission !== 'granted') return
    if (typeof Notification === 'undefined') return
    const pct = token.pct_change ?? 0
    const sign = pct >= 0 ? '+' : ''
    new Notification(`${token.outcome} ${sign}${pct.toFixed(1)}%`, {
      body: `${token.event_title}\n${token.mid_price?.toFixed(2) ?? '—'}¢`,
      tag: token.token_id,
    })
  }, [settings.enabled, permission])

  return {
    enabled: settings.enabled,
    threshold: settings.threshold,
    soundEnabled: settings.soundEnabled,
    permission,
    setEnabled,
    setThreshold,
    setSoundEnabled,
    requestPermission,
    notify,
  }
}
