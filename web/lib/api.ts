// API client for the FastAPI backend. Base URL is injected at build time via
// NEXT_PUBLIC_API_URL (e.g. your Render/Railway URL); defaults to localhost.
export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// --- types (mirror server/app.py responses) ---
export type Health = { status: string; live_runs_enabled: boolean };

export type BacktestSummary = {
  name: string; verdict: string | null; total_return: number | null;
  sharpe: number | null; p_value: number | null; pit: boolean | null;
};

export type Fold = {
  fold: number; start: string; end: string; n_periods: number;
  total_return: number; sharpe: number; hit_rate: number;
};

export type BacktestDetail = {
  name: string;
  summary: Record<string, any> & { folds?: Fold[] };
  equity: { date: string; equity: number }[];
  trades: Record<string, any>[];
};

export type JournalEntry = {
  date: string; ticker: string; rating: string; status: string;
  raw_return: number | null; alpha_return: number | null; holding: string | null;
  reflection: string; decision: string;
};
export type JournalResp = {
  summary: {
    n_resolved: number; n_pending: number; win_rate: number;
    mean_return: number; mean_alpha: number;
  };
  entries: JournalEntry[];
};

export type RunItem = { ticker: string; date: string; rating: string };
export type Stage = {
  group: string; label: string; persona: string; icon: string; content: string;
};
export type RunDetail = {
  ticker: string; date: string; rating: string;
  final_decision: string; stages: Stage[];
};

export const ratingTone = (rating?: string | null): "green" | "red" | "gray" => {
  if (rating === "Buy" || rating === "Overweight") return "green";
  if (rating === "Sell" || rating === "Underweight") return "red";
  return "gray";
};

export const numTone = (x?: number | null): "green" | "red" | undefined =>
  x === null || x === undefined || Number.isNaN(x) ? undefined : x >= 0 ? "green" : "red";

export const pct = (x: number | null | undefined, digits = 2): string =>
  x === null || x === undefined || Number.isNaN(x)
    ? "—"
    : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
