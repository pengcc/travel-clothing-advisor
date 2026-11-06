/* Run against python3 -m web.server; needs the Playwright install from "Browser test setup" in web/README.md. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:8000';
const clone = data => JSON.parse(JSON.stringify(data));
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const errors = [], results = [];
  const seedResponse = await (await browser.newContext()).request.get(`${base}/api/featured`);
  const seed = await seedResponse.json();
  const dates = {today:seed.today, forecast_end:seed.forecast_end, max_date:seed.forecast_end};
  const shift = (date, n) => { const d = new Date(date+'T12:00:00Z'); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10); };
  const nextDates = {today:shift(dates.today,1), forecast_end:shift(dates.forecast_end,1), max_date:shift(dates.today,30)};
  const stamped = (label, window = dates) => {
    const data = clone(seed); data.today = window.today; data.forecast_end = window.forecast_end;
    data.cities.forEach(c => { c.start=window.today; c.end=window.forecast_end; c.headline=label; });
    return data;
  };
  async function test(name, run) {
    const page = await browser.newPage();
    page.on('pageerror', error => errors.push(error.message));
    let currentDates = dates;
    const pending = [], arrivals = [];
    await page.route('**/api/context?*', route => route.fulfill({json:currentDates}));
    await page.route('**/api/featured?*', async route => {
      const decision = new Promise(resolve => pending.push({route, resolve}));
      arrivals.splice(0).forEach(resolve => resolve());
      const {data, fail} = await decision;
      if (fail) await route.fulfill({status:503,json:{error:'older request failed'}});
      else await route.fulfill({json:data});
    });
    const nextRequest = async () => {
      if (!pending.length) await new Promise(resolve => arrivals.push(resolve));
      return pending.shift();
    };
    const release = async (request, data, fail = false) => {
      const response = page.waitForResponse(r => r.url() === request.route.request().url());
      request.resolve({data,fail}); await response;
      // Let the fetch/json continuation and rendering finish before asserting absence.
      await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 50)));
    };
    const reload = () => page.locator('#fixture').dispatchEvent('change');
    try {
      await page.goto(base);
      const initial = await nextRequest();
      await run({page, initial, nextRequest, release, reload, setDates:value => {currentDates=value;}});
      assert.equal(await page.locator('#fixture').inputValue(), 'default', 'tests keep default selector');
      results.push({name,pass:true});
    } catch (error) {results.push({name,pass:false,error:error.message});}
    finally { pending.splice(0).forEach(r => r.resolve({fail:true})); await page.close(); }
  }
  const rejected = async page => {
    assert.equal(await page.locator('.city-card').count(),0,'invalid response must not display clothing cards');
    assert.equal(await page.locator('#prevPage').isDisabled(),true);
    assert.equal(await page.locator('#nextPage').isDisabled(),true);
    assert.match(await page.locator('#featuredGrid').textContent(),/过期|不可用|不匹配/);
  };
  for (const [name, mutate] of [
    ['stale entry on a later pagination page', d => {d.cities[8].data_status='stale';}],
    ['stale snapshot status', d => {d.data_status='stale';}],
    ['missing entry freshness', d => {delete d.cities[0].data_status;}],
    ['yesterday snapshot window', d => {d.today=shift(d.today,-1);d.forecast_end=shift(d.forecast_end,-1);}],
    ['wrong forecast end', d => {d.forecast_end=shift(d.forecast_end,1);}],
    ['entry window differs from snapshot', d => {d.cities[0].end=shift(d.forecast_end,-1);}],
  ]) await test(name, async ({page,initial,release,reload,nextRequest}) => {
    const bad=stamped('must not render'); mutate(bad); await release(initial,bad); await rejected(page);
    await reload(); await release(await nextRequest(),stamped('recovered'));
    assert.equal(await page.locator('.city-card').count(),4,'valid response recovers');
    assert.match(await page.locator('#featuredGrid').textContent(),/recovered/);
  });
  for (const failure of [false,true]) await test(`same-fixture reversed responses (${failure ? 'old failure' : 'old success'})`, async ({page,initial,nextRequest,release,reload}) => {
    await reload(); const newer=await nextRequest();
    await release(newer,stamped('new response'));
    await release(initial,stamped('old response'),failure);
    assert.match(await page.locator('#featuredGrid').textContent(),/new response/);
    assert.doesNotMatch(await page.locator('#featuredGrid').textContent(),/old response|older request failed/);
    assert.equal(await page.locator('#nextPage').isDisabled(),false);
  });
  await test('reversed responses across German midnight', async ({page,initial,nextRequest,release,setDates}) => {
    setDates(nextDates); await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    const newer=await nextRequest(); await release(newer,stamped('new German day',nextDates));
    await release(initial,stamped('yesterday response'));
    assert.match(await page.locator('#featuredGrid').textContent(),/new German day/);
    const shown = await page.locator('#featuredDates').textContent();
    assert.ok(shown.includes(nextDates.today.replace(/(\d+)-(\d+)-(\d+)/,'$1年$2月$3日')));
  });
  await test('latest response has outdated window after midnight', async ({page,initial,nextRequest,release,setDates}) => {
    await release(initial,stamped('initial')); setDates(nextDates);
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await release(await nextRequest(),stamped('yesterday response')); await rejected(page);
  });
  results.forEach(r => console.log(`${r.pass ? 'PASS' : 'FAIL'} ${r.name}${r.error ? ': '+r.error : ''}`));
  assert.deepEqual(errors,[],'no browser errors');
  await browser.close();
  assert.ok(results.every(r => r.pass),`${results.filter(r=>!r.pass).length} featured regressions failed`);
  console.log(`${results.length} featured regression tests passed`);
})().catch(error => {console.error(error);process.exit(1);});
