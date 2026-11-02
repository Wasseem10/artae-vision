const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { summarize } = require('../../scripts/experiments/capture-motion-review-poses.cjs');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
function fixture() {
  const features = { x:.5,y:.5,verticality:1,aspect:.3,visibility:.9 };
  const observations = [{ slot:'primary',features }];
  const content = { frames:[{key:'clip@1',clipId:'clip',requestedSeconds:1,decodedSeconds:1,videoSha256:'v',observations}] };
  const packet = { ...content, packetId:sha(JSON.stringify(content)) };
  const pose = Array.from({length:33},()=>({x:.5,y:.5,z:0,visibility:.9}));
  const report = {schemaVersion:1,packetId:packet.packetId,newInference:true,promoted:false,
    sources:[{id:'clip',videoSha256:'v'}],warmupSamples:11,
    frames:[{key:'clip@1',requestedSeconds:1,decodedSeconds:1,width:640,height:480,
      imageSha256:'a'.repeat(64),primaryLandmarks:pose,poses:[],observations:structuredClone(observations)}]};
  return {packet,report};
}
test('summary distinguishes exact compact features from new skeleton identity evidence',()=>{
  const {packet,report}=fixture(), result=summarize(report,packet);
  assert.equal(result.exactFeatureFrames,1);assert.equal(result.newInference,true);assert.equal(result.promoted,false);
  assert.equal(result.rows[0].primaryPosePresent,true);
  report.frames[0].observations[0].features.x=.51;
  assert.equal(summarize(report,packet).exactFeatureFrames,0);
  report.frames[0].observations=[];
  assert.equal(summarize(report,packet).rows[0].sameSlots,false);
});
test('rejects changed provenance, missing capture, warmup and decoded-time mismatch',()=>{
  for(const mutate of [r=>r.packetId='other',r=>r.newInference=false,r=>r.promoted=true,
    r=>r.frames.pop(),r=>r.frames[0].key='other',r=>r.frames[0].decodedSeconds=1.1,
    r=>r.sources=[],r=>r.sources[0].videoSha256='other',r=>r.warmupSamples=1]){
    const {packet,report}=fixture();mutate(report);assert.throws(()=>summarize(report,packet));
  }
  const {packet,report}=fixture();packet.frames[0].requestedSeconds=2;
  assert.throws(()=>summarize(report,packet),/integrity/);
});
test('rejects truncated skeletons, nonfinite coordinates and invalid raw slot mappings',()=>{
  for(const mutate of [r=>r.frames[0].primaryLandmarks.pop(),
    r=>r.frames[0].primaryLandmarks[0].x=NaN,
    r=>r.frames[0].observations[0].features.x=Infinity,
    r=>r.frames[0].observations.push({slot:'multi-0',rawIndex:0,features:r.frames[0].observations[0].features})]){
    const {packet,report}=fixture();mutate(report);assert.throws(()=>summarize(report,packet));
  }
});
test('published fresh capture preserves all review frames and explicit inference provenance',()=>{
  const root=path.resolve(__dirname,'../..');
  const packet=require('../../docs/benchmarks/motion-review-packet-v1.json');
  const report=require('../../docs/benchmarks/motion-pose-context-v1.json');
  assert.equal(report.newInference,true);assert.equal(report.promoted,false);
  assert.equal(report.packetId,packet.packetId);assert.equal(report.frameCount,21);assert.equal(report.warmupSamples,306);
  assert.equal(report.exactFeatureFrames,report.rows.filter(r=>r.exactFeatures).length);
  assert.deepEqual(report.rows.map(r=>r.key),packet.frames.map(r=>r.key));
  assert.equal(report.fingerprint.harness,sha(fs.readFileSync(path.join(root,'scripts/experiments/capture-motion-review-poses.cjs'))));
  assert.equal(report.fingerprint.template,sha(fs.readFileSync(path.join(root,'scripts/experiments/motion-pose-context.html'))));
  assert.match(report.captureSha256,/^[a-f0-9]{64}$/);
});
