/* Render Python-derived historical advice with synthetic ERA5; never fetch live data. */
const {chromium}=require('../../.local-tools/node_modules/playwright');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(__dirname,'../..');
const base=process.env.UI_BASE_URL || 'http://127.0.0.1:8001';
const data=JSON.parse(execFileSync('python3',['-c',`
import json,sys
sys.path.insert(0,'tests/web')
from test_history import HistoryTests
from test_live import NOW
from web.fixtures import featured,window
case=HistoryTests();case.setUp()
case.provider.value=lambda d:24 if d.day%2 else 0
case.worker().fill(case.jobs())
print(json.dumps(dict(advice=case.advice(),context=dict(window(NOW),fixture_mode=False),featured=featured(now=NOW))))
`],{cwd:root,encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 let checks=0;const check=(v,m)=>{assert.ok(v,m);checks++};
 try {
  const page=await browser.newPage({viewport:{width:390,height:844},permissions:['clipboard-read','clipboard-write']});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/context?*',r=>r.fulfill({json:data.context}));
  await page.route('**/api/featured?*',r=>r.fulfill({json:data.featured}));
  await page.route('**/api/advice?*',r=>r.fulfill({json:data.advice}));
  await page.goto(base+'/?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal');
  await page.waitForSelector('#resultContent:not(.hidden)');
  check((await page.locator('#resultMode').textContent())==='过去五年同期气温参考','five-year historical mode');
  check(!(await page.locator('#source').textContent()).includes('模拟'),'historical source not demo');
  check((await page.locator('#source').textContent()).includes('历史资料获取时间（最早）'),'historical acquisition label');
  check((await page.locator('#source').textContent()).includes('各月块实际获取时间'),'block acquisition times');
  check((await page.locator('#source').textContent()).includes('建议生成时间'),'separate generation time');
  check((await page.locator('#resultHeadline').textContent()).includes('冬季保暖外套'),'winter coverage in main decision');
  check((await page.locator('#resultLayers').textContent()).includes('保暖内搭'),'winter inner layers');
  const notice=await page.locator('#spanText').textContent();
  check(notice.includes('过去五年')&&!notice.includes('2026-11'),'no future cold date');
  check((await page.locator('#resultNotice').textContent()).includes('非这趟行程的预报'),'reference caveat');
  check(await page.locator('#resultWarmthMark svg').count()===0,'no fabricated main warmth bars');
  check((await page.locator('#tempText').textContent()).includes('无单一代表气温'),'no fabricated temperature');
  await page.locator('#copyAdvice').click();
  const copied=await page.evaluate(()=>navigator.clipboard.readText());
  check(copied.includes('五年')&&copied.includes('非这趟行程的预报'),'copied advice keeps caveat');
  await page.locator('#shareTrip').click();
  check(await page.evaluate(()=>navigator.clipboard.readText())===page.url(),'historical trip shares only input params');
  for(const width of [320,375,390,430,1280]){
   await page.setViewportSize({width,height:844});
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${width}px no overflow`);
  }
  await page.setViewportSize({width:390,height:844});
  if(process.argv.includes('--capture')){
   const height=await page.evaluate(()=>document.documentElement.scrollHeight);
   await page.setViewportSize({width:390,height});
   await page.evaluate(()=>{document.activeElement.blur();window.scrollTo({top:0,behavior:'instant'});return new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))});
   await page.screenshot({path:path.join(root,'docs/verification/phase2b/historical-injected-mobile.png'),fullPage:false});
  }
  await page.locator('#back').click();await page.waitForSelector('.city-card');
  check(await page.locator('#end').getAttribute('max')==='2026-11-14','live form supports thirty calendar days');
  check(await page.locator('#start').inputValue()==='2026-11-02','return restores historical dates');
  check(!await page.locator('#demo').isChecked(),'historical path is live by default');
  check(errors.length===0,'no JS errors');
  console.log(`${checks} historical browser checks passed`);
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
