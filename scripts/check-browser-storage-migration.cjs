// Isolated local-browser regression: preserve real v1 footage through the v2 upgrade.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await browser.newPage();
    const origin = new URL(process.env.ARTAE_TEST_URL || 'http://127.0.0.1:4174/demo').origin;
    await page.goto(`${origin}/icon.svg`);
    await page.evaluate(async () => {
      const blob = await (await fetch('/vision/samples/person.mp4')).blob();
      const db = await new Promise((resolve,reject) => {
        const open=indexedDB.open('artae-browser-sessions',1);
        open.onupgradeneeded=()=>open.result.createObjectStore('sessions',{keyPath:'key'});
        open.onsuccess=()=>resolve(open.result);open.onerror=()=>reject(open.error);
      });
      await new Promise((resolve,reject)=>{
        const tx=db.transaction('sessions','readwrite');
        tx.objectStore('sessions').put({key:'guest/legacy',id:'legacy',scope:'guest',name:'Legacy recording',job:'presence',createdAt:'2026-09-09T12:00:00Z',
          events:[{id:'legacy-event',at:2,title:'Person detected',visibility:.9}],
          clips:[{id:'legacy-clip',start:0,duration:10,width:640,height:360,blob}]});
        tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
      });db.close();
    });
    await page.goto(`${origin}/demo`);
    await page.getByRole('button').filter({hasText:'Legacy recording'}).click();
    await page.getByRole('button',{name:'Review footage',exact:true}).click();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('video')).some(v=>v.controls&&v.readyState>=1));
    await page.getByRole('button',{name:'Acknowledge',exact:true}).click();
    await page.getByText('Review saved on this device',{exact:true}).waitFor();
    const state=await page.evaluate(async()=>{
      const db=await new Promise(resolve=>{const open=indexedDB.open('artae-browser-sessions',2);open.onsuccess=()=>resolve(open.result);});
      const get=(store,key)=>new Promise(resolve=>{const read=db.transaction(store).objectStore(store).get(key);read.onsuccess=()=>resolve(read.result);});
      const [metadata,clip]=await Promise.all([get('sessions','guest/legacy'),get('clips','guest/legacy/legacy-clip')]);db.close();
      return {inlineBlob:!!metadata.clips[0].blob,separateBytes:clip.blob.size,review:metadata.events[0].review.status};
    });
    assert.equal(state.inlineBlob,false);assert.ok(state.separateBytes>1000);assert.equal(state.review,'acknowledged');
    await page.reload();
    await page.getByRole('button').filter({hasText:'Legacy recording'}).click();
    await page.getByRole('button',{name:'Review footage',exact:true}).click();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('video')).some(v=>v.controls&&v.readyState>=1));
    console.log('STORAGE_MIGRATION_AND_REPLAY_OK',state);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
