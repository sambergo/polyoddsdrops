import type { ReactNode } from "react";

interface LayoutProps {
  connected: boolean;
  error: string | null;
  tokenCount: number;
  notificationBell?: ReactNode;
  children: ReactNode;
}

export function Layout({
  connected,
  error,
  tokenCount,
  notificationBell,
  children,
}: LayoutProps) {
  return (
    <div className="layout">
      <header className="top-bar">
        <div className="top-bar-left">
          <img src="/icon.png" alt="" className="app-icon" />
          <h1>PolyOddsDrops</h1>
          <span className="token-count">{tokenCount} tokens</span>
        </div>
        <div className="top-bar-right">
          {notificationBell}
          <span
            className={`status-dot ${connected ? "connected" : "disconnected"}`}
          />
          <span className="status-text">
            {connected ? "Live" : "Disconnected"}
          </span>
        </div>
      </header>
      {error && <div className="error-banner">{error}</div>}
      <main>{children}</main>
    </div>
  );
}
