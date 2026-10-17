const {chromium}=require('../../../.local-tools/node_modules/playwright');
const {execFileSync}=require('node:child_process');
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true});
 try {
  const p=await b.newPage({viewport:{width:375,height:844}});
  await p.goto('http://127.0.0.1:8002');await p.waitForSelector('.city-card');
  await p.screenshot({path:'docs/verification/issue27/home-375.png',fullPage:true});
  await p.locator('.city-card').first().click();await p.waitForSelector('#resultContent:not(.hidden)');
  await p.screenshot({path:'docs/verification/issue27/forecast-375.png',fullPage:true});
  const h=JSON.parse(execFileSync('python3',['-c',`import sys,json
sys.path.insert(0,'tests/web')
from test_history import HistoryTests
c=HistoryTests();c.setUp();c.provider.value=lambda d:0 if d.year==2021 else 8
c.worker().fill(c.jobs());print(json.dumps(c.advice()))`],{encoding:'utf8'}));
  await p.route('**/api/advice?*',r=>r.fulfill({json:h}));
  await p.goto('http://127.0.0.1:8002/?view=trip&city_id=berlin&start=2026-11-02&end=2026-11-05&preference=normal');await p.waitForSelector('#resultContent:not(.hidden)');
  await p.screenshot({path:'docs/verification/issue27/history-375.png',fullPage:true});
 } finally {await b.close()}
})();
