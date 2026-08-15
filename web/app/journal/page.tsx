"use client";

import { useState } from "react";
import Metric from "@/components/Metric";
import ApiError from "@/components/ApiError";
import { useFetch } from "@/lib/useFetch";
import { useTicker } from "@/lib/useTicker";
import { getJSON, JournalResp, pct, numTone } from "@/lib/api";

const STATUSES = ["resolved", "pending"];

export default function JournalPage() {
  const jr = useFetch(() => getJSON<JournalResp>("/api/journal"), []);
  const [ticker] = useTicker();
  const [status, setStatus] = useState<string[]>(STATUSES);

  if (jr.loading) return <div className="loading">Loading…</div>;
  if (jr.error) return <ApiError error={jr.error} />;
  if (!jr.data?.entries.length) return <div className="empty">No decisions logged yet.</div>;

  const s = jr.data.summary;
  const rows = jr.data.entries.filter(
    (e) => status.includes(e.status) && (!ticker || e.ticker.toUpperCase() === ticker)
  );
  const toggle = (v: string) =>
    setStatus((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]));

  return (
    <>
      <h1>Journal</h1>
      <p className="sub">Ratings vs. realized outcome — the track record.</p>

      <div className="grid">
        <Metric label="Win rate" value={Math.round(s.win_rate * 100) + "%"} />
        <Metric label="Mean return" value={pct(s.mean_return)} tone={numTone(s.mean_return)} />
        <Metric label="Mean alpha" value={pct(s.mean_alpha)} tone={numTone(s.mean_alpha)} />
        <Metric label="Resolved" value={String(s.n_resolved)} />
        <Metric label="Pending" value={String(s.n_pending)} />
      </div>

      <div className="pillbar" style={{ marginTop: 12 }}>
        {STATUSES.map((st) => (
          <span key={st} className={"pill" + (status.includes(st) ? " on" : "")} onClick={() => toggle(st)}>
            {st}
          </span>
        ))}
      </div>

      <div className="table-wrap" style={{ marginTop: 10 }}>
        <table>
          <thead>
            <tr>
              <th>date</th><th>ticker</th><th>rating</th><th>status</th>
              <th className="num">raw</th><th className="num">alpha</th><th>hold</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={i}>
                <td>{e.date}</td><td>{e.ticker}</td><td>{e.rating}</td><td>{e.status}</td>
                <td className="num">{pct(e.raw_return)}</td>
                <td className="num">{pct(e.alpha_return)}</td>
                <td>{e.holding ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
