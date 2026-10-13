"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useAuthContext } from "./AuthContext";
import { getExchangeRate, type ExchangeRate } from "@/lib/api/market";

export type DisplayCurrency = "USD" | "KRW";
const STORAGE_KEY = "kis_display_currency";
const REFRESH_MS = 30_000;
const MAX_AGE_MS = 90_000;

interface CurrencyContextValue {
  displayCurrency: DisplayCurrency;
  setDisplayCurrency: (currency: DisplayCurrency) => void;
  exchangeRate: ExchangeRate | null;
  usableRate: number | null;
  stale: boolean;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

const CurrencyContext = createContext<CurrencyContextValue | null>(null);

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const { status } = useAuthContext();
  const [displayCurrency, setCurrency] = useState<DisplayCurrency>("USD");
  const [rateMode, setRateMode] = useState<string | null>(null);
  const [exchangeRate, setExchangeRate] = useState<ExchangeRate | null>(null);
  const [failed, setFailed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const refreshRef = useRef<() => void>(() => {});

  useEffect(() => {
    const restore = () => {
      try {
        setCurrency(localStorage.getItem(STORAGE_KEY) === "KRW" ? "KRW" : "USD");
      } catch { /* Storage may be unavailable; keep the in-memory preference. */ }
    };
    restore();
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY || event.key === null) restore();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setDisplayCurrency = useCallback((currency: DisplayCurrency) => {
    setCurrency(currency);
    try { localStorage.setItem(STORAGE_KEY, currency); } catch { /* In-memory setting still works. */ }
  }, []);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let controller: AbortController | null = null;
    setExchangeRate(null);
    setFailed(false);
    setError(null);
    setIsLoading(false);
    setNow(Date.now());

    const poll = async () => {
      if (!status.authenticated || document.visibilityState !== "visible" || inFlight) return;
      inFlight = true;
      controller = new AbortController();
      setIsLoading(true);
      try {
        const response = await getExchangeRate(controller.signal);
        if (!active) return;
        const data = response.data;
        const valid = data && data.base === "USD" && data.quote === "KRW" &&
          Number.isFinite(data.rate) && data.rate > 0 && Number.isFinite(Date.parse(data.fetched_at));
        if (valid) { setExchangeRate(data); setRateMode(status.mode); }
        const failure = response.status !== "success" || response.stale || !valid;
        setFailed(failure);
        setError(failure ? response.message || "환율을 갱신하지 못했습니다" : null);
      } catch {
        if (!active) return;
        setFailed(true);
        setError("환율을 갱신하지 못했습니다. 연결 상태를 확인해주세요.");
      } finally {
        inFlight = false;
        if (active) { setIsLoading(false); setNow(Date.now()); }
      }
    };
    refreshRef.current = () => { void poll(); };
    void poll();
    const interval = window.setInterval(() => { void poll(); }, REFRESH_MS);
    const clock = window.setInterval(() => setNow(Date.now()), 10_000);
    const onVisible = () => { setNow(Date.now()); void poll(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      controller?.abort();
      refreshRef.current = () => {};
      window.clearInterval(interval);
      window.clearInterval(clock);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [status.authenticated, status.mode]);

  const visibleRate = status.authenticated && rateMode === status.mode ? exchangeRate : null;
  const stale = failed || !!(visibleRate && now - Date.parse(visibleRate.fetched_at) > MAX_AGE_MS);
  const usableRate = visibleRate && !stale ? visibleRate.rate : null;
  const refresh = useCallback(() => refreshRef.current(), []);
  return (
    <CurrencyContext.Provider value={{ displayCurrency, setDisplayCurrency, exchangeRate: visibleRate, usableRate, stale, isLoading, error, refresh }}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  const context = useContext(CurrencyContext);
  if (!context) throw new Error("useCurrency must be used within CurrencyProvider");
  return context;
}
