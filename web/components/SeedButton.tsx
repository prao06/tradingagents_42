"use client";

import { useState } from "react";
import { postJSON } from "@/lib/api";

// One-tap populate for a fresh backend: writes demo backtest + runs + journal.
// Works out of the box when the backend has no RUN_API_KEY set.
export default function SeedButton() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const seed = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await postJSON<{ runs: number }>("/api/seed-demo", {});
      setMsg(`Seeded ${r.runs} runs — reloading…`);
      setTimeout(() => location.reload(), 700);
    } catch (e) {
      setMsg(`Failed: ${String((e as Error).message || e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 10 }} className="row">
      <button className="primary" onClick={seed} disabled={busy}>
        {busy ? "Seeding…" : "Seed demo data"}
      </button>
      {msg && <span className="muted">{msg}</span>}
    </div>
  );
}
