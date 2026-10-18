// Offline presentation matrix; synthetic states are explicit, never temperature-derived.
const {chromium}=require('../../.local-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
 for(const width of [320,390,1280]) for(const large of [false,true]) for(const missing of [false,true]) {
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'});
 if(missing) await page.route('**/static/icons/**',r=>r.abort());
 await page.goto('http://127.0.0.1:8001'); await page.waitForSelector('.city-card');
 if(!large&&!missing) await page.locator('.featured').screenshot({path:`docs/verification/issue50/home-${width}.png`});
 await page.evaluate(async()=>{
 const {CityCard}=await import('/static/components.js');
 const grid=document.querySelector('#featuredGrid');grid.replaceChildren();
 for(const level of [1,2,3,4,5,6,null,null]) {
 const variation=level===null && grid.children.length===6;
 grid.append(CityCard({city:{name:'Preview',zh:level===null?(variation?'变化状态':'暂无参考'):`保暖 L${level}`},warmth_indicator_level:level,headline:'标签视觉验证 · 模拟数据',packing_variation_summary:variation?'冷热变化大，请按日期准备。':null},'#'));
 }
 });
 if(large) await page.addStyleTag({content:'html{font-size:32px}'});
 await page.waitForFunction(missing=>[...document.querySelectorAll('.city-card picture')].every(p=>missing?p.hidden:p.querySelector('img').complete&&p.querySelector('img').naturalWidth),missing);
 const checks=await page.locator('.city-card .warmth-name').evaluateAll(nodes=>nodes.map(n=>{
 const r=n.getBoundingClientRect(),c=n.closest('.city-card').getBoundingClientRect(),range=document.createRange();range.selectNodeContents(n); const t=range.getBoundingClientRect();
 return {text:n.textContent,font:getComputedStyle(n).fontSize,ink:getComputedStyle(n).color,bg:getComputedStyle(n).getPropertyValue('--tag-bg'),fits:r.left>=c.left&&r.right<=c.right&&t.left>=r.left&&t.right<=r.right&&t.bottom<=r.bottom&&t.top>=r.top};
 }));
 assert.ok(checks.every(c=>c.fits),JSON.stringify({width,large,missing,checks}));
 assert.equal(new Set(checks.slice(0,6).map(c=>c.bg)).size,6);
 assert.equal(checks[3].text,'适中保暖');
 assert.equal(checks[6].text,'冷热变化大');assert.equal(checks[7].text,'暂无白天参考');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(!missing&&!large || width===390&&large || width===390&&missing&&!large) {
 await page.locator('.featured').screenshot({path:`docs/verification/issue50/labels-${width}${large?'-large':''}${missing?'-missing':''}.png`});
 }
 assert.equal(await page.locator('.warmth-name').first().evaluate(n=>getComputedStyle(n).transitionDuration),'0s');
 console.log(`PASS ${width}px ${large?'200% font':'normal font'} ${missing?'missing images':'images loaded'}: all 8 states fit`);
 await page.close();
 }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
