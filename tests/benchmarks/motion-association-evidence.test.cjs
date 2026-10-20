const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
test('published paired comparison preserves every regression and never claims promotion', () => {
  const report = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-association-v1.json')));
  assert.equal(report.promoted, false);
  assert.equal(report.rows.length, 33);
  assert.equal(new Set(report.rows.map(c => c.id)).size, 33);
  assert.equal(report.rows.filter(c => c.baseline.alerted && !c.candidate.alerted).length, 5);
  const mpfdd = report.groups['previously examined MPFDD development'];
  assert.equal(mpfdd.falls, 22); assert.equal(mpfdd.activities, 6);
  assert.deepEqual(mpfdd.baseline, { fallClipsAlerted: 2, activityClipsAlerted: 0 });
  assert.deepEqual(mpfdd.candidate, { fallClipsAlerted: 0, activityClipsAlerted: 0 });
  assert.ok(mpfdd.activityVideoSeconds > 63 && mpfdd.activityVideoSeconds < 64);
});
