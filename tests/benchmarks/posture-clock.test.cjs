const { test } = require('node:test');
const assert = require('node:assert/strict');
const { exactSeconds, classifyClock, planSample, resolveRange } = require('../../scripts/posture-clock.cjs');

test('raw PTS and first-frame normalization are distinct for an offset source', () => {
  assert.equal(classifyClock(0.0568, 0.0568, 0.0568).classification, 'raw-presentation');
  assert.equal(classifyClock(0, 0.0568, 0.0568).classification, 'first-frame-zero');
  assert.equal(classifyClock(12.0568, 12.0568, 0.0568).classification, 'raw-presentation');
  assert.equal(classifyClock(12, 12.0568, 0.0568).classification, 'first-frame-zero');
});
test('a zero-origin source is ambiguous, not proof of a normalization rule', () => {
  assert.equal(classifyClock(12, 12, 0).classification, 'ambiguous');
});
test('unmatched frames are never assigned the nearest clock hypothesis', () => {
  assert.equal(classifyClock(12.02, 12.0568, 0.0568).classification, 'neither');
});
test('clock rounding tolerates two microseconds but not a different frame', () => {
  assert.equal(classifyClock(12.056801, 12.0568, 0.0568).classification, 'raw-presentation');
  assert.equal(classifyClock(12.05681, 12.0568, 0.0568).classification, 'neither');
});
test('invalid or reversed clock observations fail', () => {
  for (const values of [[NaN, 1, 0], [-1, 1, 0], [0, 1, 2], [0, 1, 0, 0]]) {
    assert.throws(() => classifyClock(...values));
  }
});
test('exact rational source times reject malformed or nonfinite data', () => {
  assert.equal(exactSeconds('71/1250'), 0.0568);
  for (const value of ['1/0', '1.0/2', 'NaN', '1/-2', null]) assert.throws(() => exactSeconds(value));
});
test('full, open-ended, bounded and suffix byte requests are served accurately', () => {
  assert.deepEqual(resolveRange(undefined, 100), { status: 200, start: 0, end: 99 });
  assert.deepEqual(resolveRange('bytes=20-', 100), { status: 206, start: 20, end: 99 });
  assert.deepEqual(resolveRange('bytes=20-40', 100), { status: 206, start: 20, end: 40 });
  assert.deepEqual(resolveRange('bytes=-20', 100), { status: 206, start: 80, end: 99 });
  assert.deepEqual(resolveRange('bytes=20-200', 100), { status: 206, start: 20, end: 99 });
  assert.deepEqual(resolveRange('bytes=-200', 100), { status: 206, start: 0, end: 99 });
});
test('invalid, empty, multipart and unsafe ranges are rejected', () => {
  for (const range of ['bytes=100-', 'bytes=40-20', 'bytes=-0', 'bytes=-', 'bytes=1-2,4-5', 'items=0-1', 'bytes=9007199254740992-']) {
    assert.equal(resolveRange(range, 100), null, range);
  }
});
test('a source-aware startup preserves the logical zero tick and requests verified first PTS', () => {
  assert.deepEqual(planSample(0, 0.0568, 10), { scheduledSeconds: 0, requestedSeconds: 0.0568, verifiedFirstPTS: 0.0568 });
  assert.equal(planSample(0.05, 0.0568, 10).requestedSeconds, 0.0568);
  assert.equal(planSample(0.1, 0.0568, 10).requestedSeconds, 0.1);
  assert.equal(planSample(0, 0, 10).requestedSeconds, 0);
});
test('planning rejects missing, negative, and out-of-source bounds', () => {
  for (const args of [[0, NaN, 10], [-1, 0, 10], [0, -1, 10], [0, 10, 10], [10, 0, 10]]) assert.throws(() => planSample(...args));
});
