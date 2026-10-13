"use client";

import { RefreshCw } from "lucide-react";
import { formatKstDateTime } from "@/lib/currency";
import { useAuth } from "@/hooks";
import { useCurrency } from "@/contexts/CurrencyContext";

export function ExchangeRateTicker() {
  const { status } = useAuth();
  const { exchangeRate, stale, isLoading, error, refresh } = useCurrency();
  const fetchedTime = exchangeRate ? formatKstDateTime(exchangeRate.fetched_at) : null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs pb-2" aria-label="원 달러 환율">
      <span className="font-semibold tabular-nums text-slate-700 dark:text-slate-200" aria-live="polite">
        USD/KRW {exchangeRate ? `1달러 = ${exchangeRate.rate.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}원` : "—"}
      </span>
      <span className={stale || error ? "text-amber-600 dark:text-amber-400" : "text-slate-500"}>
        {!status.authenticated ? "KIS 인증 후 조회" : stale && exchangeRate ? "갱신 지연 · 이전 환율" : error ? "환율 조회 실패" : isLoading && !exchangeRate ? "조회 중…" : "30초 자동 갱신"}
        {fetchedTime && ` · 갱신 ${fetchedTime}`}
      </span>
      <button type="button" onClick={refresh} disabled={!status.authenticated || isLoading}
        aria-label="환율 새로고침" title={error || "KIS 환율 조회 · 30초 갱신 간격"}
        className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 focus-ring">
        <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
      </button>
      {exchangeRate?.source_quote_time && (
        <span className="text-slate-500">KIS 제공 시각 {exchangeRate.source_quote_time.replace("T", " ")}</span>
      )}
    </div>
  );
}
