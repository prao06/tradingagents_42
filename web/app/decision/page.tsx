"use client";

import { useState } from "react";
import Stages from "@/components/Stages";
import ApiError from "@/components/ApiError";
import { useFetch } from "@/lib/useFetch";
import { useTicker } from "@/lib/useTicker";
import { getJSON, RunItem, RunDetail, ratingTone } from "@/lib/api";

export default function DecisionPage() {
  const list = useFetch(() => getJSON<RunItem[]>("/api/runs"), []);
  const [ticker] = useTicker();
  const [sel, setSel] = useState<string>("");

  if (list.loading) return <div className="loading">Loading…</div>;
  if (list.error) return <ApiError error={list.error} />;
  if (!list.data?.length) return <div className="empty">No saved runs yet.</div>;

  const runs = list.data.filter((r) => !ticker || r.ticker.toUpperCase() === ticker);
  const shown = runs.length ? runs : list.data;
  const key = (r: RunItem) => `${r.ticker}/${r.date}`;
  const chosen = sel && shown.some((r) => key(r) === sel) ? sel : key(shown[0]);

  return (
    <>
      <h1>Decision</h1>
      <p className="sub">Watch the firm reason through a ticker.</p>

      <div className="row">
        <select value={chosen} onChange={(e) => setSel(e.target.value)} aria-label="Select run">
          {shown.map((r) => (
            <option key={key(r)} value={key(r)}>
              {r.ticker} · {r.date} · {r.rating}
            </option>
          ))}
        </select>
      </div>

      <DecisionDetail runKey={chosen} />
    </>
  );
}

function DecisionDetail({ runKey }: { runKey: string }) {
  const detail = useFetch(() => getJSON<RunDetail>(`/api/runs/${runKey}`), [runKey]);
  if (detail.loading) return <div className="loading">Loading run…</div>;
  if (detail.error) return <ApiError error={detail.error} />;
  const d = detail.data;
  if (!d) return null;

  return (
    <>
      <div className="card" style={{ marginTop: 10 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <strong>
            {d.ticker} · {d.date}
          </strong>
          <span className={"chip " + ratingTone(d.rating)}>{d.rating}</span>
        </div>
        <div className="body" style={{ marginTop: 8 }}>
          {d.final_decision || "(no decision text)"}
        </div>
      </div>

      <Stages stages={d.stages} />
    </>
  );
}
