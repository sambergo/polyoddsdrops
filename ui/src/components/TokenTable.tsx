import { useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { SortingState } from "@tanstack/react-table";
import type { Token, PricePoint } from "../types";
import { TokenDetail } from "./TokenDetail";

const col = createColumnHelper<Token>();

function formatRelativeTime(unixSeconds: number): string {
  if (!unixSeconds) return "—";
  const diff = Date.now() - unixSeconds * 1000;
  if (diff < 0) return "—";
  const sec = Math.floor(diff / 5000) * 5;
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return `${min}m ${remSec}s`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  if (hr < 24) return `${hr}h ${remMin}m`;
  const days = Math.floor(hr / 24);
  return `${days}d ${hr % 24}h`;
}

function formatRelativeTimeMs(timestampMs: number): string {
  const diff = Date.now() - timestampMs;
  if (diff < 0) return "—";
  const sec = Math.floor(diff / 5000) * 5;
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return `${min}m ${remSec}s`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  if (hr < 24) return `${hr}h ${remMin}m`;
  const days = Math.floor(hr / 24);
  return `${days}d ${hr % 24}h`;
}

function useTick(intervalMs: number) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return tick;
}

function formatCountdown(gameStart: string): string {
  if (!gameStart) return "—";
  const d = new Date(gameStart);
  if (isNaN(d.getTime())) return "—";
  const diff = d.getTime() - Date.now();
  if (diff <= 0) return "LIVE";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (h > 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return `${h}h ${m}m`;
}

function pctClass(v: number | null): string {
  if (v == null) return "";
  if (v > 0) return "positive";
  if (v < 0) return "negative";
  return "";
}

function toEuropeanOdds(price: number | null): number | null {
  if (price == null || price <= 0 || price >= 1) return null;
  return 1 / price;
}

function formatOdds(odds: number | null): string {
  if (odds == null) return "—";
  return odds.toFixed(2);
}

function oddsChange(
  oldest: number | null,
  current: number | null,
): number | null {
  const oldOdds = toEuropeanOdds(oldest);
  const curOdds = toEuropeanOdds(current);
  if (oldOdds == null || curOdds == null) return null;
  return (curOdds - oldOdds) / oldOdds;
}

const columns = [
  col.accessor("event_title", {
    header: "Event",
    cell: (info) => (
      <span className="cell-event">{info.getValue() || "—"}</span>
    ),
  }),
  col.accessor("outcome", {
    header: "Outcome",
    cell: (info) => {
      const { outcome, question } = info.row.original;
      let display = outcome;
      if (
        outcome.toLowerCase() === "yes" ||
        outcome.toLowerCase() === "no"
      ) {
        const q = question.replace(/\?$/, "").trim();
        const context = q.toLowerCase().startsWith("will ")
          ? q.slice(5)
          : q;
        if (context) display = context;
      }
      return (
        <span className="cell-outcome">
          {display}
          <button
            className="copy-btn"
            title="Copy to clipboard"
            onClick={(e) => {
              e.stopPropagation();
              navigator.clipboard.writeText(display);
            }}
          >
            📋
          </button>
        </span>
      );
    },
  }),
  col.accessor("league_label", { header: "League" }),
  col.accessor(
    (row) =>
      `${row.market_type || "—"}${row.line != null ? ` ${row.line}` : ""}`,
    {
      id: "market",
      header: "Market",
    },
  ),
  col.accessor((row) => toEuropeanOdds(row.oldest_price) ?? 0, {
    id: "original_odds",
    header: "Original",
    cell: (info) => formatOdds(toEuropeanOdds(info.row.original.oldest_price)),
  }),
  col.accessor((row) => toEuropeanOdds(row.mid_price) ?? 0, {
    id: "current_odds",
    header: "Current",
    cell: (info) => formatOdds(toEuropeanOdds(info.row.original.mid_price)),
  }),
  col.accessor((row) => oddsChange(row.oldest_price, row.mid_price) ?? 0, {
    id: "odds_change",
    header: "Odds Chg",
    cell: (info) => {
      const row = info.row.original;
      const chg = oddsChange(row.oldest_price, row.mid_price);
      if (chg == null) return "—";
      const sign = chg > 0 ? "+" : "";
      return (
        <span className={pctClass(chg)}>
          {sign}
          {(chg * 100).toFixed(1)}%
        </span>
      );
    },
  }),
  col.accessor("first_seen", {
    id: "drop_seen",
    header: "Seen",
    cell: () => "—",
  }),
  col.accessor("updated_at", {
    header: "Updated",
    cell: (info) => formatRelativeTime(info.getValue()),
  }),
  col.accessor((row) => new Date(row.game_start_time).getTime() || Infinity, {
    id: "countdown",
    header: "Starting",
    cell: (info) => formatCountdown(info.row.original.game_start_time),
  }),
  col.display({
    id: "link",
    header: "",
    cell: (info) => {
      const slug = info.row.original.event_slug;
      if (!slug) return null;
      return (
        <a
          href={`https://polymarket.com/event/${slug}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          title="View on Polymarket"
        >
          ↗
        </a>
      );
    },
  }),
];

interface TokenTableProps {
  tokens: Token[];
  changedIds: Set<string>;
  newIds: Set<string>;
  priceHistory: Map<string, PricePoint[]>;
  hiddenIds: Set<string>;
  onToggleHidden: (tokenId: string) => void;
  dropSeenAt: Map<string, number>;
}

export function TokenTable({ tokens, changedIds, newIds, priceHistory, hiddenIds, onToggleHidden, dropSeenAt }: TokenTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "odds_change", desc: false },
  ]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const tick = useTick(5000);

  const data = useMemo(() => tokens, [tokens, tick]);

  const allColumns = useMemo(
    () => [
      col.display({
        id: "hide",
        header: "",
        cell: (info) => {
          const id = info.row.original.token_id;
          const isHidden = hiddenIds.has(id);
          return (
            <button
              className={`hide-btn ${isHidden ? "hide-btn-restore" : ""}`}
              title={isHidden ? "Unhide" : "Hide"}
              onClick={(e) => {
                e.stopPropagation();
                onToggleHidden(id);
              }}
            >
              {isHidden ? "↩" : "✕"}
            </button>
          );
        },
      }),
      ...columns.map((c) => {
        if (c.id === "drop_seen") {
          return col.accessor(
            (row) => dropSeenAt.get(row.token_id) ?? Infinity,
            {
              id: "drop_seen",
              header: "Seen",
              cell: (info) => {
                const ts = dropSeenAt.get(info.row.original.token_id);
                if (ts == null) return "—";
                return formatRelativeTimeMs(ts);
              },
            },
          );
        }
        return c;
      }),
    ],
    [hiddenIds, onToggleHidden, dropSeenAt],
  );

  const table = useReactTable({
    data,
    columns: allColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.token_id,
  });

  return (
    <div className="table-container">
      <table>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  onClick={header.column.getToggleSortingHandler()}
                  className={header.column.getCanSort() ? "sortable" : ""}
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                  {{ asc: " ▲", desc: " ▼" }[
                    header.column.getIsSorted() as string
                  ] ?? ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <>
              <tr
                key={row.id}
                onClick={() =>
                  setExpandedId(expandedId === row.id ? null : row.id)
                }
                className={[
                  changedIds.has(row.id) ? "flash" : "",
                  newIds.has(row.id) ? "new-row" : "",
                  expandedId === row.id ? "expanded" : "",
                  hiddenIds.has(row.id) ? "hidden-row" : "",
                ].join(" ")}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
              {expandedId === row.id && (
                <tr key={`${row.id}-detail`} className="detail-row">
                  <td colSpan={allColumns.length}>
                    <TokenDetail token={row.original} priceHistory={priceHistory.get(row.original.token_id) || []} />
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
      {tokens.length === 0 && (
        <div className="empty-state">No tokens being tracked</div>
      )}
    </div>
  );
}
