"use client";

import { useEffect, useState } from "react";

type State<T> = { data?: T; loading: boolean; error?: string };

// Minimal fetch hook with loading/error states. Client-side only, so the app
// builds and renders even when the backend is unreachable.
export function useFetch<T>(fn: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [state, setState] = useState<State<T>>({ loading: true });
  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    fn()
      .then((d) => alive && setState({ data: d, loading: false }))
      .catch((e) => alive && setState({ error: String(e?.message || e), loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
