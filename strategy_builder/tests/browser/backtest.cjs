// Run with NODE_PATH pointing to a Playwright installation and the app at APP_URL.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage();
 let submitted;
 const decision=(date,action,left,right)=>({date,action,indicators:{'ma(2)':right},buy:{left_label:'close',left,operator:'>',right_label:'ma(2)',right,satisfied:action==='BUY'},sell:null});
 const fill={action:'BUY',signal_date:'20250102',execution_date:'20250103',price:10.25,quantity:9,cost:.9225,decision_index:0};
 const result={strategy_name:'Fixture strategy',points:[{date:'20250102',close:10,equity:100,benchmark:100,drawdown:0},{date:'20250103',close:11,equity:105,benchmark:110,drawdown:0}],decisions:[decision('20250102','BUY',10,9.5),decision('20250103','HOLD',11,11)],fills:[fill],trades:[{entry:fill,exit:{...fill,execution_date:'20250106',price:12.75},profit_loss:20.43}],total_return_pct:.2043,max_drawdown:0,total_trades:1,win_rate:1,final_equity:120.43,metadata:{source:'Test fixture only',adjusted:true,actual_start:'20250102',actual_end:'20250103',warning:'Completeness unverified'}};
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  let body={authenticated:false,mode:'vps'};
  if(path==='/api/strategies')body={strategies:[{id:'fixture',name:'Fixture strategy',builder_state:{metadata:{name:'Fixture strategy'}}}]};
  if(path==='/api/backtest'){submitted=route.request().postDataJSON();body=result;}
  await route.fulfill({json:body});
 });
 await page.goto((process.env.APP_URL||'http://127.0.0.1:3100')+'/backtest');
 await page.getByLabel('전략',{exact:true}).selectOption('fixture');
 await page.getByLabel('시작일',{exact:true}).fill('2025-01-02');
 await page.getByLabel('종료일',{exact:true}).fill('2025-01-06');
 await page.getByRole('button',{name:'백테스트 실행',exact:true}).click();
 await page.getByText('총수익률 20.43%',{exact:false}).waitFor();
 assert.equal(submitted.instrument_id,'NASDAQ:AAPL');
 assert.equal(submitted.initial_cash,10000);
 await page.getByRole('button',{name:'20250103 10.25',exact:true}).click();
 assert.match(await page.getByRole('region',{name:'매매 근거'}).innerText(),/close 10 > ma\(2\) 9.5 → 충족/);
 assert.match(await page.getByRole('region',{name:'매매 근거'}).innerText(),/수수료 0.9225 USD/);
 assert(await page.locator('.recharts-line').count()>=4);
 await page.getByLabel('확대 시작',{exact:true}).fill('1');
 await page.setViewportSize({width:390,height:844});
 assert(await page.getByRole('heading',{name:'미국 주식 백테스트 · 전략 해석'}).isVisible());
 await browser.close();console.log('PASS browser backtest: request, backend values, trade evidence, zoom, mobile');
})().catch(e=>{console.error(e);process.exit(1)});
