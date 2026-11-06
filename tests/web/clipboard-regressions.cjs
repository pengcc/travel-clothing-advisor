/* Full traveler-facing exports from the current Python backend, never live weather. */
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.UI_BASE_URL || 'http://127.0.0.1:8002';
const samples=JSON.parse(execFileSync('python3',['-c',`
import sys,json
sys.path.insert(0,'tests/web')
from test_history import HistoryTests
from test_live import Fake,NOW
from web.live import Service
from web.fixtures import advice,BERLIN
from datetime import datetime
c=HistoryTests();c.setUp();c.provider.value=lambda d:0 if d.year==2021 else 8
c.worker().fill(c.jobs())
history=[c.advice(preference=p) for p in ('cold','normal','hot')]
p=dict(view='trip',city_id='berlin',start='2026-10-16',end='2026-10-18',preference='normal')
f=Service(Fake(),lambda:NOW)
forecast=[f.advice(dict(p,preference=pref)) for pref in ('cold','normal','hot')]
c.setUp();c.provider.value=lambda d:24 if d.day%2 else 0
c.worker().fill(c.jobs());split=c.advice()
c.setUp();c.provider.value=lambda d:0 if d.year==2021 else 8;c.provider.edge=0
c.worker().fill(c.jobs());edge=c.advice()
long=f.advice(dict(p,end='2026-10-29'))
warm=Service(Fake(values=[14,24,14]+[14]*11),lambda:NOW).advice(p)
stable=Service(Fake(values=[14]*14),lambda:NOW).advice(p)
summer=Service(Fake(values=[29,24,29]+[29]*11),lambda:NOW).advice(p)
evening_fake=Fake(values=[29]*14)
for i,t in enumerate(evening_fake.data['hourly']['time']):
    if datetime.fromtimestamp(t,BERLIN).strftime('%Y-%m-%d %H')=='2026-10-16 20':
        evening_fake.data['hourly']['temperature_2m'][i]=24
evening=Service(evening_fake,lambda:NOW).advice(p)
fixture=advice(p,now=NOW)
l5=[Service(Fake(values=[8]*14),lambda:NOW).advice(dict(p,preference=pref)) for pref in ('normal','cold','hot')]

review_stable=[Service(Fake(values=[temp]*14),lambda:NOW).advice(dict(p,preference=pref))
               for temp,pref in ((14,'hot'),(8,'hot'),(0,'hot'),(29,'cold'),(24,'cold'))]
review_cool=[]
for temp in (29,24):
    for kind in ('cold','edge'):
        fake=Fake(values=[temp,18,temp]+[temp]*11 if kind=='cold' else [temp]*14)
        if kind=='edge':
            for i,t in enumerate(fake.data['hourly']['time']):
                if datetime.fromtimestamp(t,BERLIN).strftime('%Y-%m-%d %H')=='2026-10-16 20':
                    fake.data['hourly']['temperature_2m'][i]=18
        review_cool.append(Service(fake,lambda:NOW).advice(dict(p,preference='cold')))
print(json.dumps(dict(history=history,forecast=forecast,split=split,edge=edge,long=long,warm=warm,stable=stable,summer=summer,evening=evening,fixture=fixture,l5=l5,review_stable=review_stable,review_cool=review_cool)))
`],{encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const captures=[];
 let checks=0;const check=(v,m)=>{assert.ok(v,m);checks++};
 try {
  const page=await browser.newPage({permissions:['clipboard-read','clipboard-write']});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let response;
  await page.route('**/api/advice?*',r=>r.fulfill({json:response}));
  async function copy(data){
   response=data;
   await page.goto(`${base}/?view=trip&city_id=berlin&start=${data.start}&end=${data.end}&preference=${data.preference}`);
   await page.waitForSelector('#resultContent:not(.hidden)');
   await page.locator('#copyAdvice').click();
   return page.evaluate(()=>navigator.clipboard.readText());
  }
  const labels=['怕冷','正常','怕热'];
  for(const mode of ['history','forecast']) for(let i=0;i<3;i++) {
   const historical=mode==='history';
   const copied=await copy(samples[mode][i]);
   const expected=[
    '【德国旅行备衣建议】', '城市：柏林 · Berlin',
    historical ? '日期：2026-11-02—2026-11-05' : '日期：2026-10-16—2026-10-18',
    `冷热偏好：${labels[i]}`,
    historical ? '资料：过去五年同期参考，非这趟行程的预报' : '资料：所选日期气温预报', '',
    '【通常准备】', historical ? '外套：保暖夹克或轻羽绒。' : '外套：不必带厚外套。',
    historical ? '内搭：长袖、毛衣或抓绒。' : '内搭：短袖或薄长袖。',
    ...Object.values(samples[mode][i].packing_copy.guidance).filter(Boolean), '',
    '【冷暖提醒】',
    ...(historical ? ['历史同期偏冷：另备冬季保暖外套、保暖内搭。','历史同期偏暖：减薄内搭、脱下外层。'] : ['2026-10-17偏冷：另备适中外套、薄毛衣。']), '',
    historical ? '白天气温参考：约 8°C（历史样本），不是最高或最低气温。' : '白天气温参考：约 24°C，不是最高或最低气温。',
    `提醒：${historical ? '历史冷暖不能预测此次旅行的具体日期。' : ''}仅按气温，未评估雨、雪、风；出发前请复查。`,
    historical ? '来源：Open-Meteo / ERA5（CC BY 4.0）；GeoNames。' : '来源：Open-Meteo（CC BY 4.0）；GeoNames。',
   ].join('\n');
   assert.equal(copied,expected,mode+' complete clipboard '+labels[i]);checks++;
   if(i===1) captures.push(copied);
   check(!/获取时间|生成时间|各月|模型更新时间|年度窗口|版本|月块/.test(copied),'no technical audit '+mode+labels[i]);
   check(copied.split('Open-Meteo').length===2&&copied.split('GeoNames').length===2,'single attribution '+mode+labels[i]);
   if(historical) for(const garment of ['冬季保暖外套','保暖内搭','保暖夹克或轻羽绒','毛衣或抓绒']) {
    check(copied.split(garment).length===2,'garment occurs once '+garment+labels[i]);
   }
   // Full provenance remains available on page, including monthly times for history.
   await page.locator('.data-details summary').click();
   check((await page.locator('#source').innerText()).includes(historical?'历史资料各月获取时间':'天气获取时间'),'on-page provenance preserved');
  }
  for (const data of [...samples.l5, ...samples.history, samples.split]) {
   const copied=await copy(data);
   const guidance=data.packing_copy.guidance;
   const visible=await page.locator('#resultGuidance p').allTextContents();
   assert.deepEqual(visible,Object.values(guidance).filter(Boolean));checks++;
   for(const value of visible) check(copied.split(value).length===2,'guidance appears once in full copy');
   check(visible.length<=3,'at most three guidance paragraphs');
   check(!copied.includes('个人调整：'),'no duplicate legacy preference sentence');
   if(samples.l5.includes(data)) {
    check(copied.includes('可替代主外套方案，不必再多带一套'),'conditional mutually exclusive alternative');
    check(copied.includes('实际保暖能力适合预计活动'),'no unconditional performance promise');
   } else check(!guidance.alternative,'winter risk suppresses L5 alternative');
   for(const width of [320,375,390]) {
    await page.setViewportSize({width,height:844});
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'guidance wraps '+width);
   }
  }
  // Review #5557993556: preference copy must match actual coverage, on page and export.
  for(const data of samples.review_stable) {
   const copied=await copy(data);
   const visible=await page.locator('#resultGuidance').innerText();
   check(data.packing_copy.risks.length===0,'stable sample has no risk events');
   for(const output of [visible,copied]) {
    check(!output.includes('已提醒的较冷时段'),'no fabricated prior warning');
    if(data.preference==='cold') {
     check(output.includes('薄长袖作为轻薄内搭'),'light preference adjustment');
     check(!output.includes('毛衣'),'stable hot trip adds no sweater');
    } else check(output.includes('保留上述保暖衣物'),'stable cold coverage retained');
   }
  }
  for(const data of samples.review_cool) {
   const copied=await copy(data);
   const visible=await page.locator('#resultGuidance').innerText();
   check(data.packing_copy.risks.length>0,'cooler sample has real risk');
   for(const output of [visible,copied]) check(output.includes('可脱的薄毛衣'),'real cooler need retains actionable layer');
   check(copied.includes('可脱的薄外套'),'cooler event keeps outer coverage');
  }
  const edge=await copy(samples.edge);
  check(edge.includes('历史同期早晚较凉：外出带上已备的保暖层。'),'evening event retained without duplicate clothes');
  check(edge.split('冬季保暖外套').length===2&&edge.split('保暖内搭').length===2,'shared L6 risk only named once');
  const split=await copy(samples.split);
  check(split.includes('【分情况准备】')&&!split.includes('【通常准备】'),'split has no false usual outfit');
  check(split.includes('冬季保暖外套')&&split.includes('保暖内搭')&&split.includes('短袖或薄长袖'),'split preserves cold/warm coverage');
  check(!/历史同期.*2026/.test(split),'history does not predict future cold dates');
  const long=await copy(samples.long);
  check(long.includes('第8–14天不确定性更大'),'long forecast uncertainty retained');
  const warm=await copy(samples.warm);
  check(warm.includes('2026-10-17偏暖')&&warm.includes('减薄内搭、脱下外层'),'forecast warmer-day action retained');
  check(!warm.includes('偏冷'),'warm-only forecast invents no cold risk');
  const stable=await copy(samples.stable);
  check(!stable.includes('【冷暖提醒】'),'stable forecast invents no risk section');
  for(const [key,risk] of [
   ['summer','2026-10-17偏冷：另备薄长袖。'],
   ['evening','10月16日 20时前后较凉：另备薄长袖。'],
  ]) {
   const copied=await copy(samples[key]);
   const expected=[
    '【德国旅行备衣建议】','城市：柏林 · Berlin','日期：2026-10-16—2026-10-18',
    '冷热偏好：正常','资料：所选日期气温预报','',
    '【通常准备】','外套：不必带厚外套。','内搭：短袖、轻薄透气下装。','',
    '【冷暖提醒】',risk,'',
    '白天气温参考：约 29°C，不是最高或最低气温。',
    '提醒：仅按气温，未评估雨、雪、风；出发前请复查。',
    '来源：Open-Meteo（CC BY 4.0）；GeoNames。',
   ].join('\n');
   assert.equal(copied,expected,key+' full L1/L2 clipboard');checks++;
   check(samples[key].warmth_indicator_level===1,'original L1 decision retained: '+key);
   check(key==='summer' ? samples[key].packing_variation_notice.includes('2026-10-17偏冷') : samples[key].notices.some(n=>n.includes('20时')&&n.includes('较凉')),'original cold/edge warning retained: '+key);
   check(!copied.includes('另备不必带')&&copied.split('薄长袖').length===2,'only positive additional clothing: '+key);
   if(process.argv.includes('--capture')) captures.push(copied);
  }
  const fixture=await copy(samples.fixture);
  check(fixture.startsWith('【演示数据，非真实天气】'),'fixture copy explicit');
  check(fixture.includes('未获取真实天气或历史资料')&&!fixture.includes('CC BY 4.0'),'fixture never claims provider data');
  check(errors.length===0,'no browser errors');
  if(process.argv.includes('--capture')) fs.writeFileSync('docs/verification/issue27/copied-advice.txt', 'Synthetic current-backend examples; not live weather.\n\n'+captures.join('\n\n---\n\n')+'\n');
  console.log(`${checks} full clipboard regression checks passed`);
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
