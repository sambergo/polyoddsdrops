import { useEffect, useMemo, useRef, useState } from "react";
import { useTokenStream } from "./hooks/useTokenStream";
import { usePriceHistory } from "./hooks/usePriceHistory";
import { useNotifications } from "./hooks/useNotifications";
import { Layout } from "./components/Layout";
import { Filters } from "./components/Filters";
import { TokenTable } from "./components/TokenTable";
import { NotificationBell } from "./components/NotificationBell";
import type { Token } from "./types";

interface NumericFilters {
  moversOnly: boolean;
  threshold: number;
  minLiquidity: number;
  maxSpread: number;
  minVolume: number;
  minOdds: number;
  maxOdds: number;
}

function matchesFilter(
  token: Token,
  excludedSports: Set<string>,
  excludedLeagues: Set<string>,
  excludedMarketTypes: Set<string>,
  numeric: NumericFilters,
  showLive: boolean,
): boolean {
  if (excludedSports.size > 0 && excludedSports.has(token.sport_label))
    return false;
  if (excludedLeagues.size > 0 && excludedLeagues.has(token.league_label))
    return false;
  if (
    excludedMarketTypes.size > 0 &&
    excludedMarketTypes.has(token.market_type)
  )
    return false;
  if (numeric.moversOnly) {
    const pct = token.pct_change ?? 0;
    if (pct <= 0 || Math.abs(pct) < numeric.threshold) return false;
  }
  if (token.liquidity != null && token.liquidity < numeric.minLiquidity)
    return false;
  if (token.spread != null && token.spread > numeric.maxSpread) return false;
  if (token.volume_24h != null && token.volume_24h < numeric.minVolume)
    return false;
  if (token.mid_price != null && token.mid_price > 0) {
    const odds = 1 / token.mid_price;
    if (odds < numeric.minOdds || odds > numeric.maxOdds) return false;
  }
  if (!showLive && token.game_start_time) {
    const d = new Date(token.game_start_time);
    if (!isNaN(d.getTime()) && d.getTime() <= Date.now()) return false;
  }
  return true;
}

function playDropSound() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    gain.gain.value = 0.1;
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.stop(ctx.currentTime + 0.3);
  } catch {
    // AudioContext may not be available
  }
}

function loadHiddenIds(): Set<string> {
  try {
    const raw = localStorage.getItem("polydrop_hidden");
    if (raw) return new Set(JSON.parse(raw));
  } catch {
    /* ignore */
  }
  return new Set();
}

