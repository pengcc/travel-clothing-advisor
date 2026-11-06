/* Issue #27: presentation contracts, with synthetic Python-derived advice only. */
const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:8002';
const samples = JSON.parse(execFileSync('python3', ['-c', `
import sys,json
sys.path.insert(0,'tests/web')
from test_history import HistoryTests
c=HistoryTests();c.setUp()
c.provider.value=lambda d:0 if d.year==2021 else 8
c.worker().fill(c.jobs())
history=c.advice()
c.setUp();c.provider.value=12.8;c.worker().fill(c.jobs());near_history=c.advice()
c.setUp();c.provider.value=lambda d:24 if d.day%2 else 0
c.worker().fill(c.jobs());split_history=c.advice()
from test_live import Fake,NOW
from web.live import Service
from web.fixtures import BERLIN
from datetime import datetime
p=dict(view='trip',city_id='berlin',start='2026-10-16',end='2026-10-18',preference='normal')
f=Fake(values=[12.8]*14)
near_forecast=Service(f,lambda:NOW).advice(p)
f=Fake(values=[14]*14)
for i,t in enumerate(f.data['hourly']['time']):
    if datetime.fromtimestamp(t,BERLIN).hour==20:
        f.data['hourly']['temperature_2m'][i]=7
cool_forecast=Service(f,lambda:NOW).advice(p)
print(json.dumps(dict(history=history,near_history=near_history,split_history=split_history,
                     near_forecast=near_forecast,cool_forecast=cool_forecast)))
`], {encoding:'utf8'}));
(async () => {
 const browser=await chromium.launch({channel:'chrome',headless:true});
 let checks=0;
 const check=(v,m)=>{assert.ok(v,m);checks++};
 try {
  const page=await browser.newPage({viewport:{width:375,height:844},permissions:['clipboard-read','clipboard-write']});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const result=()=>page.waitForSelector('#resultContent:not(.hidden)');
  await page.goto(base);await page.waitForSelector('.city-card');
  check((await page.locator('[data-feeling]').allTextContents()).join('/')==='怕冷/正常/怕热','agreed labels');
  check(await page.locator('[data-feeling=normal]').getAttribute('aria-pressed')==='true','normal selected by default');
  check(!await page.locator('.demo-tools').isVisible(),'normal mode hides test tools');
  check(!/本地|临时|预取|一般体感/.test(await page.locator('body').innerText()),'normal home copy');
  await page.locator('.city-card').first().click();await result();
  check(!/体感/.test(await page.locator('#resultDates').textContent()),'city dates contain no sensitivity label');
  check((await page.locator('#preferenceNote').textContent()).includes('默认按正常冷热偏好推荐'),'city explains default');
  check(await page.locator('#preferenceNote').isVisible(),'default explanation visible');
  await page.locator('.data-details summary').click();
  check(await page.locator('#source').isVisible(),'attribution details accessible');
  check(/Open-Meteo.*CC BY 4.0.*GeoNames/.test(await page.locator('#source').textContent()),'forecast attribution');
  for(const pref of ['cold','normal','hot']) {
   await page.goto(`${base}/?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-18&preference=${pref}`);await result();
   const label={cold:'怕冷',normal:'正常',hot:'怕热'}[pref];
   check((await page.locator('#resultDates').textContent()).includes('冷热偏好：'+label),'actual preference '+pref);
   check(!await page.locator('#preferenceNote').isVisible(),'no default explanation on personal trip');
   check(!/今天仅使用|有效白天时段/.test(await page.locator('body').innerText()),'plain forecast copy');
  }
  let advice=samples.history;
  await page.route('**/api/advice?*',r=>r.fulfill({json:advice}));
  await page.goto(`${base}/?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal`);await result();
  check(!(await page.locator('#resultHeadline').textContent()).includes('冬季'),'L5 usual headline');
  check(await page.locator('#coatLabel').textContent()==='通常准备的外套','representative history uses usual heading');
  check((await page.locator('#spanText').textContent()).includes('冬季保暖外套')&&(await page.locator('#spanText').textContent()).includes('保暖内搭'),'L6 outer and inner risk visible');
  check((await page.locator('#resultMode').textContent()).includes('不是本次旅行预报'),'prominent history distinction');
  check(!(await page.locator('#spanText').textContent()).includes('2026-11'),'risk never names future date');
  check(!await page.locator('#edgeNotice').isVisible(),'no redundant similar early-evening needs');
  await page.locator('#copyAdvice').click();
  const copy=await page.evaluate(()=>navigator.clipboard.readText());
  check(copy.includes('冬季保暖外套')&&copy.includes('保暖内搭')&&copy.includes('CC BY 4.0'),'copy preserves risk and source');
  for(const width of [320,375,390]) {
   await page.setViewportSize({width,height:844});
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'historical mobile wrapping '+width);
  }
  const risk=await page.locator('#spanText').textContent();
  for(const garment of ['冬季保暖外套','保暖内搭','毛衣','抓绒']) {
   check(risk.split(garment).length-1===1,'risk names garment once: '+garment);
  }
  check(!risk.includes('保暖夹克或轻羽绒'),'risk does not repeat usual L5 coat');
  check(risk.includes('较暖时内搭减薄、外层方便脱下')&&risk.includes('不是本次旅行预报'),'risk retains warm options and uncertainty');
  for(const key of ['near_history','near_forecast','cool_forecast','split_history']) {
   advice=samples[key];
   await page.goto(`${base}/?view=trip&city_id=berlin&start=${advice.start}&end=${advice.end}&preference=normal`);await result();
   if(key.startsWith('near_')) {
    check(advice.notices.some(n=>n.includes('13°C'))&&!advice.notices.some(n=>n.includes('较凉')),'source has general guidance but no cooler edge: '+key);
    check(await page.locator('#edgeNotice').isVisible(),'general guidance remains visible: '+key);
    check(await page.locator('#edgeTitle').textContent()==='分层与厚度提示','general guidance has truthful heading: '+key);
    check(await page.locator('#edgeIcon').textContent()!=='🌙','general guidance has no evening icon: '+key);
    check((await page.locator('#edgeText').textContent()).includes('13°C'),'thickness guidance retained: '+key);
    await page.locator('#copyAdvice').click();
    check((await page.evaluate(()=>navigator.clipboard.readText())).includes('13°C'),'copy retains general guidance: '+key);
   } else if(key==='cool_forecast') {
    check(await page.locator('#edgeTitle').textContent()==='早晚注意分层','genuine cooler hours retain evening heading');
    check((await page.locator('#edgeText').textContent()).includes('20时'),'supported evening detail retained');
   } else {
    check(await page.locator('#coatLabel').textContent()==='外套建议','split history uses neutral heading');
    check(await page.locator('#resultWarmthMark svg').count()===0,'split has no representative indicator');
    check((await page.locator('#resultLayers').textContent()).includes('保暖内搭')&&(await page.locator('#resultLayers').textContent()).includes('短袖'),'split preserves cold and warm layers');
    check((await page.locator('#spanText').textContent()).includes('冬季保暖外套')&&(await page.locator('#spanText').textContent()).includes('轻薄'),'split preserves cold and warm coats');
   }
  }
  await page.unroute('**/api/advice?*');
  await page.route('**/api/advice?*',r=>r.abort());
  await page.reload();await page.waitForSelector('#resultStatus button');
  check(!await page.locator('#resultContent').isVisible(),'failure clears old success');
  check((await page.locator('#resultStatus').textContent()).includes('检查网络'),'actionable connection error');
  await page.unroute('**/api/advice?*');
  await page.goto(base);await page.waitForSelector('.city-card');
  await page.route('**/api/featured?*',r=>r.fulfill({status:503,json:{error:'城市参考暂不可用，请稍后重试。'}}));
  await page.reload();await page.waitForSelector('#retryFeatured:not(.hidden)');
  check(await page.locator('.city-card').count()===0,'failed featured response clears cards');
  await page.unroute('**/api/featured?*');await page.locator('#retryFeatured').click();await page.waitForSelector('.city-card');
  check(!await page.locator('#retryFeatured').isVisible(),'featured retry recovers');
  check(errors.length===0,'no browser errors');
  console.log(`${checks} copy regression checks passed`);
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
