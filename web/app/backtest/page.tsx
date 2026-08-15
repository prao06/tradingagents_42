"use client";

import { useState } from "react";
import Metric from "@/components/Metric";
import EquityChart from "@/components/EquityChart";
import ApiError from "@/components/ApiError";
import { useFetch } from "@/lib/useFetch";
import { useTicker } from "@/lib/useTicker";
import { getJSON, BacktestSummary, BacktestDetail, pct, numTone } from "@/lib/api";

export default function BacktestPage() {
  const list = useFetch(() => getJSON<BacktestSummary[]>("/api/backtests"), []);
  const [name, setName] = useState<string>("");
  const chosen = name || list.data?.[0]?.name || "";
  const detail = useFetch<BacktestDetail | undefined>(
    () => (chosen ? getJSON<BacktestDetail>(`/api/backtests/${chosen}`) : Promise.resolve(undefined)),
    [chosen]
  );
  const [ticker] = useTicker();

  if (list.loading) return <div className="loading">Loading…</div>;
  if (list.error) return <ApiError error={list.error} />;
  if (!list.data?.length) return <div className="empty">No backtests found.</div>;

  const s = detail.data?.summary;
  const trades = (detail.data?.trades || []).filter(
    (t) => !ticker || String(t.ticker).toUpperCase() === ticker
  );

  return (
    <>
      <h1>Backtest</h1>
      <div className="row">
        <select value={chosen} onChange={(e) => setName(e.target.value)} aria-label="Select run">
          {list.data.map((b) => (
            <option key={b.name} value={b.name}>
              {b.name}
            </option>
          ))}
        </select>
      </div>

      {detail.loading ? (
        <div className="loading">Loading run…</div>
      ) : detail.error ? (
        <ApiError error={detail.error} />
      ) : s ? (
        <>
          <div className={"banner " + (s.verdict === "PASS" ? "pass" : "fail")} style={{ marginTop: 10 }}>
            Verdict: {s.verdict ?? "—"}
          </div>
          {s.pit === false && <div className="banner warn" style={{ marginTop: 8 }}>⚠ Not point-in-time — results leak future data.</div>}

          <div className="grid" style={{ marginTop: 10 }}>
            <Metric label="Total return" value={pct(s.total_return)} tone={numTone(s.total_return)} />
            <Metric label="Annualized" value={pct(s.annualized_return)} tone={numTone(s.annualized_return)} />
            <Metric label="Sharpe" value={s.sharpe?.toFixed(2) ?? "—"} />
            <Metric label="Max drawdown" value={pct(s.max_drawdown)} />
            <Metric label="Hit rate" value={s.hit_rate != null ? Math.round(s.hit_rate * 100) + "%" : "—"} />
            <Metric label="p-value" value={s.p_value?.toFixed(3) ?? "—"} />
          </div>

          <h2>Equity curve</h2>
          <div className="card">
            <EquityChart points={detail.data?.equity || []} />
          </div>

          {Array.isArray(s.folds) && s.folds.length > 0 && (
            <>
              <h2>Walk-forward folds</h2>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>fold</th><th>start</th><th>end</th>
                      <th className="num">total</th><th className="num">sharpe</th><th className="num">hit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.folds.map((f: any) => (
                      <tr key={f.fold}>
                        <td>{f.fold}</td><td>{f.start}</td><td>{f.end}</td>
                        <td className="num">{pct(f.total_return)}</td>
                        <td className="num">{f.sharpe?.toFixed(2)}</td>
                        <td className="num">{Math.round(f.hit_rate * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <h2>Trades{ticker ? ` · ${ticker}` : ""}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>date</th><th>ticker</th><th>rating</th>
                  <th className="num">pos</th><th className="num">raw</th><th className="num">net</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i}>
                    <td>{t.date}</td><td>{t.ticker}</td><td>{t.rating}</td>
                    <td className="num">{Number(t.position).toFixed(2)}</td>
                    <td className="num">{pct(t.raw_return)}</td>
                    <td className="num">{pct(t.net_return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </>
  );
}
