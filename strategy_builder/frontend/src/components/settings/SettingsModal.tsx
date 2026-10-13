"use client";

import { useState, useEffect } from "react";
import { X, RefreshCw, Database, Shield, Clock } from "lucide-react";
import { formatKstDateTime } from "@/lib/currency";
import { useCurrency, type DisplayCurrency } from "@/contexts/CurrencyContext";
import { useAuth } from "@/hooks";
import { getMasterStatus, collectMasterFiles } from "@/lib/api/symbols";
import type { MasterStatus } from "@/types/symbols";
import type { AuthMode } from "@/types/auth";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { displayCurrency, setDisplayCurrency, exchangeRate, usableRate } = useCurrency();
  const { status, isLoading, error, login, switchMode } = useAuth();
  const [masterStatus, setMasterStatus] = useState<MasterStatus | null>(null);
  const [collectionError, setCollectionError] = useState("");
  const [isCollecting, setIsCollecting] = useState(false);
  const [cooldownTimer, setCooldownTimer] = useState(0);

  // Fetch master status on mount
  useEffect(() => {
    if (isOpen) {
      fetchMasterStatus();
    }
  }, [isOpen]);

  // Cooldown timer - 실시간으로 감소
  useEffect(() => {
    if (status.cooldown_remaining && status.cooldown_remaining > 0) {
      setCooldownTimer(status.cooldown_remaining);
    }
  }, [status.cooldown_remaining]);

  useEffect(() => {
    if (cooldownTimer > 0) {
      const interval = setInterval(() => {
        setCooldownTimer((prev) => Math.max(0, prev - 1));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [cooldownTimer]);

  const fetchMasterStatus = async () => {
    try {
      const result = await getMasterStatus();
      setMasterStatus(result);
    } catch (error) {
      console.error("Failed to fetch master status:", error);
    }
  };

  const handleCollectMaster = async () => {
    setIsCollecting(true);
    setCollectionError("");
    try {
      const result = await collectMasterFiles();
      await fetchMasterStatus();
      if (!result.success && result.errors?.length) {
        setCollectionError(result.errors.join(" / "));
      }
    } catch (error) {
      setCollectionError("마스터파일 수집에 실패했습니다. 연결 상태를 확인해주세요.");
    } finally {
      setIsCollecting(false);
    }
  };

  const handleLogin = async (mode: AuthMode) => {
    await login(mode);
  };

  const handleSwitchMode = async () => {
    const newMode = status.mode === "vps" ? "prod" : "vps";
    const success = await switchMode(newMode);
    if (success) {
      setCooldownTimer(60);
    }
  };

  if (!isOpen) return null;

  const canSwitch = status.can_switch_mode !== false && cooldownTimer === 0;
  const isVps = status.mode === "vps";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md max-h-[90vh] overflow-y-auto mx-4 bg-white dark:bg-slate-900 rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold">설정</h2>
          <button
            onClick={onClose}
            aria-label="설정 닫기"
            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-6">
          <section className="space-y-3">
            <label htmlFor="display-currency" className="text-sm font-medium text-slate-700 dark:text-slate-300">해외 시세 표시 통화</label>
            <select id="display-currency" value={displayCurrency}
              onChange={(event) => setDisplayCurrency(event.target.value as DisplayCurrency)}
              className="w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
              <option value="USD">USD · 달러</option>
              <option value="KRW">KRW · 원화 환산</option>
            </select>
            <p className="text-xs text-slate-500">미국 주식 시세와 전일 대비 금액에 적용되며, 이 브라우저에 저장됩니다.</p>
            <p className="text-xs text-slate-500">
              {usableRate !== null ? `적용 환율: 1 USD = ${usableRate.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} KRW (KIS)` : "유효한 환율이 없으면 달러로 표시합니다."}
            </p>
            {exchangeRate && <p className="text-xs text-slate-500">마지막 조회 성공: {formatKstDateTime(exchangeRate.fetched_at)}</p>}
            {exchangeRate?.source_quote_time && <p className="text-xs text-slate-500">KIS 제공 시각: {exchangeRate.source_quote_time.replace("T", " ")}</p>}
            <p className="text-xs text-slate-500">환율은 30초마다 조회하며 휴장·제공 지연 시 마지막 시세일 수 있습니다. 실제 환전 금액에는 환전 수수료 등이 반영됩니다.</p>
          </section>

          {/* Authentication & Mode Section */}
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
              <Shield className="w-4 h-4" />
              인증 및 모드
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg space-y-3">
              {/* 현재 상태 표시 */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600 dark:text-slate-400">인증 상태</span>
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                  status.authenticated
                    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                }`}>
                  {status.authenticated ? "인증됨" : "미인증"}
                </span>
              </div>
              {status.authenticated && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 dark:text-slate-400">현재 모드</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                    isVps
                      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                      : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  }`}>
                    {status.mode_display || (isVps ? "모의투자" : "실전투자")}
                  </span>
                </div>
              )}

              {/* 쿨다운 표시 */}
              {cooldownTimer > 0 && (
                <div className="flex items-center gap-2 p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                  <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  <span className="text-sm text-amber-600 dark:text-amber-400 font-medium">
                    쿨다운: {cooldownTimer}초 남음
                  </span>
                  <div className="flex-1 h-1 bg-amber-200 dark:bg-amber-800 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-amber-500 transition-all duration-1000"
                      style={{ width: `${(cooldownTimer / 60) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {/* 모드 전환 버튼 */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    // 모의투자 버튼
                    if (!status.authenticated) {
                      handleLogin("vps");
                    } else if (!isVps && canSwitch) {
                      handleSwitchMode();
                    }
                  }}
                  disabled={isLoading || (status.authenticated && isVps) || (status.authenticated && !isVps && !canSwitch)}
                  className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    isVps && status.authenticated
                      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 ring-2 ring-yellow-500 cursor-default"
                      : isLoading
                        ? "bg-slate-100 dark:bg-slate-700 opacity-50"
                        : "bg-slate-100 dark:bg-slate-700 hover:bg-yellow-50 dark:hover:bg-yellow-900/20"
                  }`}
                >
                  {isLoading ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <span className="w-2 h-2 rounded-full bg-yellow-500" />
                      모의투자
                    </>
                  )}
                </button>
                <button
                  onClick={() => {
                    // 실전투자 버튼
                    if (!status.authenticated) {
                      handleLogin("prod");
                    } else if (isVps && canSwitch) {
                      handleSwitchMode();
                    }
                  }}
                  disabled={isLoading || (status.authenticated && !isVps) || (status.authenticated && isVps && !canSwitch)}
                  className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    !isVps && status.authenticated
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 ring-2 ring-green-500 cursor-default"
                      : isLoading
                        ? "bg-slate-100 dark:bg-slate-700 opacity-50"
                        : "bg-slate-100 dark:bg-slate-700 hover:bg-green-50 dark:hover:bg-green-900/20"
                  }`}
                >
                  {isLoading ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <span className="w-2 h-2 rounded-full bg-green-500" />
                      실전투자
                    </>
                  )}
                </button>
              </div>

              {error && (
                <div className="px-2 py-1.5 rounded bg-red-50 dark:bg-red-900/20 text-xs text-red-600 dark:text-red-400">
                  {error}
                </div>
              )}

              <p className="text-xs text-slate-500 dark:text-slate-400 text-center">
                모드 전환은 1분에 1회만 가능합니다
              </p>
            </div>
          </section>

          {/* Master File Status */}
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
              <Database className="w-4 h-4" />
              종목 마스터파일
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg space-y-3">
              {masterStatus ? (
                <>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {masterStatus.exchanges?.map((item) => (
                      <div key={item.exchange} className="flex items-center justify-between">
                        <span className="text-slate-600 dark:text-slate-400">{item.name}</span>
                        <span className="font-mono">{item.count.toLocaleString()}개</span>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-600 dark:text-slate-400">총 종목 수</span>
                    <span className="font-mono font-bold">{masterStatus.total_count.toLocaleString()}개</span>
                  </div>
                  {masterStatus.kospi_updated && (
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      마지막 업데이트: {new Date(masterStatus.kospi_updated).toLocaleString()}
                    </div>
                  )}
                  {masterStatus.needs_update && (
                    <div className="text-xs text-amber-600 dark:text-amber-400">
                      업데이트가 필요합니다
                    </div>
                  )}
                </>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">
                  로딩 중...
                </div>
              )}
              {collectionError && <p role="alert" className="text-xs text-red-500">{collectionError}</p>}
              <button
                onClick={handleCollectMaster}
                disabled={isCollecting}
                className="w-full py-2 px-4 rounded-lg text-sm font-medium bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors"
              >
                {isCollecting ? (
                  <span className="flex items-center justify-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    수집 중...
                  </span>
                ) : (
                  "마스터파일 수집"
                )}
              </button>
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}

export default SettingsModal;
