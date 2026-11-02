const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');const crypto=require('node:crypto');const {pathToFileURL}=require('node:url');
const [folderArg,depsArg]=process.argv.slice(2);
assert.ok(folderArg&&depsArg,'Pass local-capture-directory dependencies-root');
const {chromium}=require(require.resolve('playwright',{paths:[path.resolve(depsArg)]}));
const folder=path.resolve(folderArg);
const packet=require('../../docs/benchmarks/motion-review-packet-v1.json');
const {summarize}=require('./capture-motion-review-poses.cjs');
async function main(){
 const bytes=fs.readFileSync(path.join(folder,'capture.json')),report=JSON.parse(bytes),summary=JSON.parse(fs.readFileSync(path.join(folder,'summary.json')));
 const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
 assert.equal(summary.captureSha256,sha(bytes));const {captureSha256,...withoutHash}=summary;assert.deepEqual(summarize(report,packet),withoutHash);
 for(const frame of report.frames)assert.equal(sha(fs.readFileSync(path.join(folder,frame.image))),frame.imageSha256);
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));await page.route(/^https?:/,route=>{network.push(route.request().url());return route.abort();});
  await page.goto(pathToFileURL(path.join(folder,'index.html')).href);
  assert.equal(await page.locator('section').count(),21);
  await page.waitForFunction(()=>[...document.images].every(img=>img.complete&&img.naturalWidth>0));
  assert.match(await page.locator('.warning').innerText(),/NEW INFERENCE/);
  for(let i=0;i<report.frames.length;i++){
   const frame=report.frames[i], section=page.locator('section').nth(i),select=section.locator('select');
   assert.equal(await select.locator('option').count(),1+frame.poses.length);
   for(let j=0;j<=frame.poses.length;j++){
    await select.selectOption(String(j));
    const data=JSON.parse(await section.locator('pre').textContent());
    assert.deepEqual(data.landmarks,j===0?frame.primaryLandmarks:frame.poses[j-1]);
   }
   await select.selectOption('0');
  }
  await page.screenshot({path:path.join(folder,'viewer-desktop.png')});
  for(const i of [8,9]){
   const section=page.locator('section').nth(i);
   await section.screenshot({path:path.join(folder,`context-${i}-primary.png`)});
   if(report.frames[i].poses.length>1){await section.locator('select').selectOption('2');await section.screenshot({path:path.join(folder,`context-${i}-multi1.png`)});}
  }
  const select=page.locator('select').first();await select.focus();await select.press('ArrowDown');
  assert.equal(await select.inputValue(),'1');
  await page.setViewportSize({width:390,height:844});await page.locator('h1').scrollIntoViewIfNeeded();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(folder,'viewer-mobile.png')});
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({frames:21,imageHashesVerified:21,allRawSlotsSelectable:true,keyboardSelection:true,mobileOverflow:false,pageErrors:0,externalRequests:0}));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
