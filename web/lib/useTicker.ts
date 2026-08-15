"use client";

import { useEffect, useState } from "react";

// A tiny shared "command bar" ticker filter, persisted in localStorage and
// synced across pages without a global provider (keeps the layout a server
// component). Set via the CommandBar; read on every page.
const KEY = "ta_ticker";
const EVENT = "ta-ticker";

export function useTicker(): [string, (value: string) => void] {
  const [ticker, setTicker] = useState("");

  useEffect(() => {
    setTicker(localStorage.getItem(KEY) || "");
    const handler = () => setTicker(localStorage.getItem(KEY) || "");
    window.addEventListener(EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  const set = (value: string) => {
    const v = value.trim().toUpperCase();
    localStorage.setItem(KEY, v);
    window.dispatchEvent(new Event(EVENT));
    setTicker(v);
  };

  return [ticker, set];
}
