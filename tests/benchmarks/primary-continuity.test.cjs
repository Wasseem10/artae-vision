const test = require('node:test');
const assert = require('node:assert/strict');
const { score } = require('../../scripts/score-primary-continuity.cjs');
const { validateSelection } = require('../../scripts/pose-audit-selection.cjs');

function fixture(actors = ['dark', 'blue']) {
  const capture = { schemaVersion: 1, localGitDirty: false, selectionSha256: 'selection',
    sampleIntervalSeconds: 0.1, results: actors.map((actor, index) => ({
      caseId: 'clip', seconds: 5 + index / 10, decodedSeconds: 5 + index / 10,
      overlaySha256: `image-${index}`, primaryFeatures: actor === 'unobserved' ? null : {},
      tracks: actor === 'unobserved' ? [] : [{ source: 'primary', id: 1 }], raw: [], countsMatchArchive: true,
    })) };
  const annotations = { schemaVersion: 1, captureSha256: 'capture', selectionSha256: 'selection',
    reviewStatus: 'provisional-ai-overlay-review', actors: { dark: 'dark clothes', blue: 'blue clothes' },
    frames: capture.results.map((row, index) => ({ caseId: row.caseId, seconds: row.seconds,
      overlaySha256: row.overlaySha256,
      status: ['ambiguous', 'unobserved'].includes(actors[index]) ? actors[index] : 'matched',
      actor: ['ambiguous', 'unobserved'].includes(actors[index]) ? null : actors[index] })) };
  return { capture, annotations };
}
const run = ({ capture, annotations }) => score(capture, annotations, 'capture');

test('exposes a same-slot person change while keeping provisional scope', () => {
  const report = run(fixture());
  assert.equal(report.summary.sameIdDifferentPersonPairs, 1);
  assert.equal(report.summary.comparablePairs, 1);
  assert.equal(report.reviewStatus, 'provisional-ai-overlay-review');
});
test('uncertainty and missing observations never bridge an inferred switch', () => {
  for (const status of ['ambiguous', 'unobserved']) {
    const report = run(fixture(['dark', status, 'blue']));
    assert.equal(report.summary.comparablePairs, 0);
    assert.equal(report.summary.sameIdDifferentPersonPairs, 0);
  }
});
test('a new slot ID is distinguished from a reused ID', () => {
  const data = fixture(); data.capture.results[1].tracks[0].id = 2;
  assert.equal(run(data).summary.sameIdDifferentPersonPairs, 0);
});
test('rejects annotation provenance and overlay mismatches', () => {
  for (const mutate of [
    (data) => { data.annotations.captureSha256 = 'other'; },
    (data) => { data.annotations.selectionSha256 = 'other'; },
    (data) => { data.annotations.frames[1].overlaySha256 = 'other'; },
    (data) => { data.annotations.frames.pop(); },
  ]) { const data = fixture(); mutate(data); assert.throws(() => run(data)); }
});
test('rejects nonadjacent, unordered, stale or mixed-clip observations', () => {
  for (const mutate of [
    (row) => { row.seconds = 5.2; row.decodedSeconds = 5.2; },
    (row) => { row.seconds = 5; row.decodedSeconds = 5; },
    (row) => { row.decodedSeconds = 4.9; },
    (row) => { row.caseId = 'other'; },
  ]) { const data = fixture(); mutate(data.capture.results[1]); assert.throws(() => run(data)); }
});
test('rejects unsupported identity claims and inconsistent observed tracks', () => {
  for (const mutate of [
    (data) => { data.annotations.frames[1].actor = 'unknown'; },
    (data) => { data.annotations.frames[1].status = 'unobserved'; },
    (data) => { data.capture.results[1].tracks = []; },
    (data) => { data.capture.localGitDirty = true; },
    (data) => { data.annotations.reviewStatus = 'human-adjudicated'; },
  ]) { const data = fixture(); mutate(data); assert.throws(() => run(data)); }
});
test('validates selection before expensive inference', () => {
  const manifest = { cases: [{ id: 'clip' }] };
  const frames = [{ caseId: 'clip', seconds: 5 }, { caseId: 'clip', seconds: 5.1 }];
  validateSelection({ frames }, manifest);
  for (const invalid of [[], [...frames, frames[0]], [{ caseId: 'other', seconds: 5 }],
    [{ caseId: 'clip', seconds: -1 }], [{ caseId: 'clip', seconds: NaN }],
    [{ caseId: 'clip', seconds: 5.05 }]]) {
    assert.throws(() => validateSelection({ frames: invalid }, manifest));
  }
});
