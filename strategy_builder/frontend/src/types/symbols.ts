/**
 * Symbols Types
 * 
 * Stock Master File Management System
 */

export type Exchange = "kospi" | "kosdaq" | "nasdaq" | "nyse" | "amex";

export interface Symbol {
  id: string;
  ticker: string;
  market: "KR" | "US";
  currency: "KRW" | "USD";
  english_name: string;
  code: string;
  name: string;
  exchange: Exchange;
  exchange_name: string;
}

export interface SymbolSearchResponse {
  query: string;
  total: number;
  items: Symbol[];
}

export interface MasterStatus {
  exchanges: { exchange: Exchange; name: string; count: number; updated_at: string | null }[];
  kospi_count: number;
  kosdaq_count: number;
  total_count: number;
  kospi_updated: string | null;
  kosdaq_updated: string | null;
  needs_update: boolean;
}

export interface CollectResult {
  success: boolean;
  kospi_count: number;
  kosdaq_count: number;
  total_count: number;
  errors: string[];
}
