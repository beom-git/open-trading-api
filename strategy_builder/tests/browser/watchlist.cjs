const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const page=await browser.newPage();let quoteCalls=0,signalCalls=0,orders=0,fail=false,basis='20250102';
await page.addInitScript(()=>localStorage.setItem('kis_display_currency','KRW'));
await page.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;let body={status:'success',data:[]};
if(path==='/api/auth/status')body={authenticated:true,mode:'vps',cooldown_remaining:0};
if(path==='/api/strategies')body={strategies:[{id:'fixture',name:'Fixture strategy',builder_state:{metadata:{name:'Fixture strategy'}}}]};
if(path==='/api/market/exchange-rate')body={status:'success',data:{base:'USD',quote:'KRW',rate:1400,fetched_at:new Date().toISOString(),source:'test fixture'}};
if(path.includes('/orders/')||path.includes('/us-paper/order')||path.includes('/us-stock/order'))orders++;
if(path.startsWith('/api/watchlist/quote/')){quoteCalls++;if(fail){await route.fulfill({status:502,json:{detail:'offline fixture'}});return;}body={instrument_id:decodeURIComponent(path.split('/quote/')[1]),currency:'USD',data:{price:185.25,change_rate:1.25},fetched_at:'2025-01-02T01:02:03Z',provider_time:null,market_status:'unknown'};}
if(path==='/api/watchlist/signal'){signalCalls++;const request=route.request().postDataJSON();body={instrument_id:request.instrument_id,action:'BUY',basis_date:basis,signal_id:request.instrument_id+':fixture:'+basis,strategy_name:'Fixture strategy',fetched_at:'2025-01-02T01:02:03Z',indicators:{'ma(2)':184.7},buy:{left:185.25,operator:'>',right:184.7,satisfied:true},sell:null,limitation:'closed daily test fixture'};}
await route.fulfill({json:body});});
await page.goto((process.env.APP_URL||'http://127.0.0.1:3100')+'/watchlist');await page.getByLabel('적용 전략',{exact:true}).selectOption('fixture');
for(const id of ['NASDAQ:ABC','NYSE:ABC','KOSPI:005930']){await page.getByLabel('관심 종목 ID',{exact:true}).fill(id);await page.getByRole('button',{name:'관심 종목 추가',exact:true}).click();}
assert.equal(await page.locator('article').count(),3);await page.reload();await page.locator('article').nth(2).waitFor();assert.equal(await page.locator('article').count(),3);
await page.getByRole('button',{name:'시작',exact:true}).click();await page.getByRole('article',{name:'NASDAQ:ABC',exact:true}).getByText('259,350 KRW',{exact:false}).waitFor();
await page.getByRole('button',{name:'일시정지',exact:true}).click();const count=quoteCalls;await page.waitForTimeout(200);assert.equal(quoteCalls,count);
await page.getByRole('button',{name:'수동 새로고침',exact:true}).click();await page.waitForTimeout(200);assert.equal(await page.getByText('새 매매 시그널',{exact:false}).count(),0);
basis='20250103';await page.getByRole('button',{name:'수동 새로고침',exact:true}).click();await page.getByRole('article',{name:'NASDAQ:ABC',exact:true}).getByText('새 매매 시그널',{exact:false}).waitFor();
await page.getByRole('button',{name:'NASDAQ:ABC · NASDAQ:ABC',exact:true}).click();await page.getByRole('region',{name:'시그널 판단 근거'}).getByText('184.7',{exact:false}).waitFor();
fail=true;await page.getByRole('button',{name:'수동 새로고침',exact:true}).click();await page.getByRole('article',{name:'NASDAQ:ABC',exact:true}).getByText('시세 갱신 지연:',{exact:false}).waitFor();assert(await page.getByRole('article',{name:'NASDAQ:ABC',exact:true}).getByText('2025-01-02 10:02:03 KST',{exact:false}).count()>0);
fail=false;await page.getByRole('button',{name:'수동 새로고침',exact:true}).click();await page.waitForTimeout(200);assert.equal(await page.getByRole('article',{name:'NASDAQ:ABC',exact:true}).getByRole('alert').count(),0);
await page.getByRole('button',{name:'NYSE:ABC 삭제',exact:true}).click();await page.reload();await page.locator('article').nth(1).waitFor();assert.equal(await page.locator('article').count(),2);assert.equal(await page.getByRole('article',{name:'NYSE:ABC',exact:true}).count(),0);
await page.setViewportSize({width:390,height:844});assert(await page.getByRole('heading',{name:'관심 종목 자동 갱신',exact:true}).isVisible());assert.equal(orders,0);assert(quoteCalls>0&&signalCalls>0);
await browser.close();console.log('PASS watchlist browser: persistence/exchange IDs, pause/manual, USD/KRW, dedup/new evidence, failure/recovery, delete, mobile, zero orders');
})().catch(e=>{console.error(e);process.exit(1)});
