/* P1 synthetic-only browser: no cloud, metadata or weather downloads. */
const {chromium}=require('../../.local-tools/node_modules/playwright');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const assert=require('node:assert/strict');
const child=spawn(process.env.PYTHON||'python3',['tests/web/serve_lifecycle.py'],{stdio:['pipe','pipe','inherit']});
const queue=[],waiters=[];
readline.createInterface({input:child.stdout}).on('line',line=>{
 const data=JSON.parse(line);if(waiters.length)waiters.shift()(data);else queue.push(data);
});
const event=()=>queue.length?Promise.resolve(queue.shift()):new Promise(resolve=>waiters.push(resolve));
const base='http://127.0.0.1:8005';
const timeout=setTimeout(()=>{child.kill();process.exit(1)},45000);
(async()=>{
 let browser;
 try{
  assert.equal((await event()).event,'ready');
  browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844},permissions:['clipboard-read','clipboard-write']});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:844});await page.goto(base);
   await page.waitForSelector('.city-card');
   const seen=new Set();
   while(true){
    for(const href of await page.locator('.city-card').evaluateAll(nodes=>nodes.map(n=>n.href)))seen.add(href);
    if(await page.locator('#nextPage').isDisabled())break;
    await page.locator('#nextPage').click();
   }
   assert.equal(seen.size,10);
   await page.locator('#prevPage').click();await page.locator('#prevPage').click();
   assert.match(await page.locator('#dateHint').textContent(),/仅支持精选十城/);
   await page.locator('.city-card').first().click();
   await page.waitForSelector('#resultContent:not(.hidden)');
   assert.match(await page.locator('#resultDates').textContent(),/今起14天/);
   await page.locator('#copyAdvice').click();
   assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/演示数据/);
   await page.locator('#shareTrip').click();
   assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/合成数据，仅供测试/);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  const trip='/?view=trip&city_id=berlin&start=2026-10-16&end=2026-10-18&preference=cold';
  await page.goto(base+trip);await page.waitForSelector('#resultContent:not(.hidden)');
  for(const code of ['forecast_preparing','scheduler_unavailable','quota_limited']){
   child.stdin.write(code+'\n');assert.equal((await event()).event,code);
   await page.reload();await page.waitForSelector('#resultStatus button');
   assert.equal(await page.locator('#resultContent').isVisible(),false);
   assert.match(page.url(),/preference=cold/);
  }
  child.stdin.write('complete\n');await event();await page.reload();
  await page.waitForSelector('#resultContent:not(.hidden)');
  await page.goto(base+'/?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal');
  await page.waitForSelector('#resultStatus button');
  assert.match(await page.locator('#resultStatus').textContent(),/五年|齐备/);
  assert.equal(await page.locator('#resultContent').isVisible(),false);
  assert.deepEqual(errors,[]);
  console.log('P1 synthetic browser passed: ten cities, 14-day detail, shared trip, status/recovery, copy/share, 320/390/1280 widths; zero external requests.');
 }finally{
  if(browser)await browser.close();child.stdin.end('stop\n');clearTimeout(timeout);
 }
})().catch(e=>{console.error(e);child.kill();process.exitCode=1});
