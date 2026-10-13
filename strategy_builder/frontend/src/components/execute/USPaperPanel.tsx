"use client";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/hooks";
import { useCurrency } from "@/contexts/CurrencyContext";
import { apiGet, apiPost } from "@/lib/api/client";
import { formatKstDateTime } from "@/lib/currency";
type Holding={instrument_id:string;quantity:number;avg_price:number;current_price:number;eval_amount:number;profit_loss:number;profit_rate:number};
type Pending={instrument_id:string;order_no:string;remaining:number;price:number;action:string};
type Outcome={status:string;message:string;order_no?:string;request_id?:string};
type Snapshot<T>={status:string;data:T;fetched_at:string};
type Draft={request_id:string;instrument_id:string;action:string;quantity:number;price:string;currency:"USD"};
export function USPaperPanel({instrumentId="NASDAQ:AAPL",currentPrice}:{instrumentId?:string;currentPrice?:number}){
 const {status}=useAuth();const {displayCurrency,usableRate,exchangeRate}=useCurrency();
 const enabled=status.authenticated&&status.mode==='vps';
 const [price,setPrice]=useState(String(currentPrice??"")),[qty,setQty]=useState(1),[action,setAction]=useState("BUY");
 const [draft,setDraft]=useState<Draft|null>(null),[outcome,setOutcome]=useState<Outcome|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [holdings,setHoldings]=useState<Snapshot<Holding[]>|null>(null),[pending,setPending]=useState<Snapshot<Pending[]>|null>(null),[buyable,setBuyable]=useState<{amount:number;quantity:number}|null>(null);
 const lock=useRef(false),version=useRef(0),modeRef=useRef(status.mode);modeRef.current=status.mode;
 useEffect(()=>{setPrice(String(currentPrice??""));setDraft(null);setBuyable(null);version.current++;},[instrumentId,currentPrice]);
 useEffect(()=>{version.current++;setHoldings(null);setPending(null);setDraft(null);setBuyable(null);},[status.mode,status.authenticated]);
 useEffect(()=>{try{const old=sessionStorage.getItem('kis_us_paper_unresolved');if(old)setOutcome(JSON.parse(old));}catch{}},[]);
 async function refresh(){
  if(!enabled||lock.current)return;lock.current=true;setBusy(true);setError("");const v=version.current;
  try{const h=await apiGet<Snapshot<Holding[]>>("/api/us-paper/holdings");if(v!==version.current)return;setHoldings(h);const p=await apiGet<Snapshot<Pending[]>>("/api/us-paper/pending");if(v===version.current)setPending(p);}
  catch(e){if(v===version.current)setError(`조회 실패 · 이전 데이터는 갱신되지 않았습니다: ${String(e)}`);}finally{lock.current=false;setBusy(false);}
 }
 async function checkBuyable(){if(!enabled||lock.current)return;lock.current=true;setBusy(true);setBuyable(null);const v=version.current;try{const r=await apiGet<Snapshot<{amount:number;quantity:number}>>(`/api/us-paper/buyable?instrument_id=${encodeURIComponent(instrumentId)}&price=${encodeURIComponent(price)}`);if(v===version.current)setBuyable(r.data);}catch(e){setError(String(e));}finally{lock.current=false;setBusy(false);}}
 function confirm(){
  if(!enabled||busy||outcome?.status==='unknown')return;
  if(!Number.isInteger(qty)||qty<=0||!Number.isFinite(Number(price))||Number(price)<=0){setError('양의 정수 수량과 USD 지정가를 입력하세요');return;}
  setError('');setDraft({request_id:crypto.randomUUID(),instrument_id:instrumentId,action,quantity:qty,price,currency:'USD'});
 }
 async function submit(){
  if(!draft||!enabled||lock.current)return;lock.current=true;setBusy(true);setError('');
  const unknown={status:'unknown',message:'접수 여부 재조회 필요',request_id:draft.request_id};
  try{sessionStorage.setItem('kis_us_paper_unresolved',JSON.stringify(unknown));}catch{}
  try{const r=await apiPost<Outcome>('/api/us-paper/order',draft);setOutcome(r);if(r.status!=='unknown')sessionStorage.removeItem('kis_us_paper_unresolved');else sessionStorage.setItem('kis_us_paper_unresolved',JSON.stringify(r));}
  catch{setOutcome({...unknown,message:'접수 여부를 확인할 수 없습니다. 주문내역을 재조회하세요. 자동 재전송하지 않습니다.'});}
  finally{setDraft(null);lock.current=false;setBusy(false);}
 }
 async function cancel(p:Pending){
  if(!enabled||lock.current)return;
  if(!window.confirm(`${p.instrument_id} 주문 ${p.order_no} · 미체결 ${p.remaining}주 취소 요청?`))return;
  lock.current=true;setBusy(true);const request={request_id:crypto.randomUUID(),instrument_id:p.instrument_id,order_no:p.order_no,quantity:p.remaining};
  try{sessionStorage.setItem('kis_us_paper_unresolved',JSON.stringify({status:'unknown',message:'취소 접수 재조회 필요',request_id:request.request_id}));const r=await apiPost<Outcome>('/api/us-paper/cancel',request);setOutcome(r);if(r.status!=='unknown')sessionStorage.removeItem('kis_us_paper_unresolved');}
  catch{setOutcome({status:'unknown',message:'취소 여부를 확인할 수 없습니다. 주문내역 재조회 필요'});}finally{lock.current=false;setBusy(false);}
 }
 return <section aria-label="미국 모의 주문" className="border rounded p-4 space-y-3"><h2>미국 주식 모의 주문 · 잔고</h2><p>현재 모드: {status.mode==='vps'?'모의투자':'실전투자'} · {enabled?'USD 지정가 지원':'모의 모드 인증 후 이용 가능'}</p><p>{instrumentId} · {instrumentId.split(':')[0]} · USD</p><div className="flex flex-wrap gap-3"><label>매매 구분<select aria-label="매매 구분" value={action} onChange={e=>setAction(e.target.value)} disabled={!enabled||busy}><option value="BUY">매수</option><option value="SELL">매도</option></select></label><label>수량<input aria-label="모의 수량" type="number" min={1} step={1} value={qty} onChange={e=>setQty(Number(e.target.value))} disabled={busy}/></label><label>지정가 USD<input aria-label="지정가 USD" type="number" step="any" value={price} onChange={e=>setPrice(e.target.value)} disabled={busy}/></label></div><button className="border p-2" disabled={!enabled||busy||outcome?.status==='unknown'} onClick={confirm}>모의 주문 확인</button><button className="border p-2" disabled={!enabled||busy||!price} onClick={checkBuyable}>주문 가능 조회</button>{buyable&&<p>주문 가능 {buyable.amount} USD · {buyable.quantity}주</p>}{draft&&<div role="dialog" aria-modal="true" aria-label="미국 모의 주문 확인" className="border p-4"><p>{draft.instrument_id} · {draft.action} · {draft.quantity}주 × {draft.price} USD = {(draft.quantity*Number(draft.price)).toFixed(4)} USD</p>{displayCurrency==='KRW'&&usableRate!==null&&<p>참고 {(draft.quantity*Number(draft.price)*usableRate).toLocaleString('ko-KR')} KRW · 적용 환율 {usableRate} · {exchangeRate&&formatKstDateTime(exchangeRate.fetched_at)}. 실제 제출은 USD입니다.</p>}<button disabled={!enabled||busy||modeRef.current!=='vps'} onClick={submit}>모의 지정가 제출</button><button disabled={busy} onClick={()=>setDraft(null)}>닫기</button></div>}{outcome&&<div role="status">{outcome.status} · 주문번호 {outcome.order_no??'확인 필요'} · {outcome.message}</div>}{error&&<p role="alert">{error}</p>}<button className="border p-2" disabled={!enabled||busy} onClick={refresh}>미국 잔고·미체결 재조회</button><p>잔고 성공 조회: {holdings?formatKstDateTime(holdings.fetched_at):'미조회'} · 미체결 성공 조회: {pending?formatKstDateTime(pending.fetched_at):'미조회'}</p><p>국내 계좌와 합산하지 않습니다. 미체결은 최근 30일 주문내역 기준입니다. 조회 실패 시 이전 성공 시각을 유지합니다.</p><div className="overflow-auto"><table><thead><tr>{['종목','수량','평균 USD','현재 USD','평가 USD','손익 USD','수익률 %'].map(t=><th key={t}>{t}</th>)}</tr></thead><tbody>{holdings?.data.map(h=><tr key={h.instrument_id}><td>{h.instrument_id}</td><td>{h.quantity}</td><td>{h.avg_price}</td><td>{h.current_price}</td><td>{h.eval_amount}</td><td>{h.profit_loss}</td><td>{h.profit_rate}</td></tr>)}</tbody></table></div>{pending?.data.map(p=><p key={p.order_no}>{p.instrument_id} · {p.order_no} · {p.action} · 미체결 {p.remaining}주 · {p.price} USD <button disabled={!enabled||busy||outcome?.status==='unknown'} onClick={()=>cancel(p)}>모의 취소</button></p>)}{holdings&&holdings.data.length===0&&<p>미국 보유 종목 없음</p>}{pending&&pending.data.length===0&&<p>해당 조회 기간의 미국 미체결 없음</p>}</section>;
}
