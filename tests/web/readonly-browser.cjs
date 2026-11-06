/* Synthetic S1 harness only: python3 tests/web/serve_readonly.py */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = 'http://127.0.0.1:8003';
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}, permissions:['clipboard-read','clipboard-write']});
    const errors=[];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
    const result = () => page.waitForSelector('#resultContent:not(.hidden)');
    await page.goto(base);
    await page.waitForSelector('.city-card');
    assert.match(await page.locator('#synthetic-test-notice').textContent(), /合成数据，仅供测试/);
    assert.ok(await page.locator('.city-card').count()>0);
    await page.locator('.city-card').first().click(); await result();
    assert.match(await page.locator('#resultDates').textContent(), /今起14天/);
    await page.locator('#copyAdvice').click();
    assert.match(await page.evaluate(()=>navigator.clipboard.readText()), /演示数据，非真实天气/);
    await page.locator('#shareTrip').click();
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()), '合成数据，仅供测试；非真实天气或历史资料\n'+base+'/?view=city&city_id=berlin');
    await page.reload(); await result();
    await page.locator('#back').click(); await page.waitForSelector('.city-card');
    await page.locator('#city').fill('柏林');
    await page.waitForSelector('#cityOptions button');
    assert.match(await page.locator('#cityOptions').textContent(), /Berlin/);
    for (const end of ['2026-10-29','2026-11-05']) {
      const start=end==='2026-11-05'?'2026-11-02':'2026-10-16';
      await page.goto(base+'/?view=trip&city_id=berlin&start='+start+'&end='+end+'&preference=normal');
      await result();
      assert.match(await page.locator('#resultKind').textContent(), /模拟数据/);
      assert.match(await page.locator('#source').textContent(), /合成数据，仅供测试/);
      await page.locator('#copyAdvice').click();
      assert.match(await page.evaluate(()=>navigator.clipboard.readText()), /演示数据，非真实天气/);
      await page.locator('#shareTrip').click();
      assert.equal(await page.evaluate(()=>navigator.clipboard.readText()), '合成数据，仅供测试；非真实天气或历史资料\n'+page.url());
      await page.reload(); await result();
      assert.match(await page.locator('#synthetic-test-notice').textContent(), /合成数据，仅供测试/);
      assert.match(await page.locator('#resultKind').textContent(), /模拟数据/);
    }
    assert.match(await page.locator('#resultMode').textContent(), /五年同期/);
    for (const width of [320,390,1280]) {
      await page.setViewportSize({width,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    await page.goto(base+'/?view=trip&city_id=123456&start=2026-10-16&end=2026-10-18&preference=normal');
    await page.waitForSelector('#resultStatus button');
    assert.equal(await page.locator('#resultContent').isVisible(), false);
    assert.match(await page.locator('#resultStatus').textContent(), /暂不可用|范围/);
    await page.route('**/api/advice?*',route=>route.fulfill({status:503,json:{code:'history_incomplete',error:'过去五年同期资料尚未齐备。'}}));
    await page.goto(base+'/?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal');
    await page.waitForSelector('#resultStatus button');
    assert.equal(await page.locator('#resultContent').isVisible(),false);
    assert.match(await page.locator('#resultStatus').textContent(), /五年/);
    assert.deepEqual(errors,[]);
    console.log('S1 browser checks passed: homepage, city, 14-day trip, five-year history, copy/share/reload, unsupported city and responsive widths');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1)});
