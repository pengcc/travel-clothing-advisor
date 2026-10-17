/* Review #5545508096: render full Service JSON generated with an offline provider. */
const {chromium} = require('../../.local-tools/node_modules/playwright');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:8001';
const root = path.resolve(__dirname, '../..');
const data = JSON.parse(execFileSync('python3', ['-c', `
import json, sys
sys.path.insert(0, 'tests/web')
from test_live import Fake, NOW, geo
from web.live import Service
from web.fixtures import window, featured
p = dict(view='trip',city_id='berlin',start='2026-10-16',end='2026-10-29',preference='normal')
responses = []
for warm, cold in [(24,0),(14,0),(24,14)]:
    responses.append(Service(Fake(values=[warm]*7+[cold]*7),lambda:NOW).advice(p))
fake = Fake()
broken = geo(123)
del broken['admin1']
fake.search = [broken,geo()]
print(json.dumps(dict(context=dict(window(NOW),fixture_mode=False),featured=featured(now=NOW),
    responses=responses,cities=Service(fake,lambda:NOW).cities('Berlin'))))
`], {cwd:root,encoding:'utf8'}));
(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  let checks = 0;
  const check = (value,message) => {assert.ok(value,message);checks++};
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const errors = [];
    page.on('pageerror',error => errors.push(error.message));
    let response = data.responses[0];
    await page.route('**/api/context?*',route => route.fulfill({json:data.context}));
    await page.route('**/api/featured?*',route => route.fulfill({json:data.featured}));
    await page.route('**/api/cities?*',route => route.fulfill({json:data.cities}));
    await page.route('**/api/advice?*',route => route.fulfill({json:response}));
    for (const [index, outer, inner, warmInner] of [
      [0,'冬季保暖外套','保暖内搭','短袖或薄长袖'],
      [1,'冬季保暖外套','保暖内搭','长袖搭配薄毛衣'],
      [2,'适中外套','薄毛衣','短袖或薄长袖'],
    ]) {
      response = data.responses[index];
      await page.goto(base+'/?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-29&preference=normal');
      await page.waitForSelector('#resultContent:not(.hidden)');
      check((await page.locator('#resultHeadline').textContent()).includes(outer),`split ${index}: visible cold outerwear`);
      check((await page.locator('#spanText').textContent()).includes(outer),`split ${index}: variation names cold layer`);
      const layers = await page.locator('#resultLayers').textContent();
      check(layers.includes(inner)&&layers.includes(warmInner),`split ${index}: visible cold and warm inner layers`);
      check((await page.locator('#spanText').textContent()).includes('2026-10-23较冷'),`split ${index}: supported cold date`);
      check((await page.locator('#resultWarmthMark').textContent()).includes('冷热变化大'),`split ${index}: no invented main level`);
      check(await page.locator('#resultWarmthMark svg').count()===0,`split ${index}: no single-level bars`);
      check((await page.locator('#tempText').textContent()).includes('无单一代表气温'),`split ${index}: no invented representative temperature`);
      check(await page.evaluate(()=>Boolean(document.querySelector('#spanRemind').compareDocumentPosition(document.querySelector('#resultLayers'))&Node.DOCUMENT_POSITION_FOLLOWING)),`split ${index}: notice before layers`);
      for (const width of [320,390]) {
        await page.setViewportSize({width,height:844});
        check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`split ${index}: ${width}px wraps`);
      }
      if (index===0) {
        const height=await page.evaluate(()=>document.documentElement.scrollHeight);
        await page.setViewportSize({width:390,height});
        await page.evaluate(()=>{document.activeElement.blur();window.scrollTo({top:0,behavior:'instant'});return new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))});
        if (!process.argv.includes('--check-only')) await page.screenshot({path:path.join(root,'docs/verification/phase2a/winter-split-injected-mobile.png'),fullPage:false});
      }
      await page.setViewportSize({width:390,height:844});
    }
    await page.goto(base);await page.waitForSelector('.city-card');
    await page.locator('#city').fill('Berlin');
    await page.waitForSelector('#cityOptions button');
    check(await page.locator('#cityOptions button').count()===1,'mixed geocoding response retains valid candidate');
    check((await page.locator('#cityOptions button').textContent()).includes('Berlin'),'candidate retains verified name and state');
    await page.locator('#cityOptions button').click();
    check((await page.locator('#city').inputValue()).includes('柏林'),'valid candidate remains selectable');
    check((await page.locator('#cityError').textContent())==='','incomplete candidate does not block search');
    check(errors.length===0,'no browser errors');
    console.log(`${checks} review regression browser checks passed`);
  } finally {await browser.close()}
})().catch(error => {console.error(error);process.exit(1)});
