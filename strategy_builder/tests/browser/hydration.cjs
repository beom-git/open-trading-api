// Delay client scripts so SSR/client clocks differ, and inject extension attributes before hydration.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const base=process.env.APP_URL||'http://127.0.0.1:3101';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 for(const scenario of ['extension-root','watchlist-clock','app-subtree']){
  const page=await browser.newPage({timezoneId:'Pacific/Honolulu'});const errors=[];
  page.on('console',m=>{if(/hydration|hydrated|server rendered|server-rendered/i.test(m.text()))errors.push(m.text());});
  page.on('pageerror',e=>{if(/hydration|hydrated|server rendered|server-rendered/i.test(e.message))errors.push(e.message);});
  await page.route('**/api/**',route=>route.fulfill({json:new URL(route.request().url()).pathname==='/api/auth/status'?{authenticated:false,mode:'vps',cooldown_remaining:0}:{strategies:[],status:'success',data:[]}}));
  let release;const gate=new Promise(resolve=>release=resolve);
  await page.route('**/_next/**',async route=>{if(new URL(route.request().url()).pathname.endsWith('.js'))await gate;await route.continue();});
  const path=scenario==='watchlist-clock'?'/watchlist':'/builder';
  await page.goto(base+path,{waitUntil:'commit'});
  await page.waitForFunction(()=>!!document.querySelector('main h1'));
  if(scenario==='extension-root')await page.evaluate(()=>{
   for(const [key,value] of Object.entries({'data-be-installed':'true','data-liner-highlight-ready':'true','suppresshydrationwarning':'true','data-lt-installed':'true'}))document.documentElement.setAttribute(key,value);
   document.documentElement.style.width='100%';document.body.setAttribute('data-liner-extension-version','7.18.44');
  });
  if(scenario==='app-subtree')await page.evaluate(()=>{document.querySelector('main h1').setAttribute('data-test-unexpected','true');});
  if(scenario==='watchlist-clock')await page.waitForTimeout(2100);
  const hydrated=page.waitForResponse(response=>new URL(response.url()).pathname==='/api/auth/status');
  release();await hydrated;await page.waitForTimeout(300);
  const shouldMismatch=scenario==='app-subtree'||process.env.EXPECT_MISMATCH==='1';
  if(shouldMismatch)assert(errors.length>0,`${scenario}: regression must detect mismatch`);
  else assert.deepEqual(errors,[],`${scenario}: hydration must be clean`);
  console.log(`${scenario}: ${errors.length?'mismatch detected':'clean hydration'}`);
  await page.close();
 }
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
