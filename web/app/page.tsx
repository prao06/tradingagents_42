"use client";

import CommandBar from "@/components/CommandBar";
import Metric from "@/components/Metric";
import ApiError from "@/components/ApiError";
import { useFetch } from "@/lib/useFetch";
import { getJSON, BacktestSummary, JournalResp, pct, numTone } from "@/lib/api";

export default function Home() {
  const bts = useFetch(() => getJSON<BacktestSummary[]>("/api/backtests"), []);
  const jr = useFetch(() => getJSON<JournalResp>("/api/journal"), []);
  const latest = bts.data?.[0];

  return (
    <>
      <h1>TradingAgents</h1>
      <p className="sub">Transparent multi-agent reasoning — and whether it paid off.</p>
      <CommandBar />

      <h2>Latest backtest</h2>
      {bts.loading ? (
        <div className="loading">Loading…</div>
      ) : bts.error ? (
        <ApiError error={bts.error} />
      ) : !latest ? (
        <div className="empty">No backtests yet.</div>
      ) : (
        <>
          <div className={"banner " + (latest.verdict === "PASS" ? "pass" : "fail")}>
            Verdict: {latest.verdict ?? "—"}
          </div>
          <div className="grid" style={{ marginTop: 10 }}>
            <Metric label="Total return" value={pct(latest.total_return)} tone={numTone(latest.total_return)} />
            <Metric label="Sharpe" value={latest.sharpe?.toFixed(2) ?? "—"} />
            <Metric label="p-value" value={latest.p_value?.toFixed(3) ?? "—"} />
          </div>
        </>
      )}

      <h2>Decision track record</h2>
      {jr.loading ? (
        <div className="loading">Loading…</div>
      ) : jr.error ? (
        <ApiError error={jr.error} />
      ) : (
        <div className="grid">
          <Metric
            label="Win rate"
            value={jr.data ? Math.round(jr.data.summary.win_rate * 100) + "%" : "—"}
          />
          <Metric label="Mean return" value={pct(jr.data?.summary.mean_return)} tone={numTone(jr.data?.summary.mean_return)} />
          <Metric label="Mean alpha" value={pct(jr.data?.summary.mean_alpha)} tone={numTone(jr.data?.summary.mean_alpha)} />
        </div>
      )}
    </>
  );
}
