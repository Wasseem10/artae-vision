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

test('published reset diagnostics preserve full coverage, provenance and the five regression windows', () => {
  const crypto = require('node:crypto');
  const report = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-association-diagnostics-v1.json')));
  const paired = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-association-v1.json')));
  assert.equal(report.promoted, false); assert.equal(report.newInference, false);
  assert.equal(report.sourceReportSha256, paired.fullReportSha256);
  assert.equal(report.clips, 33); assert.equal(report.sampledFrames, 3356);
  assert.deepEqual(report.rows.map(c => c.id), paired.rows.map(c => c.id));
  assert.ok(report.rows.every(c => c.replayMatchesEveryFrame));
  for (const [key, file] of [['instrumentationSha256', 'motion-association.cjs'],
    ['diagnosticScriptSha256', 'diagnose-motion-association.cjs']]) {
    assert.equal(report[key], crypto.createHash('sha256').update(fs.readFileSync(
      path.join(root, 'scripts/experiments', file))).digest('hex'));
  }
  const drops = report.rows.flatMap(c => c.droppedHistories);
  assert.equal(drops.filter(h => h.reason === 'ambiguous').length, 219);
  assert.equal(drops.filter(h => h.reason === 'expired').length, 13);
  assert.equal(drops.filter(h => ['upright', 'descending'].includes(h.status)).length, 48);
  const regressions = report.rows.filter(c => c.firstBaselineAlertSeconds !== null);
  assert.equal(regressions.length, 5);
  assert.ok(regressions.every(c => c.threeSecondsBeforeBaselineAlert.some(h =>
    h.reason === 'ambiguous' && ['upright', 'descending'].includes(h.status))));
});
