"use client";
import {useEffect,useRef,useState} from "react";
import Link from "next/link";
import {useAuth} from "@/hooks";
import {useLocalStrategies} from "@/hooks/useLocalStrategies";
import {useCurrency} from "@/contexts/CurrencyContext";
import {SymbolSearch} from "@/components/symbols/SymbolSearch";
import {apiGet,apiPost} from "@/lib/api/client";
import {formatKstDateTime} from "@/lib/currency";
import {RefreshLoop,signalIsNew} from "@/lib/refresh-loop";
import type {BuilderState} from "@/types/builder";
type Item={id:string;name:string;strategyId:string};
type Quote={instrument_id:string;currency:string;data:{price:number;change_rate:number};fetched_at:string;provider_date:string|null;provider_time:string|null;market_status:string};
type Signal={instrument_id:string;action:string;basis_date:string;signal_id:string;strategy_name:string;fetched_at:string;indicators:Record<string,number|null>;buy:unknown;sell:unknown;limitation:string};
type Row={quote?:Quote;signal?:Signal;quoteError?:string;signalError?:string;highlight?:boolean};
const KEY='kis_watchlist_v1',CONFIG='kis_watchlist_settings_v1',SIGNALS='kis_watchlist_signal_ids_v1';
function normalize(id:string){let v=id.trim().toUpperCase();if(/^[0-9][A-Z0-9]{5}$/.test(v))v='KRX:'+v;if(!/^(KOSPI|KOSDAQ|KRX):[A-Z0-9]{6}$/.test(v)&&!/^(NASDAQ|NYSE|AMEX):[A-Z0-9][A-Z0-9./-]{0,19}$/.test(v))throw Error('공통 종목 ID 형식이 필요합니다');if(v.includes('..'))throw Error('잘못된 티커');return v;}
export default function WatchlistPage(){
 const {status}=useAuth(),local=useLocalStrategies(),currency=useCurrency();
 const [items,setItems]=useState<Item[]>([]),[strategies,setStrategies]=useState<{id:string;name:string;builder_state:BuilderState}[]>([]);
 const [input,setInput]=useState(''),[selectedStrategy,setSelectedStrategy]=useState(''),[running,setRunning]=useState(false),[quoteSeconds,setQuoteSeconds]=useState(30),[signalSeconds,setSignalSeconds]=useState(60),[ready,setReady]=useState(false);
 const [rows,setRows]=useState<Record<string,Row>>({}),[states,setStates]=useState<Record<string,{state:string;next:number|null}>>({}),[error,setError]=useState(''),[detail,setDetail]=useState<string|null>(null),[now,setNow]=useState(Date.now());
 const loops=useRef<RefreshLoop<unknown>[]>([]),lastSignal=useRef<Record<string,string>>({});
 const choices=[...strategies,...local.strategies.map(s=>({id:'local_'+s.id,name:s.name,builder_state:s.state}))];
 useEffect(()=>{try{
  const saved=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(saved)||saved.length>20)throw Error('저장된 관심 목록 형식 오류');
  const validated=saved.map((i:Item)=>({id:normalize(i.id),name:String(i.name),strategyId:String(i.strategyId)}));setItems(Array.from(new Map(validated.map(i=>[i.id,i])).values()));
  const config=JSON.parse(localStorage.getItem(CONFIG)||'{}');setQuoteSeconds(Math.min(3600,Math.max(30,Number(config.quoteSeconds)||30)));setSignalSeconds(Math.min(3600,Math.max(60,Number(config.signalSeconds)||60)));setRunning(config.running===true);
  const signals=JSON.parse(localStorage.getItem(SIGNALS)||'{}');if(signals&&typeof signals==='object'&&!Array.isArray(signals))lastSignal.current=signals;
 }catch(e){setError(`저장 복원 실패: ${String(e)}`);}setReady(true);
 apiGet<{strategies:typeof strategies}>('/api/strategies').then(r=>setStrategies(r.strategies)).catch(e=>setError(String(e)));
 const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);
 },[]);
 function save(next:Item[]){setItems(next);try{localStorage.setItem(KEY,JSON.stringify(next));}catch{setError('목록을 저장하지 못했습니다. 브라우저 저장소를 확인하세요.');}}
 function add(id=input,name=id){try{const value=normalize(id);if(items.some(i=>i.id===value))throw Error('이미 등록된 종목입니다');if(items.length>=20)throw Error('최대 20종목입니다');if(!selectedStrategy)throw Error('적용할 전략을 선택하세요');save([...items,{id:value,name,strategyId:selectedStrategy}]);setInput('');setError('');}catch(e){setError(String(e));}}
 useEffect(()=>{if(!ready)return;try{localStorage.setItem(CONFIG,JSON.stringify({running,quoteSeconds,signalSeconds}));}catch{setError('갱신 설정 저장 실패');}},[ready,running,quoteSeconds,signalSeconds]);
 // A separate generation is created whenever selection, strategy definition or auth mode changes.
 const signature=JSON.stringify(choices.map(s=>[s.id,s.builder_state]));
 useEffect(()=>{
  if(!ready||!status.authenticated)return;
  const list:RefreshLoop<unknown>[]=[];
  const definitions=JSON.parse(signature) as [string,BuilderState][];
  const state=(key:string)=>(value:string,next:number|null)=>setStates(prev=>({...prev,[key]:{state:value,next}}));
  for(const item of items){
   const quote=new RefreshLoop<Quote>(abort=>apiGet(`/api/watchlist/quote/${encodeURIComponent(item.id)}`,abort),Math.max(quoteSeconds,items.length*2)*1000,
    value=>setRows(prev=>({...prev,[item.id]:{...prev[item.id],quote:value,quoteError:undefined}})),
    e=>setRows(prev=>({...prev,[item.id]:{...prev[item.id],quoteError:String(e)}})),state(item.id+':quote'));
   const definition=definitions.find(s=>s[0]===item.strategyId)?.[1];
   const signal=new RefreshLoop<Signal>(abort=>apiPost('/api/watchlist/signal',{instrument_id:item.id,strategy_id:item.strategyId,builder_state:definition},abort),Math.max(signalSeconds,items.length*10)*1000,
    value=>{const key=item.id+':'+item.strategyId;const fresh=signalIsNew(lastSignal.current[key],value.signal_id)&&['BUY','SELL'].includes(value.action);lastSignal.current[key]=value.signal_id;try{localStorage.setItem(SIGNALS,JSON.stringify(lastSignal.current));}catch{}setRows(prev=>({...prev,[item.id]:{...prev[item.id],signal:value,signalError:undefined,highlight:fresh||prev[item.id]?.highlight}}));},
    e=>setRows(prev=>({...prev,[item.id]:{...prev[item.id],signalError:String(e)}})),state(item.id+':signal'));
   for(const loop of [quote,signal]){loop.setVisible(document.visibilityState==='visible');if(running)loop.start();list.push(loop as RefreshLoop<unknown>);}
  }
  loops.current=list;
  const visibility=()=>list.forEach(loop=>loop.setVisible(document.visibilityState==='visible'));
  document.addEventListener('visibilitychange',visibility);
  return()=>{list.forEach(loop=>loop.dispose());document.removeEventListener('visibilitychange',visibility);loops.current=[];};
 },[ready,status.authenticated,status.mode,items,running,quoteSeconds,signalSeconds,signature]);
 useEffect(()=>{setRows({});setStates({});},[status.mode,status.authenticated]);
 const amount=(q:Quote)=>{const krw=q.currency==='USD'&&currency.displayCurrency==='KRW'&&currency.usableRate!==null;return `${(q.data.price*(krw?currency.usableRate!:1)).toLocaleString(krw?'ko-KR':'en-US',{maximumFractionDigits:krw?0:4})} ${krw?'KRW':q.currency}`;};
 const current=detail?rows[detail]?.signal:undefined;
 return <main className="max-w-6xl mx-auto p-4 space-y-4"><h1 className="text-2xl">관심 종목 자동 갱신</h1><p>시세 감시와 완성 일봉 전략 판단. 오늘 진행 중인 봉 제외 · 자동 주문 없음.</p><p>미국 현지 시각 {new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',dateStyle:'short',timeStyle:'long'}).format(new Date(now))} · 시장 상태: 알 수 없음 (휴장·조기 폐장 달력 미연결)</p><div className="flex flex-wrap gap-3"><label>적용 전략<select aria-label="적용 전략" value={selectedStrategy} onChange={e=>setSelectedStrategy(e.target.value)}><option value="">선택</option>{choices.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label>관심 종목 ID<input aria-label="관심 종목 ID" value={input} onChange={e=>setInput(e.target.value)} placeholder="KOSPI:005930 / NASDAQ:AAPL"/></label><button onClick={()=>add()}>관심 종목 추가</button><SymbolSearch onSelect={s=>add(s.id,s.name)}/></div><div className="flex flex-wrap gap-3"><label>시세 간격 초<input aria-label="시세 간격 초" type="number" min={30} max={3600} value={quoteSeconds} onChange={e=>setQuoteSeconds(Math.min(3600,Math.max(30,Number(e.target.value)||30)))}/></label><label>시그널 간격 초<input aria-label="시그널 간격 초" type="number" min={60} max={3600} value={signalSeconds} onChange={e=>setSignalSeconds(Math.min(3600,Math.max(60,Number(e.target.value)||60)))}/></label><button disabled={!status.authenticated||running} onClick={()=>setRunning(true)}>시작</button><button disabled={!running} onClick={()=>setRunning(false)}>일시정지</button><button disabled={!status.authenticated} onClick={()=>loops.current.forEach(loop=>loop.manual())}>수동 새로고침</button></div><p>실제 최소 간격: 시세 {Math.max(quoteSeconds,items.length*2)}초 · 시그널 {Math.max(signalSeconds,items.length*10)}초. 동일 요청 캐시 · 실패 시 지수 지연, 5회 연속 실패 시 자동 중지.</p>{!status.authenticated&&<p>설정에서 KIS 인증이 필요합니다</p>}{error&&<p role="alert">{error}</p>}{items.length===0&&<p>관심 종목을 추가하세요</p>}{items.map(item=>{const row=rows[item.id]||{},q=row.quote,s=row.signal;const stale=!!q&&(!!row.quoteError||now-Date.parse(q.fetched_at)>Math.max(quoteSeconds,items.length*2)*2000);return <article key={item.id} aria-label={item.id} className={`border rounded p-4 space-y-2 ${row.highlight?'bg-amber-100 dark:bg-amber-900':''}`}><div className="flex flex-wrap gap-3"><button onClick={()=>{setDetail(item.id);setRows(prev=>({...prev,[item.id]:{...prev[item.id],highlight:false}}));}}>{item.name} · {item.id}</button><button aria-label={`${item.id} 삭제`} onClick={()=>{save(items.filter(i=>i.id!==item.id));setRows(prev=>{const next={...prev};delete next[item.id];return next;});}}>삭제</button><select aria-label={`${item.id} 전략`} value={item.strategyId} onChange={e=>{save(items.map(i=>i.id===item.id?{...i,strategyId:e.target.value}:i));setRows(prev=>({...prev,[item.id]:{...prev[item.id],signal:undefined,signalError:undefined,highlight:false}}));}}>{choices.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div><p>{q?`${amount(q)} · ${q.data.change_rate.toFixed(2)}%`:'시세 미조회'} {stale&&'· 오래된 데이터'} {row.highlight&&'· 새 매매 시그널'}</p>{q&&currency.displayCurrency==='KRW'&&q.currency==='USD'&&currency.usableRate!==null&&<p>원 시세 {q.data.price} USD · 환율 {currency.usableRate} · {currency.exchangeRate&&formatKstDateTime(currency.exchangeRate.fetched_at)}</p>}<p>시세 조회 성공 {q?formatKstDateTime(q.fetched_at):'없음'} · 공급자 시세 발생 {q?.provider_date||q?.provider_time?`${q.provider_date??''} ${q.provider_time??''}`:'미제공'}</p><p>최근 판단 {s?.action??'미조회'} · 발생 기준 {s?.basis_date??'없음'} 거래소 일봉 날짜 · 시그널 조회 성공 {s?formatKstDateTime(s.fetched_at):'없음'}</p>{['quote','signal'].map(kind=>{const t=states[item.id+':'+kind];return <p key={kind}>{kind==='quote'?'시세':'시그널'}: {t?.state??'일시정지'} {t?.next&&`· 다음 ${formatKstDateTime(new Date(t.next).toISOString())}`}</p>;})}{row.quoteError&&<p role="alert">시세 갱신 지연: {row.quoteError}</p>}{row.signalError&&<p role="alert">시그널 갱신 지연: {row.signalError}</p>}{/^(NASDAQ|NYSE|AMEX):/.test(item.id) && <Link href={`/backtest?instrument_id=${encodeURIComponent(item.id)}&strategy_id=${encodeURIComponent(item.strategyId)}`}>전략 해석 그래프 열기</Link>}</article>;})}{current&&<section aria-label="시그널 판단 근거" className="border p-4"><h2>{current.strategy_name} · {current.basis_date} · {current.action}</h2><p>{current.limitation}</p><pre className="overflow-auto">{JSON.stringify({indicators:current.indicators,buy:current.buy,sell:current.sell},null,2)}</pre></section>}</main>;
}
