"use client";
import {useState} from "react";
import {USPaperPanel} from "@/components/execute/USPaperPanel";
export default function Page(){const [input,setInput]=useState('NASDAQ:AAPL'),[id,setId]=useState('NASDAQ:AAPL');return <main className="max-w-5xl p-4 mx-auto"><h1>미국 모의투자</h1><label>종목 ID<input value={input} onChange={e=>setInput(e.target.value)}/></label><button onClick={()=>setId(input.trim().toUpperCase())}>선택</button><USPaperPanel instrumentId={id}/></main>}
