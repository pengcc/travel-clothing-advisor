/* Synthetic S2; child process owns data, controls are stdin only. */
const {chromium}=require('../../.local-tools/node_modules/playwright');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const assert=require('node:assert/strict');
const child=spawn(process.env.PYTHON || 'python3',['tests/web/serve_publication.py'],{stdio:['pipe','pipe','inherit']});
const queue=[],waiters=[];
readline.createInterface({input:child.stdout}).on('line',line=>{
  const item=JSON.parse(line); if(waiters.length)waiters.shift()(item);else queue.push(item);
});
const event=()=>queue.length?Promise.resolve(queue.shift()):new Promise(resolve=>waiters.push(resolve));
const base='http://127.0.0.1:8004';
const timeout=setTimeout(()=>{child.kill();process.exit(1)},45000);
(async()=>{
  let browser;
  try {
    const first=await event();assert.equal(first.event,'ready');
    browser=await chromium.launch({channel:'chrome',headless:true});
    const page=await browser.newPage({viewport:{width:390,height:844},permissions:['clipboard-read','clipboard-write']});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
    await page.goto(base);
    await page.waitForFunction(()=>document.querySelector('#featuredGrid').textContent.includes('不可用') || document.querySelector('#featuredGrid').textContent.includes('未准备'));
    assert.equal(await page.locator('.city-card').count(),0);
    const path='/?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-29&preference=normal';
    const result=()=>page.waitForSelector('#resultContent:not(.hidden)');
    await page.goto(base+path);await result();
    const headline=await page.locator('#resultHeadline').textContent();
    assert.match(await page.locator('#synthetic-test-notice').textContent(),/合成数据，仅供测试/);
    await page.locator('#copyAdvice').click();
    assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/演示数据，非真实天气/);
    await page.locator('#shareTrip').click();
    assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/合成数据，仅供测试/);
    child.stdin.write('publish\n');const second=await event();assert.notEqual(first.version,second.version);
    await page.reload();await result();
    assert.notEqual(await page.locator('#resultHeadline').textContent(),headline);
    const data=await page.evaluate(()=>fetch('/api/advice?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-29&preference=normal').then(r=>r.json()));
    assert.equal(data.dataset_version,second.version);
    child.stdin.write('rollback\n');const rollback=await event();assert.equal(rollback.version,first.version);
    await page.reload();await result();assert.equal(await page.locator('#resultHeadline').textContent(),headline);
    await page.goto(base+'/?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal');
    await page.waitForSelector('#resultStatus button');
    assert.equal(await page.locator('#resultContent').isVisible(),false);
    assert.match(await page.locator('#resultStatus').textContent(),/五年|未齐备|不可用/);
    for(const width of [320,390,1280]){
      await page.setViewportSize({width,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    assert.deepEqual(errors,[]);
    console.log('S2 synthetic browser passed: same server v1 → v2 → rollback, rule-driven advice, copy/share labels, partial history/featured unavailable, responsive widths');
    console.log(JSON.stringify({synthetic_source_bytes:first.source_bytes}));
  } finally {
    if(browser)await browser.close();child.stdin.end('stop\n');clearTimeout(timeout);
  }
})().catch(e=>{console.error(e);child.kill();process.exitCode=1});
