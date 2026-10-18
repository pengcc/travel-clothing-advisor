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
 return {text:n.textContent,font:getComputedStyle(n).fontSize,ink:getComputedStyle(n).getPropertyValue('--tag-ink').trim(),bg:getComputedStyle(n).getPropertyValue('--tag-bg').trim(),fits:r.left>=c.left&&r.right<=c.right&&t.left>=r.left&&t.right<=r.right&&t.bottom<=r.bottom&&t.top>=r.top};
 }));
 assert.ok(checks.every(c=>c.fits),JSON.stringify({width,large,missing,checks}));
 assert.equal(new Set(checks.slice(0,6).map(c=>c.bg)).size,6);
 // Distinct hex values alone cannot catch nearly identical colors (Issue #50).
 const rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
 const distance=(a,b)=>Math.hypot(...rgb(a).map((v,i)=>v-rgb(b)[i]));
 const luminance=hex=>rgb(hex).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
   .reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
 const contrast=(a,b)=>(Math.max(luminance(a),luminance(b))+.05)/(Math.min(luminance(a),luminance(b))+.05);
 assert.ok(distance(checks[3].bg,checks[6].bg)>=60,'L4 and large-variation backgrounds must be visibly different');
 assert.ok(rgb(checks[3].bg)[2]>rgb(checks[3].bg)[0]+25,'L4 reads as cool blue');
 assert.ok(rgb(checks[6].bg)[0]>rgb(checks[6].bg)[2]+25,'variation reads as warm orange');
 assert.ok(checks.every(c=>contrast(c.bg,c.ink)>=4.5),'tag text must meet AA contrast');

 assert.deepEqual(checks.slice(0,6).map(c=>c.text), ['清爽透气','轻薄衣物','薄外套','中等厚度','保暖外套','厚实保暖']);
 assert.deepEqual(checks.slice(0,6).map(c=>c.bg), ['#FFE0A0','#D9EDBC','#B1E3DA','#ADD8F2','#B9C6F1','#CEB9ED']);
 assert.equal(checks[6].bg, '#FBE9DD', 'variation matches approved pastel apricot');
 assert.ok(await page.locator('.city-card .warmth-variation img').evaluate(img => img.getAttribute('src').includes('alert-variation-landscape')), 'featured variation uses existing wide illustration');
 assert.ok(await page.locator('.city-card .warmth-unavailable .warmth-name').evaluate(el => getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)'), 'no-data/reference state is text-only');
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
