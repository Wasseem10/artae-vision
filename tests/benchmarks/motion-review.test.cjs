const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { selectFrames } = require('../../scripts/experiments/build-motion-review.cjs');
const { blankReview, validateReview } = require('../../scripts/experiments/motion-review-labels.cjs');
const packet = { packetId: 'frozen-packet', frames: [{ key: 'clip@1',
  observations: [{ slot: 'primary' }, { slot: 'multi-0' }] },
{ key: 'clip@1.1', observations: [] }] };
function complete() {
  const review = blankReview(packet); review.reviewer = 'Test reviewer';
  review.frames[0].visiblePeople = 1;
  review.frames[0].assignments.forEach(a => { a.actor = 'person-1'; });
  review.frames[1].visiblePeople = 0;
  return review;
}

test('draft defaults do not invent zero people, actor IDs, or completed labels', () => {
  const draft = blankReview(packet);
  assert.equal(draft.status, 'draft'); assert.equal(draft.frames[0].visiblePeople, null);
  assert.ok(draft.frames[0].assignments.every(a => a.actor === 'unreviewed'));
  validateReview(draft, packet);
  assert.throws(() => validateReview(draft, packet, true), /reviewer/);
  draft.reviewer = 'Reviewer';
  assert.throws(() => validateReview(draft, packet, true), /Unreviewed/);
});

test('single review permits duplicate observations of one actor and explicit zero-person frames', () => {
  const review = complete(); review.status = 'single-review';
  validateReview(review, packet);
  review.frames[1].visiblePeople = null;
  assert.throws(() => validateReview(review, packet), /counts remain/);
});

test('imports reject wrong packets, missing/reordered frames and changed observation slots', () => {
  for (const mutate of [r => { r.packetId = 'other'; }, r => r.frames.pop(),
    r => r.frames.reverse(), r => r.frames[0].assignments.pop(),
    r => { r.frames[0].assignments[0].slot = 'multi-3'; }]) {
    const review = complete(); mutate(review); assert.throws(() => validateReview(review, packet));
  }
});

test('uncertainty and non-person assignments require notes, not a guessed person', () => {
  for (const actor of ['uncertain', 'non-person']) {
    const review = complete(); review.frames[0].assignments[0].actor = actor;
    assert.throws(() => validateReview(review, packet, true), /Explain/);
    review.frames[0].notes = 'Marker overlaps an occluded torso; center alone is insufficient.';
    validateReview(review, packet, true);
  }
});

test('malformed labels and impossible actor counts fail even draft validation', () => {
  for (const value of [-1, 1.5, '1', NaN, Infinity]) {
    const review = complete(); review.frames[0].visiblePeople = value;
    assert.throws(() => validateReview(review, packet), /count/);
  }
  for (const actor of ['person-0', 'chair', '<script>', null]) {
    const review = complete(); review.frames[0].assignments[0].actor = actor;
    assert.throws(() => validateReview(review, packet), /actor label/);
  }
  const review = complete(); review.frames[0].assignments[1].actor = 'person-2';
  assert.throws(() => validateReview(review, packet), /More assigned actors/);
});

test('window selection includes raw suppressed slots and adjacent samples, deduplicating history drops', () => {
  const feature = { x: .5, y: .5, verticality: 1, aspect: .4, visibility: .9 };
  const clip = { id: 'clip', videoSha256: 'video', baseline: { temporalEvents: [{}] },
    candidate: { temporalEvents: [] }, frames: [.9, 1, 1.1].map(t => ({ requestedSeconds: t,
      decodedSeconds: t, primary: feature, multi: [feature, feature] })) };
  const report = { revision: 'revision', results: [clip] };
  const drop = { seconds: 1, reason: 'ambiguous', status: 'descending' };
  const diagnostics = { captureRevision: 'revision', newInference: false,
    rows: [{ id: 'clip', threeSecondsBeforeBaselineAlert: [drop, { ...drop, id: 2 }] }] };
  const frames = selectFrames(report, diagnostics);
  assert.equal(frames.length, 3); assert.equal(frames[1].drops.length, 2);
  assert.deepEqual(frames[1].observations.map(o => o.slot), ['primary', 'multi-0', 'multi-1']);
  clip.frames.pop(); assert.throws(() => selectFrames(report, diagnostics), /Missing surrounding sample/);
});

test('published packet pins extraction, observations, and review code without completed labels', () => {
  const root = path.resolve(__dirname, '../..');
  const published = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-review-packet-v1.json')));
  const sha = value => crypto.createHash('sha256').update(value).digest('hex');
  const { packetId, ...content } = published;
  assert.equal(packetId, sha(JSON.stringify(content)));
  assert.equal(published.frames.length, 21);
  assert.equal(new Set(published.frames.map(f => f.key)).size, 21);
  assert.equal(new Set(published.frames.map(f => f.clipId)).size, 5);
  assert.equal(published.frames.reduce((n, f) => n + f.observations.length, 0), 52);
  assert.ok(published.frames.every(f => f.imagePresentationSeconds === f.decodedSeconds));
  for (const [key, file] of [['builderSha256', 'scripts/experiments/build-motion-review.cjs'],
    ['validatorSha256', 'scripts/experiments/motion-review-labels.cjs'],
    ['templateSha256', 'scripts/experiments/motion-review.html'],
    ['diagnosticsSha256', 'docs/benchmarks/motion-association-diagnostics-v1.json']]) {
    assert.equal(published[key], sha(fs.readFileSync(path.join(root, file))), `Changed ${file}`);
  }
  const draft = blankReview(published);
  assert.ok(draft.frames.every(f => f.visiblePeople === null));
  validateReview(draft, published);
});