export default function App() {
  const notif = useNotifications();
  const [threshold, setThreshold] = useState(3);
  const { tokens, connected, error, changedIds, newIds } =
    useTokenStream(threshold);
  const priceHistory = usePriceHistory(tokens);
  const [excludedSports, setExcludedSports] = useState<Set<string>>(new Set());
  const [excludedLeagues, setExcludedLeagues] = useState<Set<string>>(
    new Set(),
  );
  const [excludedMarketTypes, setExcludedMarketTypes] = useState<Set<string>>(
    new Set(),
  );
  const [moversOnly, setMoversOnly] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [minLiquidity, setMinLiquidity] = useState(10000);
  const [maxSpread, setMaxSpread] = useState(0.03);
  const [minVolume, setMinVolume] = useState(0);
  const [minOdds, setMinOdds] = useState(1.1);
  const [maxOdds, setMaxOdds] = useState(6.0);
  const [showLive, setShowLive] = useState(false);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(loadHiddenIds);
  const [showHidden, setShowHidden] = useState(false);

  const numeric = useMemo<NumericFilters>(
    () => ({
      moversOnly,
      threshold,
      minLiquidity,
      maxSpread,
      minVolume,
      minOdds,
      maxOdds,
    }),
    [
      moversOnly,
      threshold,
      minLiquidity,
      maxSpread,
      minVolume,
      minOdds,
      maxOdds,
    ],
  );

  const toggleHidden = (tokenId: string) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      if (next.has(tokenId)) next.delete(tokenId);
      else next.add(tokenId);
      localStorage.setItem("polydrop_hidden", JSON.stringify([...next]));
      return next;
    });
  };

  const filtered = useMemo(
    () =>
      tokens.filter((t) => {
        if (!showHidden && hiddenIds.has(t.token_id)) return false;
        return matchesFilter(
          t,
          excludedSports,
          excludedLeagues,
          excludedMarketTypes,
          numeric,
          showLive,
        );
      }),
    [
      tokens,
      excludedSports,
      excludedLeagues,
      excludedMarketTypes,
      numeric,
      showLive,
      hiddenIds,
      showHidden,
    ],
  );

  // Fire browser notifications for new drops that pass category filters
  const prevNewIds = useRef<Set<string>>(new Set());
  const tokenMapRef = useRef<Map<string, Token>>(new Map());

  // Keep token map in sync
  useEffect(() => {
    const map = new Map<string, Token>();
    for (const t of tokens) map.set(t.token_id, t);
    tokenMapRef.current = map;
  }, [tokens]);

  useEffect(() => {
    if (!notif.enabled) return;
    const prev = prevNewIds.current;
    let fired = false;
    const notifNumeric: NumericFilters = {
      ...numeric,
      moversOnly: true,
      threshold: notif.threshold,
    };
    for (const id of newIds) {
      if (prev.has(id)) continue;
      const token = tokenMapRef.current.get(id);
      if (!token) continue;
      if (hiddenIds.has(token.token_id)) continue;
      if (
        !matchesFilter(
          token,
          excludedSports,
          excludedLeagues,
          excludedMarketTypes,
          notifNumeric,
          showLive,
        )
      )
        continue;
      notif.notify(token);
      fired = true;
    }
    if (fired && notif.soundEnabled) playDropSound();
    prevNewIds.current = new Set(newIds);
  }, [
    newIds,
    notif,
    excludedSports,
    excludedLeagues,
    excludedMarketTypes,
    numeric,
    showLive,
    hiddenIds,
  ]);

  const bell = (
    <NotificationBell
      enabled={notif.enabled}
      threshold={notif.threshold}
      soundEnabled={notif.soundEnabled}
      permission={notif.permission}
      onEnabledChange={notif.setEnabled}
      onThresholdChange={notif.setThreshold}
      onSoundEnabledChange={notif.setSoundEnabled}
      onRequestPermission={notif.requestPermission}
    />
  );

  return (
    <Layout
      connected={connected}
      error={error}
      tokenCount={filtered.length}
      notificationBell={bell}
    >
      <Filters
        tokens={tokens}
        excludedSports={excludedSports}
        onExcludedSportsChange={setExcludedSports}
        excludedLeagues={excludedLeagues}
        onExcludedLeaguesChange={setExcludedLeagues}
        excludedMarketTypes={excludedMarketTypes}
        onExcludedMarketTypesChange={setExcludedMarketTypes}
        moversOnly={moversOnly}
        onMoversOnlyChange={setMoversOnly}
        threshold={threshold}
        onThresholdChange={setThreshold}
        showAdvanced={showAdvanced}
        onShowAdvancedChange={setShowAdvanced}
        minLiquidity={minLiquidity}
        onMinLiquidityChange={setMinLiquidity}
        maxSpread={maxSpread}
        onMaxSpreadChange={setMaxSpread}
        minVolume={minVolume}
        onMinVolumeChange={setMinVolume}
        minOdds={minOdds}
        onMinOddsChange={setMinOdds}
        maxOdds={maxOdds}
        onMaxOddsChange={setMaxOdds}
        showLive={showLive}
        onShowLiveChange={setShowLive}
        showHidden={showHidden}
        onShowHiddenChange={setShowHidden}
        hiddenCount={hiddenIds.size}
      />
      <TokenTable
        tokens={filtered}
        changedIds={changedIds}
        newIds={newIds}
        priceHistory={priceHistory}
        hiddenIds={hiddenIds}
        onToggleHidden={toggleHidden}
      />
    </Layout>
  );
}
