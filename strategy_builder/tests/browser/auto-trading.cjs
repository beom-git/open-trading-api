const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:844}});let external=0,starts=0,previews=0;
  let state={config:{instrument_id:'NASDAQ:AAPL',strategy_id:'golden_cross',buy_percent:'10',sell_percent:'100',buy_offset_percent:'0.1',sell_offset_percent:'0.1',cancel_seconds:300},running:false,current_mode:'vps',authenticated:true,reason:'사용자 시작 대기',heartbeat:new Date().toISOString(),last_success:null,next_run:null,owned:4,manual:7,fetched_at:'2026-10-14T15:00:00Z',preview:null,decision:{action:'BUY',basis_date:'20261013',indicators:{'ma(5)':100},buy:{left_label:'ma(5)',left:100,operator:'crosses_above',right_label:'ma(20)',right:99,previous:{left:98,right:99},satisfied:true},sell:null},orders:[{id:'fixture',created_at:'2026-10-14T15:00:00Z',basis_date:'20261013',action:'BUY',quantity:9,filled:4,price:'100.10',status:'partial',order_no:'42',cancel_at:'2026-10-14T15:05:00Z',provider_date:'20261014',provider_time:'110000'}],signals:[{basis_date:'20261013',action:'BUY',outcome:'accepted'}]};
  await page.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;let body={status:'success',data:[]};
   if(path==='/api/auth/status')body={authenticated:true,mode:'vps',paper_only:true,can_switch_mode:false,cooldown_remaining:0};
   if(path==='/api/symbols/status')body={exchanges:[],total_count:0,kospi_count:0,kosdaq_count:0,needs_update:false};
   if(path.includes('/order')||path.includes('/cancel'))external++;
   if(path.startsWith('/api/auto-trading')){
    if(path.endsWith('/settings')){state.config=route.request().postDataJSON();state.preview=null;}
    if(path.endsWith('/start')){assert.equal(route.request().postDataJSON().mode,'vps');starts++;state.running=true;state.reason=null;state.next_run='2026-10-14T15:01:00Z';}
    if(path.endsWith('/stop')){state.running=false;state.reason='사용자 중지';}
    if(path.endsWith('/preview')){previews++;state.preview={available_usd:'10000',provider_max_quantity:100,budget_usd:'2000',spendable_usd:'1980.198',fee_reserve_usd:'19.802',quantity:19,limit_price_usd:'100.10',total_usd:'1901.90',action:'BUY',provider_at:'2026-10-14T15:00:00Z',fetched_at:'2026-10-14T15:00:01Z',sell:{quantity:2,limit_price_usd:'99.90',total_usd:'199.80'}};}
    body=path.endsWith('/verify')?{ready:false,order_ready:false,fetched_at:'2026-10-14T15:00:01Z',checks:{authentication:{status:'passed'},daily_signal:{status:'passed'},holdings:{status:'failed',message:'90070000: 모의 계좌와 사용자정보 불일치',remedy:'my_paper_stock 확인'},buyable:{status:'failed',message:'90070000'}}}:state;
   }
   await route.fulfill({json:body});
  });
  await page.goto((process.env.APP_URL||'http://127.0.0.1:3100')+'/auto-trading');
  await page.getByRole('button',{name:'모의 연결 검증',exact:true}).click();await page.getByRole('region',{name:'모의 연결 검증'}).getByText('my_paper_stock 확인',{exact:false}).waitFor();
  await page.getByRole('button',{name:'설정 열기',exact:true}).click();assert(await page.getByRole('button',{name:'실전투자 (서버에서 차단)',exact:true}).isDisabled());await page.getByRole('button',{name:'설정 닫기',exact:true}).click();
  const buy=page.getByLabel('매수 비율 (%)',{exact:true}),sell=page.getByLabel('자동매매 보유분 매도 비율 (%)',{exact:true});
  await buy.fill('20');await sell.fill('50');assert(await page.getByRole('button',{name:'모의 자동매매 시작',exact:true}).isDisabled());
  await page.getByRole('button',{name:'설정 저장',exact:true}).click();await page.getByRole('button',{name:'모의 자동매매 시작',exact:true}).isEnabled();
  await page.getByRole('button',{name:'주문 가능 금액 조회',exact:true}).click();await page.getByText('10,000.00 USD',{exact:true}).waitFor();
  assert.equal(state.config.buy_percent,'20');assert.equal(state.config.sell_percent,'50');assert.equal(previews,1);
  await page.getByText('부분 체결',{exact:true}).waitFor();await page.getByText('2026-10-15 00:00:00 KST',{exact:true}).first().waitFor();
  await page.getByRole('button',{name:'모의 자동매매 시작',exact:true}).click();await page.getByText('전체 모드: 모의투자 · 실행 중',{exact:true}).waitFor();assert(await buy.isDisabled());assert.equal(starts,1);
  await page.getByRole('button',{name:'중지',exact:true}).click();await page.getByText('전체 모드: 모의투자 · 중지',{exact:true}).waitFor();assert(await buy.isEnabled());
  assert.equal(external,0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'horizontal overflow');
  await page.screenshot({path:`/tmp/auto-trading-${width}.png`,fullPage:true});await page.close();
 }
 await browser.close();console.log('PASS auto-trading desktop/mobile: settings, mode-confirmed start/stop, funds, evidence, partial-fill history, KST, no external order calls');
})().catch(e=>{console.error(e);process.exit(1)});
