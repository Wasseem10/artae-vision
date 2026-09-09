// Run with NODE_PATH pointing at Playwright, or with Playwright installed locally.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1100}});
    page.on('pageerror',e=>console.log('PAGE_ERROR',e.message));
    page.on('console',m=>{if(m.type()==='error')console.log('CONSOLE',m.text().slice(0,300));});
    await page.goto(process.env.ARTAE_TEST_URL || 'http://127.0.0.1:4173/demo');
    const input=process.env.ARTAE_TEST_FILE;
    const label=input?require('node:path').basename(input):'Sample: person in view';
    if(process.env.ARTAE_TEST_JOB)await page.getByLabel('1. What should it watch for?').selectOption(process.env.ARTAE_TEST_JOB);
    if(input){await page.getByLabel('2. Connect video').selectOption('file');await page.getByLabel('Choose a video').setInputFiles(input);}
    await page.getByRole('button',{name:'Start agent',exact:true}).click();
    await page.waitForFunction(()=>/Analyzing real video|Stopped · history kept/.test(document.body.innerText)||document.querySelector('[role="alert"]'),{},{timeout:60000});
    console.log('STATE', await page.locator('body').innerText());
    await page.screenshot({path:'browser-monitor-qa.png',fullPage:true});
    assert.deepEqual((await page.getByRole('alert').allTextContents()).filter(t=>t.trim()),[],'Browser must start without errors');
    await page.waitForFunction(()=> /[1-9]\d* frames analyzed/.test(document.body.innerText),{},{timeout:20000});
    await page.waitForTimeout(12000);
    const stop=page.getByRole('button',{name:'Stop agent',exact:true});if(await stop.count())await stop.click();
    await page.waitForTimeout(800);
    console.log('STOPPED',await page.locator('body').innerText());
    await page.screenshot({path:'browser-monitor-stopped.png',fullPage:true});
    if(process.env.ARTAE_EXPECT_EVENTS==='yes')assert.ok(await page.getByRole('button',{name:'Review footage',exact:true}).count(),'Real detection must create an event');
    if(process.env.ARTAE_EXPECT_EVENTS==='no')assert.equal(await page.getByRole('button',{name:'Review footage',exact:true}).count(),0,'Negative footage must not create an event');
    const history=page.getByRole('button').filter({hasText:label});
    assert.ok(await history.count(),'Stopped session should appear in history');
    await page.reload();
    await page.getByRole('button').filter({hasText:label}).first().waitFor();
    await page.getByRole('button').filter({hasText:label}).first().click();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('video')).some(v=>v.controls&&v.readyState>=1),{},{timeout:10000});
    if(process.env.ARTAE_EXPECT_EVENTS==='yes')assert.ok(await page.getByRole('button',{name:'Review footage',exact:true}).count(),'Event must remain after reload');
    console.log('PERSISTENCE_OK');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
