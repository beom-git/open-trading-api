"use client";
import {useEffect,useRef,useState} from "react";
import {useAuth} from "@/hooks";
import {apiGet,apiPost} from "@/lib/api/client";
import {formatKstDateTime} from "@/lib/currency";
type Holding={instrument_id:string;quantity:number;avg_price:number;current_price:number;eval_amount:number;profit_loss:number;profit_rate:number};
type Pending={instrument_id:string;order_no:string;remaining:number;price:number;action:string};
type Snapshot<T>={data:T;fetched_at:string;mode:string};
export function USStockAccount(){
 const {status}=useAuth();const enabled=status.authenticated;
 const [holdings,setHoldings]=useState<Snapshot<Holding[]>|null>(null),[pending,setPending]=useState<Snapshot<Pending[]>|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[outcome,setOutcome]=useState<{status:string;message:string}|null>(null);
 const lock=useRef(false),version=useRef(0);
 useEffect(()=>{version.current++;setHoldings(null);setPending(null);setOutcome(null);setError('');},[status.mode,status.authenticated]);
 useEffect(()=>{const dirty=()=>setError('주문 접수 이후 잔고·미체결을 다시 조회하세요');window.addEventListener('kis-us-account-dirty',dirty);return()=>window.removeEventListener('kis-us-account-dirty',dirty);},[]);
 async function refresh(){
  if(!enabled||lock.current)return;lock.current=true;setBusy(true);setError('');const v=version.current;
  try{const h=await apiGet<Snapshot<Holding[]>>('/api/us-stock/holdings');if(v!==version.current)return;setHoldings(h);const p=await apiGet<Snapshot<Pending[]>>('/api/us-stock/pending');if(v===version.current)setPending(p);}
  catch(e){if(v===version.current)setError(`갱신 지연 · 이전 성공 시각 유지: ${String(e)}`);}finally{lock.current=false;setBusy(false);}
 }
 async function cancel(p:Pending){
  if(!enabled||lock.current||outcome?.status==='unknown')return;
  if(!window.confirm(`${status.mode==='vps'?'모의':'실전'} · ${p.instrument_id} 주문 ${p.order_no} 미체결 ${p.remaining}주 취소 요청?`))return;
  lock.current=true;setBusy(true);
  const request_id=crypto.randomUUID();const unresolved={status:'unknown',message:'취소 접수 확인 필요',request_id};
  try{sessionStorage.setItem('kis_us_paper_unresolved',JSON.stringify(unresolved));const r=await apiPost<{status:string;message:string}>('/api/us-stock/cancel',{request_id,instrument_id:p.instrument_id,order_no:p.order_no,quantity:p.remaining});setOutcome(r);if(r.status!=='unknown')sessionStorage.removeItem('kis_us_paper_unresolved');setError('취소 요청 이후 주문내역을 다시 조회하세요');}
  catch{setOutcome(unresolved);}finally{lock.current=false;setBusy(false);}
 }
 return <section aria-label="미국 계좌 잔고·미체결" className="card p-4 space-y-3"><h3>미국 주식 잔고·미체결 주문</h3><p>설정 모드: {status.mode==='vps'?'모의투자':'실전투자'} · USD</p><button className="border p-2" disabled={!enabled||busy} onClick={refresh}>{busy?'조회 중...':'미국 잔고·미체결 재조회'}</button>{!enabled&&<p>설정에서 인증해주세요</p>}{error&&<p role="alert">{error}</p>}{outcome&&<p role="status">{outcome.status} · {outcome.message}</p>}<p>잔고 성공 조회 {holdings?formatKstDateTime(holdings.fetched_at):'미조회'}</p><p>미체결 성공 조회 {pending?formatKstDateTime(pending.fetched_at):'미조회'}</p><p className="text-xs">계좌 전체의 미국 종목입니다. 국내 잔고와 합산하지 않습니다. 미체결 조회 범위: 최근 30일.</p><div className="overflow-auto"><table><thead><tr>{['종목','수량','평균 USD','현재 USD','평가 USD','손익 USD','수익률 %'].map(t=><th key={t}>{t}</th>)}</tr></thead><tbody>{holdings?.data.map(h=><tr key={h.instrument_id}><td>{h.instrument_id}</td><td>{h.quantity}</td><td>{h.avg_price}</td><td>{h.current_price}</td><td>{h.eval_amount}</td><td>{h.profit_loss}</td><td>{h.profit_rate}</td></tr>)}</tbody></table></div>{pending?.data.map(p=><p key={p.order_no}>{p.instrument_id} · {p.order_no} · {p.action} · 미체결 {p.remaining}주 · {p.price} USD <button disabled={!enabled||busy||outcome?.status==='unknown'} onClick={()=>cancel(p)}>주문 취소</button></p>)}{holdings&&holdings.data.length===0&&<p>미국 보유 종목 없음</p>}{pending&&pending.data.length===0&&<p>해당 조회 기간의 미국 미체결 없음</p>}</section>;
}
