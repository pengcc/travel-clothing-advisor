/* Offline fixture server: python3 -m web.server --fixtures --port 8001 */
const {chromium} = require('../../.local-tools/node_modules/playwright');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:8001';
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    for (const width of [320,390,1280]) for (const density of [1,2]) {
      const page = await browser.newPage({viewport:{width,height:844},deviceScaleFactor:density});
      const errors = [], icons = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('response', r => { if(r.url().includes('/icons/')) {assert.equal(r.status(),200);icons.push(r.url());} });
      await page.goto(base); await page.waitForSelector('.city-card');
      await page.evaluate(async () => {
        const {WarmthIndicator,CityCard} = await import('/static/components.js');
        const host = document.createElement('div'); host.id='iconTest'; document.body.append(host);
        for(let level=1;level<=6;level++) host.append(WarmthIndicator(level));
        host.append(WarmthIndicator(null),WarmthIndicator(null,false));
        const card=CityCard({city:{name:'Test',zh:'测试'},warmth_indicator_level:null},'#');
        host.append(card);
      });
      await page.waitForFunction(() => [...document.querySelectorAll('.warmth-icon img')].every(i => i.complete && i.naturalWidth>0));
      const levels = await page.locator('#iconTest > .warmth-mark img').evaluateAll(imgs => imgs.map(i=>i.currentSrc));
      for(let i=0;i<6;i++) assert.ok(levels[i].endsWith(`/${density}x/warmth-l${i+1}.webp`));
      assert.match(await page.locator('#iconTest > .warmth-mark').nth(6).textContent(),/冷热变化大/);
      assert.equal(await page.locator('#iconTest > .warmth-mark').nth(7).locator('img').count(),0);
      assert.match(await page.locator('#iconTest .city-card').textContent(),/暂无白天参考/);
      assert.ok(icons.every(url=>url.endsWith('.webp')),'no duplicate PNG download');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      if(width===390 && density===2) await page.screenshot({path:'.local-tools/issue40-home.png',fullPage:true});
      assert.deepEqual(errors,[]);
      await page.close();
    }
    // Review #5561693950: warnings must coexist with a representative level.
    for (const width of [320,390,1280]) for (const [scenario,level,kind] of [['colder',2,'cold'],['warmer',4,'warm'],['stable',4,null],['split',null,'mixed']]) {
      const page = await browser.newPage({viewport:{width,height:844}});
      const fixture = await (await page.request.get(`${base}/api/featured?fixture=${scenario}`)).json();
      await page.route('**/api/featured?*', route => route.fulfill({json:fixture}));
      await page.goto(base); await page.waitForSelector('.city-card');
      const cards = page.locator('.city-card');
      for (let i=0;i<await cards.count();i++) {
        const card=cards.nth(i), warning=card.locator('.card-variation');
        const primary=card.locator('.warmth-host img');
        assert.equal(await primary.count(),1,'primary indicator preserved');
        assert.ok((await primary.getAttribute('src')).includes(level===null?'alert-variation':`warmth-l${level}`));
        assert.ok(await primary.evaluate(img => img.getBoundingClientRect().width >= 64),'featured illustration remains legible');
        if (scenario==='stable') {
          assert.equal(await warning.count(),0,'no warning without backend variation');
          assert.equal(await card.locator('img[src*="alert-variation"]').count(),0);
        } else {
          assert.equal(await warning.locator('img').count(),0,'card warning uses no miniature mascot');
          assert.equal(await warning.textContent(),fixture.cities[i].packing_variation_summary,'backend summary preserved');
          assert.equal(fixture.cities[i].packing_variation_kind,kind,'backend direction matches fixture');
          assert.equal(await warning.evaluate((el,k) => el.classList.contains('card-variation--'+k),kind),true,'notice style driven by backend direction');
          const bg=await warning.evaluate(el => getComputedStyle(el).backgroundColor);
          if(kind==='cold') assert.equal(bg,'rgb(237, 245, 251)','Scheme A cold blue');
          if(kind==='warm') assert.equal(bg,'rgb(255, 244, 229)','Scheme A warm amber');
          if(kind==='mixed') assert.notEqual(await warning.evaluate(el => getComputedStyle(el).backgroundImage),'none','Scheme A mixed gradient');
          assert.equal(await warning.evaluate(el => getComputedStyle(el,'::before').content),'"!"','clear CSS warning sign');
        }
      }
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      if(width===390 && scenario==='colder') await page.screenshot({path:'.local-tools/issue40-card-variation.png',fullPage:true});
      await page.close();
    }
    for(const mode of ['png','none']) {
      const page=await browser.newPage({viewport:{width:320,height:844}});
      await page.route('**/static/icons/**', route => mode==='none'||route.request().url().endsWith('.webp') ? route.abort() : route.continue());
      await page.goto(base); await page.waitForSelector('.city-card');
      await page.waitForFunction(mode=>[...document.querySelectorAll('.warmth-icon')].every(p=>mode==='none'?p.hidden:p.querySelector('img').complete&&p.querySelector('img').naturalWidth>0),mode);
      assert.ok((await page.locator('.warmth-name').first().textContent()).length>0);
      assert.ok((await page.locator('.card-variation').first().textContent()).length>0,'warning text survives image failures');
      if(mode==='png') assert.ok((await page.locator('.warmth-icon img').first().evaluate(i=>i.currentSrc)).endsWith('.png'));
      await page.close();
    }
    const page=await browser.newPage({viewport:{width:320,height:844}});
    const context=await (await page.request.get(base+'/api/context')).json();
    await page.goto(`${base}/?view=trip&city_id=berlin&start=${context.today}&end=${context.forecast_end}&preference=normal`);
    // Fixture selectors stay explicitly opt-in; inject only advice to test the real result renderer.
    await page.route('**/api/advice?*',async route=>{
      const url=new URL(route.request().url());url.searchParams.set('fixture','split');
      await route.fulfill({response:await page.request.get(url.toString())});
    });
    await page.reload(); await page.waitForSelector('#resultContent:not(.hidden)');
    await page.waitForFunction(()=>document.querySelector('#spanRemind img')?.naturalWidth>0);
    assert.match(await page.locator('#resultWarmthMark').textContent(),/冷热变化大/);
    assert.ok((await page.locator('#spanText').textContent()).length>0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:'.local-tools/issue40-result.png',fullPage:true});
    await page.route('**/static/icons/**',route=>route.abort());
    await page.reload(); await page.waitForSelector('#resultContent:not(.hidden)');
    await page.waitForFunction(()=>document.querySelector('#spanRemind picture')?.hidden);
    assert.ok((await page.locator('#spanText').textContent()).length>0);
    console.log('PASS: levels 1–6, null/no-reference, 320/390/1280px, 1x/2x WebP, PNG retry, all-image failure, result variation, no normal image 404/duplicate PNG');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
