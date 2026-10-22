/* Real API/DOM flow using the Git dataset and the Vercel handler locally. */
const {chromium} = require('../../.local-tools/node_modules/playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    for (const width of [1280, 390]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(process.env.UI_BASE_URL || 'http://127.0.0.1:8007');
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
      await cards.nth(0).click();
      await page.locator('#resultContent').waitFor({state:'visible'});
      assert.match(await page.locator('#resultMode').innerText(), /今起14天气温预报/);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('PASS: bundled Berlin forecast, Munich history, Hamburg unavailable; details, reload, pagination; desktop/mobile');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode=1;});
