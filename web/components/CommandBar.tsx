"use client";

import { useTicker } from "@/lib/useTicker";

// Bloomberg-style ticker filter, shared across pages.
export default function CommandBar() {
  const [ticker, setTicker] = useTicker();
  return (
    <div className="command">
      <input
        value={ticker}
        placeholder="Filter by ticker — e.g. NVDA"
        onChange={(e) => setTicker(e.target.value)}
        inputMode="text"
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        aria-label="Ticker filter"
      />
    </div>
  );
}
