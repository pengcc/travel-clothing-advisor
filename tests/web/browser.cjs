/* Dev only. Install once with: (cd tests/web && npm ci); see "Browser test setup" in web/README.md. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const output = 'docs/verification/phase1';
const capture = !process.argv.includes('--check-only');
const shortDate = iso => iso.replace(/^(\d{4})-(\d{2})-(\d{2})$/, '$1年$2月$3日');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:8000';
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const context = await browser.newContext({viewport:{width:390,height:844}, reducedMotion:'reduce', permissions:['clipboard-read','clipboard-write']});
  const p = await context.newPage(), errors = [], checks = [];
  p.on('pageerror', e => errors.push(e.message));
  const check = (name, value) => {assert.ok(value, name); checks.push(name);};
  const waitHome = () => p.waitForSelector('.city-card');
  const waitResult = () => p.waitForSelector('#resultContent:not(.hidden)');
  const shot = async name => {
    if (!capture) return;
    const viewport = p.viewportSize();
    const height = await p.evaluate(() => document.documentElement.scrollHeight);
    await p.setViewportSize({width:viewport.width, height});
    await p.evaluate(() => {window.scrollTo({top:0,behavior:'instant'}); return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));});
    await p.screenshot({path:`${output}/${name}.png`, fullPage:false, animations:'disabled'});
    await p.setViewportSize(viewport);
  };
  await p.goto(base); await waitHome();
  const dates = await p.evaluate(async () => (await fetch('/api/context')).json());
  const shift = n => {const d = new Date(dates.today+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10)};
  await shot('01-home-mobile');
  // Keyboard-only city selection, then retain personal form across independent city navigation.
  await p.locator('#city').fill('frankfurt');
  await p.waitForSelector('#cityOptions button');
  check('Ambiguous city suggestions include both federal states', await p.locator('#cityOptions button').count() === 2);
  await p.locator('#city').fill('慕尼黑'); await p.waitForFunction(()=>document.querySelector('#cityOptions button')?.textContent.includes('München'));
  await p.locator('#city').press('ArrowDown'); await p.keyboard.press('Enter');
  await p.locator('#start').fill(shift(2)); await p.locator('#end').fill(shift(4));
  await p.locator('[data-feeling="cold"]').click();
  await p.locator('.city-card').first().click(); await waitResult();
  check('City canonical URL contains only view and city_id', p.url().endsWith('?view=city&city_id=berlin'));
  check('City always normal, current fourteen days', (await p.locator('#preferenceNote').textContent()).includes('默认按正常冷热偏好推荐') && (await p.locator('#resultDates').textContent()).includes('今起14天'));
  await shot('02-city-result-mobile');
  await p.locator('#shareTrip').click();
  check('Copied city link contains no private trip state', (await p.evaluate(()=>navigator.clipboard.readText())).endsWith('?view=city&city_id=berlin'));
  await p.reload(); await waitResult();
  await p.locator('#back').click(); await waitHome();
  check('City reload and return preserve personal city', (await p.locator('#city').inputValue()).includes('München'));
  check('City leaves personal dates and sensitivity unchanged', await p.locator('#start').inputValue() === shift(2) && await p.locator('[data-feeling="cold"]').getAttribute('aria-pressed') === 'true');
  await p.locator('[type="submit"]').click(); await waitResult();
  check('Trip URL uses personal inputs', p.url().includes(`view=trip&city_id=munich&start=${shift(2)}&end=${shift(4)}&preference=cold`));
  await shot('03-trip-result-mobile');
  await p.locator('#shareTrip').click(); check('Trip share preserves all parameters', await p.evaluate(()=>navigator.clipboard.readText()) === p.url());
  await p.locator('#copyAdvice').click(); check('Copied advice explicitly labels fixture', (await p.evaluate(()=>navigator.clipboard.readText())).includes('演示数据，非真实天气'));
  await p.goBack(); await waitHome(); await p.goForward(); await waitResult(); await p.reload(); await waitResult();
  check('Back forward reload maintain trip identity', (await p.locator('#resultKind').textContent()).includes('行程'));
  await p.goto(`${base}/?view=trip&city_id=berlin&start=${shift(20)}&end=${shift(24)}&preference=normal`); await waitResult();
  check('Historical mode explicitly not a forecast', (await p.locator('#resultNotice').textContent()).includes('不是旅行当天的天气预报'));
  check('Historical mode invents no future cold date', !(await p.locator('#spanRemind').isVisible()));
  await shot('04-historical-result-mobile');
  await p.goto(base); await waitHome(); await p.setViewportSize({width:1280,height:900}); await shot('05-home-desktop');
  await p.goto(`${base}/?view=city&city_id=berlin&start=invalid&preference=hot`); await waitResult();
  check('City deep link discards injected trip values', p.url().endsWith('?view=city&city_id=berlin'));
  await p.locator('.demo-tools summary').click();
  for (const [fixture, label, notice] of [['stable','中等厚度',false],['colder','轻薄衣物',true],['warmer','中等厚度',true],['split','冷热变化大',true]]) {
    await p.locator('#fixture').selectOption(fixture); await waitResult();
    check(`${fixture} marker comes from response`, (await p.locator('#resultWarmthMark').textContent()).includes(label));
    check(`${fixture} notice visibility`, await p.locator('#spanRemind').isVisible() === notice);
    if (fixture === 'split') check('Split state has no invented bars', await p.locator('#resultWarmthMark svg').count() === 0);
    if (fixture === 'split') check('Split fixture range is marked simulated', (await p.locator('#tempText').textContent()).includes('不代表真实气温'));
    const expectedDirection = {stable:null, colder:'cold', warmer:'warm', split:'mixed'}[fixture];
    const banner = p.locator('#spanRemind');
    if (notice) {
      check(`${fixture} notice before inner layers`, await p.evaluate(()=>Boolean(document.querySelector('#spanRemind').compareDocumentPosition(document.querySelector('#resultLayers')) & Node.DOCUMENT_POSITION_FOLLOWING)));
      check(`${fixture} direction class`, await banner.evaluate((el,k)=>el.classList.contains('variation-banner--'+k), expectedDirection));
      const art = {cold:'alert-cold', warm:'alert-hot', mixed:'alert-variation'}[expectedDirection];
      check(`${fixture} correct illustration`, (await banner.locator('img').first().getAttribute('src')).includes(art));
      const title = {cold:'偏冷提醒',warm:'偏暖提醒',mixed:'冷热变化提醒'}[expectedDirection];
      check(`${fixture} direction heading`, (await banner.locator('strong').textContent()).includes(title));
      const appearance = await banner.evaluate(el => ({fill:getComputedStyle(el).backgroundColor, image:getComputedStyle(el).backgroundImage}));
      if (expectedDirection==='cold') check('Cold detail tint matches Scheme A',appearance.fill==='rgb(237, 245, 251)');
      if (expectedDirection==='warm') check('Warm detail tint matches Scheme A',appearance.fill==='rgb(255, 244, 229)');
      if (expectedDirection==='mixed') check('Mixed detail has two-tone gradient',appearance.image.includes('linear-gradient'));
    } else {
      check('No detail reminder carries stale direction', await banner.evaluate(el=>!['cold','warm','mixed'].some(k=>el.classList.contains('variation-banner--'+k))));
    }
    for (const width of [320,375,390,430,1280]) {
      await p.setViewportSize({width,height:844});
      check(`${fixture} ${width}px no horizontal overflow`, await p.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
    }
    await p.setViewportSize({width:390,height:844}); await shot(`fixture-${fixture}`);
  }
  // Returning from a mixed result to a stable one must clear any stale CSS state.
  await p.locator('#fixture').selectOption('stable'); await waitResult();
  check('Mixed-to-stable clears reminder state', await p.locator('#spanRemind').evaluate(el =>
    el.classList.contains('hidden') && !['cold','warm','mixed'].some(k => el.classList.contains('variation-banner--'+k))));
  // Older API payloads without direction retain readable original copy and default styling.
  await p.route('**/api/advice?*', async route => {
    const response=await route.fetch(), data=await response.json();
    delete data.packing_variation_kind;
    await route.fulfill({json:data});
  });
  await p.locator('#fixture').selectOption('warmer'); await waitResult();
  check('Missing direction keeps variation visible', await p.locator('#spanRemind').isVisible());
  check('Missing direction retains original illustration', (await p.locator('#spanRemind img').first().getAttribute('src')).includes('alert-variation'));
  check('Missing direction does not invent a colored variant', await p.locator('#spanRemind').evaluate(el =>
    !['cold','warm','mixed'].some(k=>el.classList.contains('variation-banner--'+k))));
  await p.unroute('**/api/advice?*');
  for (const fixture of ['loading','unavailable','stale']) {
    await p.locator('#fixture').selectOption(fixture); await p.waitForSelector('#resultStatus:not(.hidden)');
    if (fixture !== 'loading') await p.waitForFunction(()=>document.querySelector('#result').getAttribute('aria-busy') === 'false');
    check(`${fixture} shows no clothing answer`, !(await p.locator('#resultContent').isVisible()));
    await shot(`fixture-${fixture}`);
  }
  await p.goto(`${base}/?view=trip&city_id=berlin&start=2026-02-30&end=${shift(2)}&preference=normal`);
  await p.waitForFunction(()=>document.querySelector('#resultStatus')?.textContent.includes('有效日期')); check('Invalid deep link renders understandable error', (await p.locator('#resultStatus').textContent()).includes('有效日期'));
  await shot('fixture-invalid');
  await p.goto(`${base}/?view=city&city_id=berlin&city_id=munich`); await p.waitForSelector('#resultStatus:not(.hidden)');
  check('Duplicate query rejected', (await p.locator('#resultStatus').textContent()).includes('重复'));
  await p.goto(base); await waitHome();
  for (const width of [320,375,390,430,1280]) {
    await p.setViewportSize({width,height:844});
    check(`Home ${width}px no overflow`, await p.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
    await shot(`home-${width}`);
  }
  // 200% text enlargement, complete Chinese variation copy must wrap.
  await p.goto(`${base}/?view=city&city_id=berlin`); await waitResult(); await p.setViewportSize({width:320,height:844});
  await p.evaluate(() => { const sizes = [...document.querySelectorAll('body *')].map(el => [el, parseFloat(getComputedStyle(el).fontSize)]); sizes.forEach(([el,size]) => el.style.fontSize = `${size*2}px`); });
  check('Enlarged Chinese copy does not overflow viewport', await p.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
  await shot('large-text-320');
  await p.goto(base); await waitHome();
  const cityNames = [];
  for (let i = 0; i < 3; i++) {
    cityNames.push(...await p.locator('.city-name').allTextContents());
    if (i < 2) await p.locator('#nextPage').click();
  }
  check('All ten featured cities are reachable through pagination', new Set(cityNames).size === 10);
  const invalid = await p.request.get(`${base}/api/advice?view=trip&city_id=berlin&start=2026-02-30&end=${shift(2)}&preference=normal`);
  check('Invalid API input returns 400', invalid.status() === 400);
  const unavailable = await p.request.get(`${base}/api/advice?view=city&city_id=berlin&fixture=unavailable`);
  check('Unavailable API fixture returns 503', unavailable.status() === 503);
  // Simulate the server observing German midnight without changing machine time.
  await p.goto(`${base}/?view=city&city_id=berlin`); await waitResult();
  const nextContext = {...dates, today:shift(1), forecast_end:shift(14), max_date:shift(30)};
  await p.route('**/api/context?*', route => route.fulfill({json:nextContext}));
  await p.route('**/api/advice?*', async route => {
    const response = await route.fetch(); const data = await response.json();
    data.start = shift(1); data.end = shift(14);
    await route.fulfill({json:data});
  });
  await p.evaluate(() => window.dispatchEvent(new Event('focus')));
  await p.waitForFunction(expected => document.querySelector('#resultDates').textContent.startsWith(expected), shortDate(shift(1)));
  check('Returning across German midnight refreshes independent city dates', (await p.locator('#resultDates').textContent()).includes(shortDate(shift(14))));
  await p.unroute('**/api/context?*'); await p.unroute('**/api/advice?*');
  // Contrast checks use actual computed colors, not only documented tokens.
  const colors = await p.evaluate(() => ({action:getComputedStyle(document.querySelector('.action')).backgroundColor, ink:getComputedStyle(document.body).color, page:getComputedStyle(document.body).backgroundColor, muted:getComputedStyle(document.querySelector('.source')).color}));
  function luminance(rgb) {const c = rgb.match(/[\d.]+/g).slice(0,3).map(Number).map(n => n/255).map(n => n <= .04045 ? n/12.92 : ((n+.055)/1.055)**2.4); return c[0]*.2126+c[1]*.7152+c[2]*.0722;}
  function contrast(a,b) {const x=luminance(a), y=luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
  check('Action white text has AA contrast', contrast(colors.action,'rgb(255,255,255)') >= 4.5);
  check('Body and source text have AA contrast', contrast(colors.ink,colors.page) >= 4.5 && contrast(colors.muted,colors.page) >= 4.5);
  check('No browser JavaScript errors', errors.length === 0);
  if (capture) fs.writeFileSync(`${output}/browser-results.json`, JSON.stringify({browser:await browser.version(), checks, errors},null,2)+'\n');
  console.log(`${checks.length} browser checks passed`);
  await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
