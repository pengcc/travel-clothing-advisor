/* Synthetic 穿衣小伙伴 harness only: python3 tests/web/serve_pal.py, then node tests/web/pal-browser.cjs
   Set PAL_SHOT_DIR=<dir> to also save screenshots. */
const {chromium} = require('../../.local-tools/node_modules/playwright');
const assert = require('node:assert/strict');
const base = 'http://127.0.0.1:8008';
const FORBIDDEN = /[雨风云晴阴雪]|太阳/;
const PAL_API = /\/api\/pal(\?|$)/;                   // the page now calls /api/pal?city=<id>

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
      // Tap whatever reaches the speakers: a running peak (0..1) of the real output, not just the switch state.
      window.__tap = {max: 0};
      const connect = AudioNode.prototype.connect;
      AudioNode.prototype.connect = function (target, ...rest) {
        if (target instanceof AudioDestinationNode && !window.__tap.analyser) {
          const an = this.context.createAnalyser(); an.fftSize = 2048; connect.call(this, an); window.__tap.analyser = an;
          const buf = new Float32Array(2048);
          setInterval(() => { an.getFloatTimeDomainData(buf); for (const x of buf) window.__tap.max = Math.max(window.__tap.max, Math.abs(x)); }, 10);
        }
        return connect.call(this, target, ...rest);
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
      ['/pal/berlin/manifest.webmanifest', '/static/pal/apple-touch-icon.png']);

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
    // back link to the homepage is visible (also checked in the unavailable state below)
    assert.equal(await page.locator('#homeLink').isVisible(), true);
    assert.equal(await page.locator('#homeLink').getAttribute('href'), '/');
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
    await page.evaluate(() => { window.__tap.max = 0; });
    await page.locator('#bSound').click();
    await page.waitForFunction(() => window.PalAudio.on);
    assert.equal(await page.evaluate(() => window.__ac.count), 1);
    assert.equal(await page.evaluate(() => window.__ac.instances[0].state), 'running');
    assert.equal(await page.locator('#bSound').getAttribute('aria-pressed'), 'true');
    // The confirmation blip must be clearly audible (measured output peak, full scale = 1.0).
    await page.waitForTimeout(450);
    const blipPeak = await page.evaluate(() => window.__tap.max);
    assert.ok(blipPeak > 0.1 && blipPeak < 0.95, 'power-on blip peak ' + blipPeak);
    // Each warmth cue: peak between -20 dBFS (0.1) and clipping (0.95). Levels 3 and 4 are silent by design.
    await page.evaluate(() => { window.PalAudio.heroLoop = () => {}; });          // the hero animation loop must not leak into a measurement
    const peakOf = async level => {
      await page.evaluate(l => { window.__tap.max = 0; window.PalAudio.replay(l); }, level);
      await page.waitForTimeout(2800);
      return page.evaluate(() => window.__tap.max);
    };
    const peaks = {};
    for (const level of [1, 2, 5, 6]) {
      peaks[level] = await peakOf(level);
      assert.ok(peaks[level] > 0.1 && peaks[level] < 0.95, `level ${level} output peak ${peaks[level]}`);
    }
    for (const level of [3, 4]) {
      await page.evaluate(l => window.PalAudio.replay(l), level);              // stop scheduling new cold/heat cues, let already scheduled ones finish
      await page.waitForTimeout(1800);
      peaks[level] = await peakOf(level);
      assert.ok(peaks[level] < 0.005, `level ${level} should be silent, peak ${peaks[level]}`);
    }
    console.log('measured output peaks', JSON.stringify({blip: +blipPeak.toFixed(3), ...Object.fromEntries(Object.entries(peaks).map(([k, v]) => [k, +v.toFixed(3)]))}));
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
      await page.unroute(PAL_API);
      await page.route(PAL_API, route => route.fulfill({status: 200, json: body}));
    };
    const iso = ms => new Date(ms).toISOString().replace(/\.\d+Z$/, '+00:00');
    await stale({stale: true, weather_fetched_at: iso(Date.now() - 14 * 3600e3)});
    await poke(); await page.waitForSelector('#staleBanner:not([hidden])');
    assert.match(await page.locator('#staleBanner').textContent(), /新数据到了会自动更新/);
    await stale({stale: false, data_version: 'changed-version'});          // new data: screen updates, short notice
    await poke(); await page.waitForSelector('#toast:not([hidden])');
    assert.equal(await page.locator('#staleBanner').isVisible(), false);

    await page.unroute(PAL_API);
    await page.route(PAL_API, route => route.abort());                // network error, data well under 48 h: keep the screen
    await poke(); await page.waitForTimeout(400);
    assert.equal(await state(), 'ready');

    await page.unroute(PAL_API);
    await page.route(PAL_API, route => route.fulfill({status: 503, json: {code: 'temporarily_unavailable', error: 'x'}}));
    await poke(); await settled('unavailable');                            // explicit 503: unavailable at once
    assert.equal(await page.locator('#scene').isVisible(), false);
    assert.equal(await page.locator('#heroImg').isVisible(), false);
    assert.equal(await page.locator('#unavailable').isVisible(), true);
    assert.equal(await page.evaluate(() => window.PalAudio.on), false);

    await page.unroute(PAL_API);
    await page.route(PAL_API, route => route.continue());
    await poke(); await settled('ready');                                  // recovers when data is back
    for (const bad of [{status: 500, body: 'oops'}, {status: 200, body: 'not json'}, {status: 200, body: '{"days":[]}'}]) {
      await page.unroute(PAL_API);                                    // not a network error: never keep the screen
      await page.route(PAL_API, route => route.fulfill({status: bad.status, body: bad.body}));
      await poke(); await settled('unavailable');
      await page.unroute(PAL_API);
      await page.route(PAL_API, route => route.continue());
      await poke(); await settled('ready');
    }
    await stale({weather_fetched_at: iso(Date.now() - 60 * 3600e3)});
    await poke(); await settled('unavailable');                            // older than 48 h: never shown
    await page.unroute(PAL_API);

    // ---- V2 on first load: 503 shows the unavailable state without any cold/heat animation
    const fresh = await context.newPage();
    await fresh.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await fresh.route(PAL_API, route => route.fulfill({status: 503, json: {code: 'temporarily_unavailable', error: 'x'}}));
    await fresh.goto(base + '/pal/berlin');
    await fresh.waitForSelector('body[data-state="unavailable"]');
    assert.equal(await fresh.locator('#scene').isVisible(), false);
    assert.equal(await fresh.locator('.hero').isVisible(), false);
    assert.equal(await fresh.locator('#fxFront > *').count(), 0);
    assert.doesNotMatch(await fresh.locator('body').innerText(), /示例|模拟/);
    assert.equal(await fresh.locator('#homeLink').isVisible(), true);
    assert.equal(await fresh.locator('#homeLink').getAttribute('href'), '/');

    // ---- Issue #111: chooser, per-city pages, per-city API calls, standalone navigation
    const cityPage = await context.newPage();
    const cityErrors = [];
    cityPage.on('pageerror', e => cityErrors.push(e.message));
    const apiCalls = [];
    cityPage.on('request', r => { if (PAL_API.test(r.url())) apiCalls.push(new URL(r.url()).search); });
    await cityPage.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await cityPage.goto(base + '/pal');
    assert.equal(await cityPage.locator('a.city').count(), 10);
    const chooserWords = await cityPage.evaluate(() => document.body.textContent + ' ' + [...document.querySelectorAll('[alt],[aria-label],[title]')].map(e => [e.alt, e.getAttribute('aria-label'), e.title].join(' ')).join(' '));
    assert.doesNotMatch(chooserWords, FORBIDDEN);
    assert.equal(await cityPage.locator('#homeLink').isVisible(), true);          // normal browser tab: the way back to the homepage is there
    assert.deepEqual(apiCalls, []);                                              // the chooser asks for no weather data
    if (process.env.PAL_SHOT_DIR) await cityPage.screenshot({path: process.env.PAL_SHOT_DIR + '/pal-chooser-390.png', fullPage: true});
    await cityPage.locator('a.city', {hasText: '慕尼黑'}).click();
    await cityPage.waitForURL(base + '/pal/munich');
    await cityPage.waitForSelector('body[data-state="ready"]');
    assert.match(await cityPage.title(), /慕尼黑/);
    assert.equal(await cityPage.locator('#where').textContent(), '慕尼黑');
    assert.equal(await cityPage.locator('body').getAttribute('data-city'), 'munich');
    assert.equal(await cityPage.locator('link[rel=manifest]').getAttribute('href'), '/pal/munich/manifest.webmanifest');
    assert.deepEqual(apiCalls, ['?city=munich']);
    assert.equal(await cityPage.locator('#switchLink').isVisible(), true);
    assert.equal(await cityPage.locator('#switchLink').getAttribute('href'), '/pal');
    assert.equal(await cityPage.locator('#homeLink').isVisible(), true);
    const munichWords = await cityPage.evaluate(() => {
      const copy = document.body.cloneNode(true);
      copy.querySelectorAll('[data-allow-words],script').forEach(e => e.remove());
      return copy.textContent + ' ' + [...document.querySelectorAll('[alt],[aria-label],[title]')].filter(e => !e.closest('[data-allow-words]')).map(e => [e.alt, e.getAttribute('aria-label'), e.title].join(' ')).join(' ');
    });
    assert.doesNotMatch(munichWords, FORBIDDEN);
    if (process.env.PAL_SHOT_DIR) await cityPage.screenshot({path: process.env.PAL_SHOT_DIR + '/pal-munich-390.png', fullPage: true});
    await cityPage.locator('#switchLink').click();                                // 换城市 returns to the chooser
    await cityPage.waitForURL(base + '/pal');
    await cityPage.goto(base + '/pal/freiburg');                                  // not a featured city: no page
    assert.match(await cityPage.locator('body').innerText(), /页面不存在/);
    assert.deepEqual(cityErrors, []);

    // Standalone (opened from the home-screen icon): the link to '/' is outside the manifest scope, so it is hidden;
    // 换城市 stays. Two paths are checked: iOS (navigator.standalone) and the display-mode media query.
    const iosContext = await browser.newContext({viewport: {width: 390, height: 844}});
    await iosContext.addInitScript(() => Object.defineProperty(navigator, 'standalone', {get: () => true}));
    const ios = await iosContext.newPage();
    await ios.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    await ios.goto(base + '/pal/munich');
    await ios.waitForSelector('body[data-state="ready"]');
    assert.equal(await ios.locator('#homeLink').isVisible(), false);
    assert.equal(await ios.locator('#switchLink').isVisible(), true);
    await ios.goto(base + '/pal');
    assert.equal(await ios.locator('#homeLink').isVisible(), false);
    assert.equal(await ios.locator('a.city').count(), 10);
    await iosContext.close();
    // Headless Chrome cannot emulate display-mode, so the media-query path is checked in the CSSOM instead:
    // the loaded stylesheets must contain a (display-mode: standalone) rule that hides #homeLink and not #switchLink.
    const hides = async path => {
      const probe = await context.newPage();
      await probe.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
      await probe.goto(base + path);
      const found = await probe.evaluate(() => {
        const out = [];
        for (const sheet of document.styleSheets) for (const rule of sheet.cssRules)
          if (rule instanceof CSSMediaRule && /display-mode:\s*standalone/.test(rule.conditionText))
            for (const inner of rule.cssRules) out.push([inner.selectorText, inner.style.display]);
        return out;
      });
      await probe.close();
      return found;
    };
    for (const path of ['/pal/hamburg', '/pal']) {
      const rules = await hides(path);
      assert.ok(rules.some(([selector, display]) => selector === '#homeLink' && display === 'none'), path + ' hides #homeLink in display-mode: standalone');
      assert.ok(!rules.some(([selector]) => /switchLink/.test(selector)), path + ' keeps 换城市');
    }

    assert.deepEqual(errors, []);
    console.log('pal browser checks passed: chooser, per-city pages and API calls, standalone navigation, page, 7 days, no weather words/scene, time+temperature in scene, small prints, sound off by default and resume-failure reset, stale label, refresh rules, 503 state, widths');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
