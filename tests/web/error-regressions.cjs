/* Offline error contexts: all API responses are injected. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
 const page=await browser.newPage({viewport:{width:375,height:812}});
 let code='history_incomplete', status=503, release;
 const city={id:'munich',zh:'慕尼黑',name:'München',state:'Bayern'};
 await page.route('**/api/context?*',r=>r.fulfill({json:{today:'2026-10-16',forecast_end:'2026-10-29',max_date:'2026-11-14',fixture_mode:false}}));
 await page.route('**/api/cities?*',r=>r.fulfill({json:{cities:[city]}}));
 await page.route('**/api/city?*',r=>r.fulfill({status:status===400?400:200,json:status===400?{error:'请选择可确认的德国城市。',code:'invalid_request'}:{city}}));
 await page.route('**/api/featured?*',r=>r.fulfill({status:503,json:{error:'暂不可用'}}));
 await page.route('**/api/advice?*',async r=>{await new Promise(resolve=>release=resolve);await r.fulfill({status,json:{code,error:code==='history_incomplete'?'这个查询的过去五年同期历史资料尚未齐备。':'服务暂不可用，请重试。'}})});
 const open=async(end,id='munich')=>{release=null;await page.goto(`${process.env.UI_BASE_URL||'http://127.0.0.1:8002'}/?view=trip&city_id=${id}&start=2026-10-20&end=${end}&preference=cold`);await page.waitForFunction(()=>document.querySelector('#result').getAttribute('aria-busy')==='true');while(!release)await new Promise(r=>setTimeout(r,10));};
 await open('2026-11-02');
 const before=await page.locator('#resultDates').textContent();
 assert.match(before,/怕冷/);assert.match(await page.locator('#resultCity').textContent(),/München/);
 assert.match(await page.locator('#resultMode').textContent(),/五年/);
 release();await page.waitForFunction(()=>document.querySelector('#result').getAttribute('aria-busy')==='false');
 assert.equal(await page.locator('#resultDates').textContent(),before);
 assert.equal(await page.getByRole('button',{name:'重试查询',exact:true}).count(),0);
 assert.equal(await page.evaluate(()=>document.activeElement.id),'resultCity');
 await page.getByRole('button',{name:'修改行程',exact:true}).click();
 assert.equal(await page.locator('#city').inputValue(),'慕尼黑 · München');assert.equal(await page.locator('#end').inputValue(),'2026-11-02');assert.equal(await page.locator('[data-feeling=cold]').getAttribute('aria-pressed'),'true');
 code='temporarily_unavailable';await open('2026-10-22');release();await page.getByRole('button',{name:'重试查询',exact:true}).waitFor();
 assert.match(await page.locator('#resultMode').textContent(),/气温预报/);assert.match(await page.locator('#resultCity').textContent(),/München/);
 status=400;code='invalid_request';await page.goto((process.env.UI_BASE_URL||'http://127.0.0.1:8002')+'/?view=trip&city_id=invalid&start=2026-10-20&end=2026-11-02&preference=cold');await page.waitForFunction(()=>document.querySelector('#result').getAttribute('aria-busy')==='false');
 assert.match(await page.locator('#resultCity').textContent(),/未能确定城市/);assert.equal(await page.getByRole('button',{name:'重试查询',exact:true}).count(),0);
 await page.goto((process.env.UI_BASE_URL||'http://127.0.0.1:8002')+'/?view=trip&view=city');await page.getByText('查询参数无效',{exact:true}).waitFor();
 console.log('Error context, loading, history/forecast actions, unknown city, duplicate link and edit restoration passed');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
