/* Synthetic 穿衣小伙伴 harness only: python3 tests/web/serve_pal.py, then node tests/web/pal-browser.cjs
   Set PAL_SHOT_DIR=<dir> to also save screenshots. */
const {chromium} = require('../../.local-tools/node_modules/playwright');
const assert = require('node:assert/strict');
const base = 'http://127.0.0.1:8008';
const FORBIDDEN = /[雨风云晴阴雪]|太阳/;

(async () => {
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 390, height: 844}});
    await context.addInitScript(() => {            // count AudioContext constructions without replacing behaviour
      window.__ac = {count: 0, instances: []};
      const Original = window.AudioContext;
      window.AudioContext = class extends Original {
        constructor(...args) { super(...args); window.__ac.count++; window.__ac.instances.push(this); }
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    const ready = () => page.waitForSelector('body[data-state="ready"]');
    const state = () => page.evaluate(() => document.body.dataset.state);
    const poke = async () => { await page.waitForTimeout(300); await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); };   // let an in-flight refresh finish first
    const settled = async want => { await page.waitForFunction(w => document.body.dataset.state === w, want); };
    const real = async () => (await (await page.request.get(base + '/api/pal')).json());

    // ---- V1: page, name, 7 days, 3 slots
    await page.goto(base + '/pal/berlin');
    await ready();
    assert.match(await page.title(), /穿衣小伙伴/);
    assert.equal(await page.locator('#strip .day').count(), 7);
    assert.ok(await page.locator('#slots .slot').count() === 3);
    assert.equal((await page.goto(base + '/pal/berlin/')).status(), 200);
    await ready();
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll('link[rel=manifest],link[rel=apple-touch-icon]')].map(l => l.getAttribute('href'))),
      ['/static/pal/manifest.webmanifest', '/static/pal/apple-touch-icon.png']);

    // ---- V5: only cold/heat content; no weather words or scene elements outside the two small prints
    const words = await page.evaluate(() => {
      const copy = document.body.cloneNode(true);
      copy.querySelectorAll('[data-allow-words],script').forEach(e => e.remove());
      const attrs = [...document.querySelectorAll('[alt],[aria-label],[title]')]
        .filter(e => !e.closest('[data-allow-words]')).map(e => [e.alt, e.getAttribute('aria-label'), e.title].join(' ')).join(' ');
      return copy.textContent + ' ' + attrs;
    });
    assert.doesNotMatch(words, FORBIDDEN);
    assert.equal(await page.locator('.cloud,.drop,.snowf,.gust,.leaf,.sun,.moon,.umb,.bolt,.flash,.stars').count(), 0);

    // ---- V7: time and temperature inside the animation area; three small prints; fixture label
    assert.ok(await page.evaluate(() => document.getElementById('scene').contains(document.querySelector('.mk.on b'))));
    assert.match(await page.locator('.mk.on b').textContent(), /°/);
    assert.match(await page.locator('#thTimeT').textContent(), /^\d\d:\d\d$/);
    assert.ok(await page.evaluate(() => document.getElementById('scene').contains(document.getElementById('thTimeT'))));
    assert.match(await page.locator('#dataTime').textContent(), /数据时间/);
    assert.match(await page.locator('#caveat').textContent(), /未针对儿童调校/);
    assert.match(await page.locator('#d9note').textContent(), /不代表实际天气/);
    assert.match(await page.locator('#fixtureBanner').textContent(), /模拟数据/);
    assert.equal(await page.locator('#staleBanner').isVisible(), false);
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({width, height: 844});
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no horizontal scroll at ' + width);
    }
    await page.setViewportSize({width: 390, height: 844});
    if (process.env.PAL_SHOT_DIR) await page.screenshot({path: process.env.PAL_SHOT_DIR + '/pal-390.png', fullPage: true});

    // ---- V6: sound default off, only a click creates the AudioContext
    assert.equal(await page.evaluate(() => window.__ac.count), 0);
    assert.equal(await page.locator('#bSound').getAttribute('aria-pressed'), 'false');
    await page.locator('#hero').dispatchEvent('click');                            // nudge only, still silent
    assert.equal(await page.evaluate(() => window.__ac.count), 0);
    await page.locator('#bSound').click();
    await page.waitForFunction(() => window.PalAudio.on);
    assert.equal(await page.evaluate(() => window.__ac.count), 1);
    assert.equal(await page.evaluate(() => window.__ac.instances[0].state), 'running');
    assert.equal(await page.locator('#bSound').getAttribute('aria-pressed'), 'true');
    await page.locator('#bSound').click();
    assert.equal(await page.evaluate(() => window.PalAudio.on), false);
    assert.equal(await page.locator('#bSound').getAttribute('aria-pressed'), 'false');
    // turn on again, hide the page, come back with a failing resume: the switch returns to off
    await page.locator('#bSound').click();
    await page.waitForFunction(() => window.PalAudio.on);
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.evaluate(() => {
      AudioContext.prototype.resume = () => Promise.reject(new Error('blocked'));
      Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForFunction(() => document.getElementById('bSound').getAttribute('aria-pressed') === 'false');
    assert.equal(await page.evaluate(() => window.PalAudio.on), false);

    // ---- stale label (data from an earlier day), D18 refresh and failure rules
    const stale = async patch => {
      const body = Object.assign(await real(), patch);
      await page.unroute('**/api/pal');
      await page.route('**/api/pal', route => route.fulfill({status: 200, json: body}));
    };
    const iso = ms => new Date(ms).toISOString().replace(/\.\d+Z$/, '+00:00');
    await stale({stale: true, weather_fetched_at: iso(Date.now() - 14 * 3600e3)});
    await poke(); await page.waitForSelector('#staleBanner:not([hidden])');
    assert.match(await page.locator('#staleBanner').textContent(), /新数据到了会自动更新/);
    await stale({stale: false, data_version: 'changed-version'});          // new data: screen updates, short notice
    await poke(); await page.waitForSelector('#toast:not([hidden])');
    assert.equal(await page.locator('#staleBanner').isVisible(), false);

    await page.unroute('**/api/pal');
    await page.route('**/api/pal', route => route.abort());                // network error, data well under 48 h: keep the screen
    await poke(); await page.waitForTimeout(400);
    assert.equal(await state(), 'ready');

    await page.unroute('**/api/pal');
    await page.route('**/api/pal', route => route.fulfill({status: 503, json: {code: 'temporarily_unavailable', error: 'x'}}));
    await poke(); await settled('unavailable');                            // explicit 503: unavailable at once
    assert.equal(await page.locator('#scene').isVisible(), false);
    assert.equal(await page.locator('#heroImg').isVisible(), false);
    assert.equal(await page.locator('#unavailable').isVisible(), true);
    assert.equal(await page.evaluate(() => window.PalAudio.on), false);

    await page.unroute('**/api/pal');
    await page.route('**/api/pal', route => route.continue());
    await poke(); await settled('ready');                                  // recovers when data is back
    for (const bad of [{status: 500, body: 'oops'}, {status: 200, body: 'not json'}, {status: 200, body: '{"days":[]}'}]) {
      await page.unroute('**/api/pal');                                    // not a network error: never keep the screen
      await page.route('**/api/pal', route => route.fulfill({status: bad.status, body: bad.body}));
      await poke(); await settled('unavailable');
      await page.unroute('**/api/pal');
      await page.route('**/api/pal', route => route.continue());
      await poke(); await settled('ready');
    }
    await stale({weather_fetched_at: iso(Date.now() - 60 * 3600e3)});
    await poke(); await settled('unavailable');                            // older than 48 h: never shown
    await page.unroute('**/api/pal');

    // ---- V2 on first load: 503 shows the unavailable state without any cold/heat animation
    const fresh = await context.newPage();
    await fresh.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await fresh.route('**/api/pal', route => route.fulfill({status: 503, json: {code: 'temporarily_unavailable', error: 'x'}}));
    await fresh.goto(base + '/pal/berlin');
    await fresh.waitForSelector('body[data-state="unavailable"]');
    assert.equal(await fresh.locator('#scene').isVisible(), false);
    assert.equal(await fresh.locator('.hero').isVisible(), false);
    assert.equal(await fresh.locator('#fxFront > *').count(), 0);
    assert.doesNotMatch(await fresh.locator('body').innerText(), /示例|模拟/);

    assert.deepEqual(errors, []);
    console.log('pal browser checks passed: page, 7 days, no weather words/scene, time+temperature in scene, small prints, sound off by default and resume-failure reset, stale label, refresh rules, 503 state, widths');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
