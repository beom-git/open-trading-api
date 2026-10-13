// Integrated order flow, global mode, and account tabs. All provider responses replaced.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
for(const scenario of ['vps','prod','unknown']){
 const mode=scenario==='unknown'?'vps':scenario,page=await browser.newPage();let orders=[];
 await page.addInitScript(()=>{localStorage.setItem('kis_display_currency','KRW');localStorage.setItem('kis_selected_stocks',JSON.stringify([{code:'NASDAQ:AAPL',name:'Apple fixture'},{code:'NYSE:IBM',name:'IBM fixture'}]));});
 await page.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;let body={status:'success',data:[],logs:[]};
  if(path==='/api/auth/status')body={authenticated:true,mode,cooldown_remaining:0};
  if(path==='/api/strategies')body={strategies:[{id:'fixture',name:'Fixture strategy',category:'fixture',description:'fixture',params:[],builder_state:{metadata:{name:'Fixture strategy'}}}]};
  if(path==='/api/strategies/execute')body={status:'success',logs:[],results:[{code:'NASDAQ:AAPL',name:'Apple fixture',action:'BUY',strength:.7,reason:'fixture',currency:'USD',order_supported:true},{code:'NYSE:IBM',name:'IBM fixture',action:'SELL',strength:.7,reason:'fixture',currency:'USD',order_supported:true}]};
  if(path.startsWith('/api/market/price/'))body={status:'success',data:{price:185.25,change:1.25,change_rate:.68,currency:'USD'}};
  if(path==='/api/market/exchange-rate')body={status:'success',data:{base:'USD',quote:'KRW',rate:1400,fetched_at:new Date().toISOString(),source:'test fixture'}};
  if(path==='/api/us-stock/order'){orders.push(route.request().postDataJSON());body={status:scenario==='unknown'?'unknown':'accepted',order_no:scenario==='unknown'?undefined:'42',message:scenario==='unknown'?'fixture reconciliation required':'fixture accepted'};}
  if(path==='/api/us-stock/buyable')body={status:'success',data:{amount:10000,quantity:53}};
  if(path==='/api/us-stock/holdings')body={status:'success',mode,fetched_at:'2025-01-01T01:02:03Z',data:[{instrument_id:'NYSE:BRK/B',quantity:2,avg_price:185.25,current_price:186.01,eval_amount:372.02,profit_loss:1.52,profit_rate:.41}]};
  if(path==='/api/us-stock/pending')body={status:'success',mode,fetched_at:'2025-01-01T01:02:03Z',data:[]};
  if(path==='/api/account/balance')body={status:'success',data:{deposit:10000,total_eval:10000,purchase_amount:0,eval_amount:0,profit_loss:0},logs:[]};
  if(path==='/api/orders/pending')body={status:'success',orders:[]};
  await route.fulfill({json:body});
 });
 await page.goto((process.env.APP_URL||'http://127.0.0.1:3100')+'/execute');
 assert.equal(await page.getByRole('link',{name:'미국 모의투자',exact:true}).count(),0);
 await page.getByRole('tab',{name:'미국 주식',exact:true}).click();await page.getByRole('button',{name:'미국 잔고·미체결 재조회',exact:true}).click();await page.getByText('NYSE:BRK/B',{exact:true}).waitFor();
 await page.getByRole('button',{name:'전략 선택',exact:true}).click();await page.getByText('Fixture strategy',{exact:true}).click();await page.getByRole('button',{name:'시그널 생성',exact:true}).click();await page.getByRole('button',{name:'Apple fixture 매수 시그널',exact:true}).click();
 await page.getByRole('button',{name:'주문 확인',exact:true}).click();const dialog=page.getByRole('dialog',{name:'주문 확인',exact:true});await dialog.waitFor();
 assert.match(await dialog.innerText(),new RegExp(`설정 모드: ${mode==='vps'?'모의투자':'실전투자'}`));assert(await dialog.getByRole('button',{name:'시장가',exact:true}).isDisabled());
 await dialog.getByLabel('지정가',{exact:true}).fill('185.25');await dialog.getByLabel('주문 수량',{exact:true}).fill('2');await dialog.getByText('실제 제출은 USD입니다.',{exact:false}).waitFor();
 await dialog.getByRole('button',{name:'매수 주문',exact:true}).click();await page.getByRole('dialog',{name:'주문 결과',exact:true}).waitFor();
 assert.equal(orders.length,1);assert.equal(orders[0].price,'185.25');assert.equal(orders[0].currency,'USD');assert.equal(orders[0].quantity,2);
 if(scenario==='unknown'){assert(await page.getByText('접수 확인 필요',{exact:true}).isVisible());assert.equal(await page.getByText('주문 실패',{exact:true}).count(),0);}
 else assert(await page.getByText('주문 접수',{exact:true}).isVisible());
 await page.getByRole('button',{name:'확인',exact:true}).click();
 assert(await page.getByRole('tab',{name:'미국 주식',exact:true}).getAttribute('aria-selected')==='true');
 await page.getByRole('button',{name:'IBM fixture 매도 시그널',exact:true}).click();assert(await page.getByText('NYSE:BRK/B',{exact:true}).isVisible());
 assert.equal(await page.locator('[aria-label="미국 계좌 잔고·미체결"]').count(),1);
 await page.reload();await page.getByRole('tab',{name:'미국 주식',exact:true}).waitFor();await page.waitForTimeout(100);assert.equal(await page.getByRole('tab',{name:'미국 주식',exact:true}).getAttribute('aria-selected'),'true');
 await page.setViewportSize({width:390,height:844});assert(await page.getByRole('tab',{name:'미국 주식',exact:true}).isVisible());await page.close();
}await browser.close();console.log('PASS integrated orders: global paper/live mode, USD/KRW, shared confirmation/result, unknown, independent account tabs, persistence/mobile');
})().catch(e=>{console.error(e);process.exit(1)});
