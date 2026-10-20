const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { exactSeconds, classifyClock, planSample } = require('../../scripts/posture-clock.cjs');
const root = path.resolve(__dirname, '../..');
const read = (name) => fs.readFileSync(path.join(root, name));
const sha = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');

test('published clock evidence preserves all seven source identities and unverified labels', () => {
  const report = JSON.parse(read('docs/benchmarks/posture-browser-clock-v1.json'));
  const mediaBytes = read('docs/benchmarks/posture-media-v1.json');
  const media = JSON.parse(mediaBytes);
  assert.equal(report.source_media_evidence_sha256, sha(mediaBytes));
  assert.equal(report.source_lock_sha256, sha(read('docs/benchmarks/posture-source-v1.lock.json')));
  assert.equal(report.script_sha256, sha(read('scripts/check-posture-video-clock.cjs')));
  assert.equal(report.contract_sha256, sha(read('scripts/posture-clock.cjs')));
  assert.equal(report.working_tree_dirty, false);
  assert.equal(report.benchmark_eligible, false);
  assert.equal(report.label_clock_verified, false);
  assert.equal(report.sampler_revision, 'f670e4bf1a0202514ab6ad3a5d5d07fbb136806b');
  assert.equal(report.code_revision, '481c999b901959b4f8e237f89caf0aa140ed4bc7');
  assert.equal(report.tolerance_seconds, 0.000002);
  assert.equal(report.blocked_requests, 0);
  assert.deepEqual(report.browser_server_errors, []);
  assert.equal(report.clips.length, 7);
  assert.deepEqual(report.clips.map(c => c.path).sort(), media.clips.map(c => c.path).sort());
  for (const clip of report.clips) {
    const source = media.clips.find(c => c.path === clip.path);
    assert.equal(clip.media_sha256, source.sha256);
    const first = exactSeconds(source.decode.first_pts_seconds_exact);
    const last = exactSeconds(source.decode.last_pts_seconds_exact);
    assert.deepEqual(clip.firstClock, classifyClock(clip.observed.first.mediaTime, first, first));
    assert.deepEqual(clip.lastClock, classifyClock(clip.observed.last.mediaTime, last, first));
    assert.equal(clip.firstClock.classification, 'raw-presentation');
    assert.equal(clip.lastClock.classification, 'raw-presentation');
    assert.equal(clip.observed.first.presentedFrames, 1);
    assert.equal(clip.observed.zeroTickSampler.accepted, false);
    assert.match(clip.observed.zeroTickSampler.error, /Unexpected presented video frame/);
    const planned = clip.observed.sourcePlannedSampler;
    assert.deepEqual(planned.plan, planSample(0, first, exactSeconds(source.decode.last_frame_end_seconds_exact)));
    assert.equal(planned.accepted, true);
    assert.equal(planned.value.requestedSeconds, first);
    assert.equal(planned.value.presentedFrames, 1);
    assert.ok(Math.abs(planned.value.decodedSeconds - first) <= report.tolerance_seconds);
    assert.ok(Math.abs(clip.observed.duration - exactSeconds(source.decode.container_duration_seconds_exact)) <= report.tolerance_seconds);
  }
});
