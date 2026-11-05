const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const spec = require('../../scripts/experiments/primary-history-cases-v1.json');
const { expandCases, loadRules, runStress, observeWindow } = require('../../scripts/experiments/primary-history-stress.cjs');

test('rejects sequences with gaps, overlaps, missing identity or nonfinite features', () => {
  for (const mutate of [
    (row) => { row.cases[0].segments[1].from = 8; },
    (row) => { row.cases[0].segments[1].from = 6; },
    (row) => { row.cases[0].segments[0].actor = null; },
    (row) => { row.poses.standing.x = NaN; },
    (row) => { row.cases[1].id = row.cases[0].id; },
    (row) => { row.cases[0].segments[0].through = 10000; },
  ]) { const input = structuredClone(spec); mutate(input); assert.throws(() => expandCases(input)); }
});

test('oracle reset uses actor changes across gaps and preserves same-actor motion', () => {
  class EchoRule {
    count = 0;
    update(primary) {
      this.count++;
      return primary ? [{ source: 'primary', id: 1, status: String(this.count), temporalHit: false, windowHit: false }] : [];
    }
  }
  const report = runStress(spec, EchoRule, {});
  const same = report.results.find((row) => row.id === 'same-person-fall');
  assert.deepEqual(same.baseline, same.oracleResetControl);
  const gap = report.results.find((row) => row.id === 'short-occlusion-different-person');
  assert.deepEqual(gap.actorBoundarySeconds, [1]);
  assert.equal(gap.oracleResetControl.primaryPhaseTransitions.find((row) => row.seconds === 1).phase, '1');
  assert.equal(gap.baseline.primaryPhaseTransitions.find((row) => row.seconds === 1).phase, '11');
});

// Integration tests compile the actual unchanged application rule, not a copy.
// Set this path explicitly on machines where web dependencies are elsewhere.
const dependenciesRoot = process.env.ARTAE_STRESS_DEPENDENCIES_ROOT || path.resolve(__dirname, '../../apps/web');
const rules = loadRules(dependenciesRoot);
const report = runStress(spec, rules.FusedRule, rules.model);

test('records known false alerts from different-person feature history', () => {
  for (const id of ['different-person-already-down', 'short-occlusion-different-person']) {
    const row = report.results.find((item) => item.id === id);
    assert.equal(row.expectedFall, false);
    assert.equal(row.baseline.temporalEvents.length, 1);
    assert.equal(row.oracleResetControl.temporalEvents.length, 0);
  }
});
test('preserves synthetic fall controls including a bystander and rearming', () => {
  const positives = report.results.filter((row) => row.expectedFall);
  assert.equal(positives.length, 3);
  for (const row of positives) {
    assert.equal(row.baseline.temporalEvents.length, 1);
    assert.equal(row.oracleResetControl.temporalEvents.length, 1);
  }
});

function observedFixture() {
  const capture = { schemaVersion: 1, localGitDirty: false, selectionSha256: 'selection',
    sampleIntervalSeconds: 0.1, sourceHashes: { rule: 'same' }, results: [5, 5.1].map((seconds) => ({
      caseId: 'clip', seconds, decodedSeconds: seconds, overlaySha256: `image-${seconds}`,
      primaryFeatures: {}, raw: [], tracks: [{ source: 'primary', id: 1, status: 'upright', temporalHit: false, windowHit: false }],
    })) };
  const annotations = { schemaVersion: 1, reviewStatus: 'provisional-ai-overlay-review',
    captureSha256: 'capture', selectionSha256: 'selection', actors: { a: 'actor A', b: 'actor B' },
    frames: capture.results.map((row) => ({ caseId: row.caseId, seconds: row.seconds,
      overlaySha256: row.overlaySha256, status: 'matched', actor: 'a' })) };
  return { capture, annotations };
}

test('exports observed rule state without converting associations into alert claims', () => {
  const { capture, annotations } = observedFixture();
  const observed = observeWindow(capture, annotations, 'capture', { rule: 'same' });
  assert.deepEqual(observed.summary.phaseCounts, { upright: 2 });
  assert.equal(observed.summary.temporalAlertFrames, 0);
  assert.equal(observed.reviewStatus, 'provisional-ai-overlay-review');
});

test('rejects mismatched source, unknown phase and nonboolean observed alerts', () => {
  for (const mutate of [
    (data) => { data.capture.sourceHashes.rule = 'different'; },
    (data) => { data.capture.results[1].tracks[0].status = 'unknown'; },
    (data) => { data.capture.results[1].tracks[0].temporalHit = 'false'; },
  ]) {
    const data = observedFixture(); mutate(data);
    assert.throws(() => observeWindow(data.capture, data.annotations, 'capture', { rule: 'same' }));
  }
});
test('existing long-gap, horizontal-jump and posture guards remain silent', () => {
  for (const id of ['large-horizontal-change', 'same-person-sits', 'already-down-from-start', 'long-occlusion-different-person']) {
    const row = report.results.find((item) => item.id === id);
    assert.equal(row.baseline.temporalEvents.length, 0);
    assert.equal(row.oracleResetControl.temporalEvents.length, 0);
  }
});
