const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { MotionAssociation } = require('../../scripts/experiments/motion-association.cjs');
const { diagnose, verifyArchive } = require('../../scripts/experiments/diagnose-motion-association.cjs');
const pose = x => ({ x, y: .3, verticality: .9, aspect: .5, visibility: .95 });
const factory = () => ({ update: () => false, status: 'descending' });
const tracker = () => new MotionAssociation(factory, factory);

test('ambiguous observations report each discarded history once with its prior state', () => {
  const t = tracker();
  t.update(null, [pose(.4), pose(.6)], 0);
  t.update(null, [pose(.5), pose(.51)], .1);
  assert.equal(t.lastDiagnostics.ambiguousObservations.length, 2);
  assert.deepEqual(t.lastDiagnostics.droppedHistories, [1, 2].map(id =>
    ({ id, reason: 'ambiguous', status: 'descending', lastObservedSeconds: 0 })));
  const snapshot = t.lastDiagnostics;
  t.update(pose(.5), [], .2);
  assert.deepEqual(t.lastDiagnostics.droppedHistories, []);
  assert.equal(snapshot.droppedHistories.length, 2);
});

test('missing observations retain histories without claiming a reset', () => {
  const t = tracker(); t.update(pose(.2), [], 0);
  t.update(null, [], .1);
  assert.deepEqual(t.lastDiagnostics.retainedMissingIds, [1]);
  assert.deepEqual(t.lastDiagnostics.droppedHistories, []);
  t.update(pose(.2), [], 1);
  assert.equal(t.lastDiagnostics.droppedHistories[0].reason, 'expired');
  assert.deepEqual(t.lastDiagnostics.createdIds, [2]);
});

test('clock resets differ from invalid clock inputs, which leave histories intact', () => {
  const t = tracker(); t.update(pose(.2), [], 1);
  t.update(pose(.2), [], NaN);
  assert.equal(t.lastDiagnostics.invalidClock, true);
  assert.deepEqual(t.lastDiagnostics.droppedHistories, []);
  t.update(pose(.2), [], .5);
  assert.equal(t.lastDiagnostics.droppedHistories[0].reason, 'clock-reset');
});

test('suppression and capacity drops are separate from ambiguity', () => {
  const t = tracker(); t.update(pose(.1), [pose(.1), pose(NaN)], 0);
  assert.equal(t.lastDiagnostics.fusionSuppressed, 1);
  assert.equal(t.lastDiagnostics.invalidObservations, 1);
  t.update(null, [.6, .7, .8, .9, 1].map(pose), .1);
  assert.equal(t.lastDiagnostics.capacitySuppressed, 1);
  assert.deepEqual(t.lastDiagnostics.droppedHistories.map(h => h.reason), ['capacity']);
  assert.equal(t.lastDiagnostics.ambiguousObservations.length, 0);
});

test('archive verification refuses altered bytes and mismatched provenance', () => {
  const bytes = Buffer.from(JSON.stringify({ revision: 'capture' }));
  const expected = { fullReportSha256: crypto.createHash('sha256').update(bytes).digest('hex'), captureRevision: 'capture' };
  assert.equal(verifyArchive(bytes, expected).revision, 'capture');
  assert.throws(() => verifyArchive(Buffer.concat([bytes, Buffer.from(' ')]), expected), /digest mismatch/);
  assert.throws(() => verifyArchive(bytes, { ...expected, captureRevision: 'other' }), /revision mismatch/);
});

test('diagnosis refuses incomplete traces or any changed candidate output', () => {
  const report = { schemaVersion: 1, dirty: false, results: Array.from({ length: 33 }, (_, i) => ({
    id: `fixture-${i}`, scope: 'test', expectedFall: false, duration: .1,
    baseline: { temporalEvents: [] }, candidate: { temporalEvents: [] },
    frames: [{ requestedSeconds: 0, decodedSeconds: 0, primary: pose(.2), multi: [], baseline: [],
      candidate: [{ features: pose(.2), source: 'primary', index: -1, id: 1,
        temporalHit: false, windowHit: false, status: 'descending' }] }],
  })) };
  assert.equal(diagnose(report, tracker).length, 33);
  const altered = structuredClone(report);
  altered.results[0].frames[0].candidate[0].id = 9;
  assert.throws(() => diagnose(altered, tracker), /replay diverged/);
  const incomplete = structuredClone(report);
  incomplete.results[0].frames = [];
  assert.throws(() => diagnose(incomplete, tracker), /Incomplete/);
});
