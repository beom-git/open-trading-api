const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 for(const mode of ['vps','prod']){
 const page=await browser.newPage();let orders=[];
 await page.addInitScript(()=>localStorage.setItem('kis_display_currency','KRW'));
 await page.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;let body={status:'success',data:[]};
 if(path==='/api/auth/status')body={authenticated:true,mode,cooldown_remaining:0};
 if(path==='/api/market/exchange-rate')body={status:'success',data:{base:'USD',quote:'KRW',rate:1400,fetched_at:new Date().toISOString(),source:'test fixture'}};
 if(path==='/api/us-paper/order'){orders.push(route.request().postDataJSON());body={status:'accepted',order_no:'42',message:'fixture accepted'};}
 if(path==='/api/us-paper/holdings')body={status:'success',fetched_at:'2025-01-01T01:02:03Z',data:[{instrument_id:'NYSE:BRK/B',quantity:2,avg_price:185.25,current_price:186.01,eval_amount:372.02,profit_loss:1.52,profit_rate:.41}]};
 if(path==='/api/us-paper/pending')body={status:'success',fetched_at:'2025-01-01T01:02:03Z',data:[]};
 await route.fulfill({json:body});});
 await page.goto((process.env.APP_URL||'http://127.0.0.1:3100')+'/paper');
 const confirm=page.getByRole('button',{name:'모의 주문 확인',exact:true});
 if(mode==='prod'){assert(await confirm.isDisabled());assert.equal(orders.length,0);await page.close();continue;}
 await page.getByLabel('지정가 USD',{exact:true}).fill('185.25');await page.getByLabel('모의 수량',{exact:true}).fill('2');
 await confirm.click();await page.getByRole('dialog',{name:'미국 모의 주문 확인'}).waitFor();
 assert.match(await page.getByRole('dialog').innerText(),/370.5000 USD/);
 await page.getByText('실제 제출은 USD입니다.',{exact:false}).waitFor();
 await page.getByRole('button',{name:'모의 지정가 제출'}).click();await page.getByText('fixture accepted',{exact:false}).waitFor();
 assert.equal(orders.length,1);assert.equal(orders[0].price,'185.25');assert.equal(orders[0].currency,'USD');assert.equal(orders[0].quantity,2);
 await page.getByRole('button',{name:'미국 잔고·미체결 재조회'}).click();await page.getByText('NYSE:BRK/B',{exact:true}).waitFor();
 await page.getByText('2025-01-01 10:02:03 KST',{exact:false}).waitFor();
 await page.setViewportSize({width:390,height:844});assert(await confirm.isVisible());await page.close();
 }await browser.close();console.log('PASS paper browser: confirmation, KRW reference/USD payload, result, balance, live guard, mobile');
})().catch(e=>{console.error(e);process.exit(1)});
