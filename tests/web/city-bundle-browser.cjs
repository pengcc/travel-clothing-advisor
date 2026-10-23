/* Offline synthetic API/DOM flow using a temporary Git-format dataset and the Vercel handler locally. */
const {chromium} = require('../../.local-tools/node_modules/playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    for (const width of [1280, 390, 320]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      const base = process.env.UI_BASE_URL || 'http://127.0.0.1:8007';
      await page.request.post(base + '/__test/reset');
      await page.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
      await page.goto(process.env.UI_BASE_URL || 'http://127.0.0.1:8007');
      await page.waitForFunction(() => document.querySelector('.subnote span').textContent.includes('精选十城'));
      assert.match(await page.locator('#dateHint').innerText(), /不保证都有资料/);
      for (const selector of ['#home', '#result']) {
        for (const href of ['https://open-meteo.com/', 'https://creativecommons.org/licenses/by/4.0/', 'https://www.geonames.org/'])
          assert.ok(await page.locator(selector + ' a[href="' + href + '"]').count());
      }
      await page.locator('#city').fill('unsupported');
      await page.locator('#cityOptions').waitFor({state:'visible'});
      assert.match(await page.locator('#cityOptions').innerText(), /不在支持范围/);
      await page.locator('#city').fill('Berlin');
      await page.locator('#cityOptions button').first().waitFor();
      await page.locator('#city').press('ArrowDown');
      await page.keyboard.press('Enter');
      await page.locator('#start').fill('2026-10-18');
      await page.locator('#end').fill('2026-10-20');
      await page.locator('#start').fill('2026-10-19');
      assert.equal(await page.locator('#end').inputValue(), '2026-10-20');
      assert.equal(await page.locator('#end').getAttribute('min'), '2026-10-19');
      await page.locator('#start').fill('2026-10-21');
      assert.equal(await page.locator('#end').inputValue(), '');
      await page.locator('#end').fill('2026-10-23');
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#end').min === '2026-10-21');
      assert.equal(await page.locator('#end').inputValue(), '2026-10-23');
      for (const [preference, label] of [['cold', '怕冷'], ['normal', '正常'], ['hot', '怕热']]) {
        await page.locator('[data-feeling="' + preference + '"]').click();
        await page.locator('#tripForm [type="submit"]').click();
        await page.locator('#resultContent').waitFor({state:'visible', timeout:5000}).catch(async error => {
          console.error(await page.locator('#cityError, #dateError, #formError, #resultStatus').allTextContents());
          throw error;
        });
        assert.match(await page.locator('#resultMode').innerText(), /气温预报/);
        assert.ok((await page.locator('#resultDates').innerText()).includes('冷热偏好：' + label));
        await page.locator('#back').click();
        await page.locator('#home').waitFor({state:'visible'});
        assert.equal(await page.locator('#start').inputValue(), '2026-10-21');
        assert.equal(await page.locator('#end').inputValue(), '2026-10-23');
      }
      const cards = page.locator('#featuredGrid .city-card');
      await cards.first().waitFor();
      assert.match(await cards.nth(0).innerText(), /柏林[\s\S]*查看14天预报/);
      assert.match(await cards.nth(1).innerText(), /慕尼黑[\s\S]*历史备衣参考（非预报）/);
      assert.match(await cards.nth(2).innerText(), /汉堡[\s\S]*数据暂缺/);
      assert.equal(await cards.nth(2).getAttribute('href'), null);
      await cards.nth(1).click();
      await page.locator('#resultContent').waitFor({state:'visible'});
      assert.match(await page.locator('#resultMode').innerText(), /过去五年同期参考，不是本次旅行预报/);
      await page.reload();
      await page.locator('#resultContent').waitFor({state:'visible'});
      assert.match(await page.locator('#resultCity').innerText(), /慕尼黑/);
      await page.locator('#back').click();
      await cards.first().waitFor();
      await page.locator('#nextPage').click();
      assert.equal(await cards.count(), 4);
      await page.locator('#nextPage').click();
      assert.equal(await cards.count(), 2);
      assert.equal(await page.locator('#pageDisplay').innerText(), '3 / 3');
      await page.locator('#prevPage').click();
      await page.locator('#prevPage').click();
      await page.route('**/static/icons/**', route => route.abort());
      await cards.nth(0).click();
      await page.locator('#resultContent').waitFor({state:'visible'});
      assert.match(await page.locator('#resultMode').innerText(), /今起14天气温预报/);
      assert.ok((await page.locator('#resultHeadline').innerText()).length);
      await page.locator('#back').click();
      await cards.first().waitFor();
      await page.locator('#start').fill('2026-10-16');
      await page.locator('#end').fill('2026-10-16');
      await cards.nth(0).click();
      await page.locator('#resultContent').waitFor({state:'visible'});
      const copied = [];
      await page.exposeFunction('captureCopy', value => copied.push(value));
      await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {value:{writeText: window.captureCopy}, configurable:true}));
      await page.locator('#copyAdvice').click();
      await page.waitForFunction(() => document.querySelector('#toast').textContent === '已复制建议');
      assert.match(copied[0], /资料获取时间/);
      assert.match(copied[0], /creativecommons.org/);
      await page.locator('#shareTrip').click();
      await page.waitForFunction(() => document.querySelector('#toast').textContent.includes('已复制行程链接'));
      assert.match(copied[1], /view=city&city_id=berlin/);
      await page.request.post(base + '/__test/advance');
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await page.waitForFunction(() => document.querySelector('#resultMode').textContent.includes('过去五年'));
      assert.match(await page.locator('#resultMode').innerText(), /不是本次旅行预报/);
      assert.equal(await page.locator('#start').getAttribute('min'), '2026-10-17');
      assert.equal(await page.locator('#start').inputValue(), '');
      assert.equal(await page.locator('#end').inputValue(), '');
      await page.goto(base + '?view=trip&city_id=hamburg&start=2026-10-21&end=2026-10-23&preference=hot');
      await page.locator('#resultStatus button').first().waitFor();
      assert.match(await page.locator('#resultStatus').innerText(), /当前没有可用建议/);
      await page.locator('#back').click();
      await cards.first().waitFor();
      assert.equal(await page.locator('#start').inputValue(), '2026-10-21');
      assert.equal(await page.locator('#end').inputValue(), '2026-10-23');
      assert.equal(await page.locator('[data-feeling="hot"]').getAttribute('aria-pressed'), 'true');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('PASS: synthetic Production bundle; mixed states, 4/4/2, dates/restoration, sources/copy/share, midnight, failure preservation; 1280/390/320');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode=1;});
