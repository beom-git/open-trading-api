"use client";
import {useState,useCallback,useRef} from "react";
import {executeOrder} from "@/lib/api";
import {apiPost} from "@/lib/api/client";
import {isUSInstrument} from "@/lib/instruments";
import {useAuth} from "./useAuth";
import type {OrderRequest,OrderResult} from "@/types/order";
import type {LogEntry} from "@/types/signal";
export function useOrder(){
 const {status}=useAuth();const auth=useRef(status);auth.current=status;
 const [result,setResult]=useState<OrderResult|null>(null),[logs,setLogs]=useState<LogEntry[]>([]),[isLoading,setIsLoading]=useState(false),[error,setError]=useState<string|null>(null);
 const lock=useRef(false);
 const execute=useCallback(async(request:OrderRequest):Promise<OrderResult>=>{
  const us=isUSInstrument(request.stock_code);
  if(lock.current)return {status:'unknown',message:'이전 주문 접수 확인 중입니다'};
  lock.current=true;setIsLoading(true);setError(null);setResult(null);setLogs([]);
  let outcome:OrderResult;
  try{
   if(us){
    if(!auth.current.authenticated)throw Error('설정에서 인증이 필요합니다');
    if(request.order_type!=='limit')throw Error('미국 주문은 지정가를 선택하세요');
    if(sessionStorage.getItem('kis_us_paper_unresolved')){outcome={status:'unknown',currency:'USD',message:'이전 주문 접수 여부를 계좌에서 확인하세요. 자동 재전송하지 않습니다.'};}
    else{
     const request_id=crypto.randomUUID();
     sessionStorage.setItem('kis_us_paper_unresolved',JSON.stringify({request_id,status:'unknown'}));
     try{const response=await apiPost<{status:string;order_no?:string;message:string}>('/api/us-stock/order',{request_id,instrument_id:request.stock_code,action:request.action,quantity:request.quantity,price:String(request.price),currency:'USD'});
      outcome={status:response.status==='accepted'?'success':response.status==='unknown'?'unknown':'error',order_id:response.order_no,message:response.message,currency:'USD'};
      if(response.status!=='unknown')sessionStorage.removeItem('kis_us_paper_unresolved');
     }catch{outcome={status:'unknown',currency:'USD',message:'접수 여부를 확인할 수 없습니다. 계좌 주문내역을 재조회하세요. 자동 재전송하지 않습니다.'};}
     window.dispatchEvent(new Event('kis-us-account-dirty'));
    }
   }else{const response=await executeOrder(request);setLogs(response.logs);outcome={status:response.status,order_id:response.data?.order_id,message:response.message};}
  }catch(e){outcome={status:'error',message:e instanceof Error?e.message:'주문 실행 오류',currency:us?'USD':'KRW'};}
  finally{lock.current=false;setIsLoading(false);}
  setResult(outcome);if(outcome.status!=='success')setError(outcome.message);return outcome;
 },[]);
 const reset=useCallback(()=>{setResult(null);setLogs([]);setError(null)},[]);
 return {result,logs,isLoading,error,execute,reset};
}
export default useOrder;
