"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

interface Options {
  /** Re-fetch silently every N ms (no loading flash). */
  interval?: number;
  enabled?: boolean;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = [], options: Options = {}) {
  const { interval, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const alive = useRef(true);
  const requestId = useRef(0);

  const load = useCallback(async (silent = false) => {
    const id = ++requestId.current;
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await fetcherRef.current();
      if (!alive.current || id !== requestId.current) return;
      setData(result);
      setError(null);
    } catch (e) {
      if (!alive.current || id !== requestId.current) return;
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      if (alive.current && id === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    requestId.current++;
    if (!enabled) return () => { alive.current = false; requestId.current++; };
    setData(null);
    setError(null);
    load(false);
    let timer: ReturnType<typeof setInterval> | undefined;
    if (interval) timer = setInterval(() => load(true), interval);
    return () => {
      alive.current = false;
      requestId.current++;
      if (timer) clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, interval, load, ...deps]);

  return { data, error, loading, refreshing, refetch: () => load(true), reload: () => load(false), setData };
}
