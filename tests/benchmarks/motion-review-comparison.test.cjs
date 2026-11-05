const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { blankReview } = require('../../scripts/experiments/motion-review-labels.cjs');
const { compareReviews } = require('../../scripts/experiments/compare-motion-reviews.cjs');
const root = path.resolve(__dirname, '../..');
const sha = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
function fixture() {
  const content = { schemaVersion: 1, frames: ['a', 'a', 'b'].map((clipId, index) => ({
    clipId, key: `${clipId}@${index}`, observations: [{ slot: 'primary' }, { slot: 'multi-0' }],
  })) };
  const packet = { ...content, packetId: sha(content) };
  const left = blankReview(packet);
  left.reviewer = 'Synthetic left';
  left.status = 'single-review';
  for (const frame of left.frames) {
    frame.visiblePeople = 2;
    frame.assignments[0].actor = 'person-1';
    frame.assignments[1].actor = 'person-2';
  }
  return { packet, left, right: structuredClone(left) };
}

test('consistent actor renaming and separate clip namespaces do not create conflicts', () => {
  const { packet, left, right } = fixture();
  right.frames.forEach((frame, index) => frame.assignments.forEach((assignment, slot) => {
    assignment.actor = `person-${index === 2 ? 9 - slot : 5 + slot}`;
  }));
  const result = compareReviews(packet, left, right);
  assert.equal(result.totals.identityConflicts, 0);
  assert.equal(result.totals.identityComparisons, 7); // C(4, 2) + C(2, 2), never cross-clip.
  assert.equal(result.totals.categoryDisagreements, 0);
  assert.equal(result.adjudicated, false);
  assert.equal(result.promoted, false);
});

test('identity swaps across frames are detected even with identical counts and categories', () => {
  const { packet, left, right } = fixture();
  right.frames[1].assignments[0].actor = 'person-2';
  right.frames[1].assignments[1].actor = 'person-1';
  const result = compareReviews(packet, left, right);
  assert.equal(result.totals.identityConflicts, 4);
  assert.ok(result.clips[0].identityConflicts.every(row => !row.withinFrame));
  assert.equal(result.totals.countDisagreements, 0);
  assert.equal(result.totals.categoryDisagreements, 0);
});

test('duplicate-vs-distinct assignments identify the precise within-frame observation pair', () => {
  const { packet, left, right } = fixture();
  right.frames[2].assignments[1].actor = 'person-1';
  const result = compareReviews(packet, left, right);
  const conflict = result.clips[1].identityConflicts[0];
  assert.equal(conflict.withinFrame, true);
  assert.equal(conflict.first.frame, 'b@2');
  assert.equal(conflict.first.slot, 'primary');
  assert.equal(conflict.second.slot, 'multi-0');
  assert.equal(conflict.left, 'different-people');
  assert.equal(conflict.right, 'same-person');
});

test('missing counts and matching uncertain labels remain unresolved, not agreements', () => {
  const { packet, left, right } = fixture();
  left.status = right.status = 'draft';
  left.frames[0].visiblePeople = null;
  left.frames[1].assignments[0].actor = right.frames[1].assignments[0].actor = 'uncertain';
  right.frames[2].assignments[0].actor = 'unreviewed';
  const result = compareReviews(packet, left, right);
  assert.equal(result.totals.unreviewedCounts, 1);
  assert.equal(result.totals.unresolvedObservations, 2);
  assert.equal(result.totals.countDisagreements, 0);
  assert.equal(result.totals.identityComparisons, 3);
  assert.equal(result.totals.identityConflicts, 0);
});

test('person/non-person and visible count disagreements are independent review tasks', () => {
  const { packet, left, right } = fixture();
  right.frames[2].assignments[1].actor = 'non-person';
  right.frames[2].notes = 'Synthetic furniture assignment';
  right.frames[2].visiblePeople = 1;
  const result = compareReviews(packet, left, right);
  assert.equal(result.totals.countDisagreements, 1);
  assert.equal(result.totals.categoryDisagreements, 1);
  assert.equal(result.totals.identityComparisons, 6);
});

test('changed packet, incomplete coverage and ambiguous frame identities are rejected', () => {
  for (const mutate of [x => { x.packet.frames[0].clipId = 'changed'; },
    x => { x.right.packetId = 'wrong'; }, x => x.right.frames.pop(),
    x => x.right.frames.reverse(), x => { x.right.frames[0].assignments[0].slot = 'other'; }]) {
    const value = fixture(); mutate(value);
    assert.throws(() => compareReviews(value.packet, value.left, value.right));
  }
  const value = fixture();
  value.packet.frames[1].key = value.packet.frames[0].key;
  const { packetId, ...content } = value.packet;
  value.packet.packetId = sha(content);
  assert.throws(() => compareReviews(value.packet, value.left, value.right), /duplicate frame/);
});

test('published AI draft self-comparison preserves provenance and all four uncertainties', () => {
  const packet = require('../../docs/benchmarks/motion-review-packet-v1.json');
  const review = require('../../docs/benchmarks/motion-review-ai-draft-v1.json');
  const before = JSON.stringify(review);
  const result = compareReviews(packet, review, structuredClone(review));
  assert.equal(result.totals.frames, 21);
  assert.equal(result.totals.observations, 52);
  assert.equal(result.totals.unresolvedObservations, 4);
  assert.equal(result.totals.identityConflicts, 0);
  assert.equal(result.inputs.left.status, 'draft');
  assert.equal(result.inputs.left.declaredHumanAdjudicated, false);
  assert.equal(result.adjudicated, false);
  assert.equal(JSON.stringify(review), before);
});

test('CLI produces JSON without overwriting input or existing output, and fails on invalid input', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'artae-review-comparison-'));
  try {
    const value = fixture();
    const paths = ['packet', 'left', 'right'].map(key => {
      const file = path.join(folder, `${key}.json`);
      fs.writeFileSync(file, JSON.stringify(value[key]));
      return file;
    });
    const output = path.join(folder, 'comparison.json');
    const run = destination => spawnSync(process.execPath,
      [path.join(root, 'scripts/experiments/compare-motion-reviews.cjs'), ...paths, destination], { encoding: 'utf8' });
    assert.equal(run(output).status, 0);
    const original = fs.readFileSync(output, 'utf8');
    assert.match(JSON.parse(original).comparatorSha256, /^[a-f0-9]{64}$/);
    assert.equal(run(output).status, 1);
    assert.equal(fs.readFileSync(output, 'utf8'), original);
    assert.equal(run(paths[1]).status, 1);
    assert.deepEqual(JSON.parse(fs.readFileSync(paths[1])), value.left);
    fs.writeFileSync(paths[2], '{}');
    const invalidOutput = path.join(folder, 'invalid.json');
    assert.equal(run(invalidOutput).status, 1);
    assert.equal(fs.existsSync(invalidOutput), false);
  } finally {
    assert.equal(path.dirname(path.resolve(folder)), path.resolve(os.tmpdir()), 'Cleanup must stay in the temporary directory');
    fs.rmSync(folder, { recursive: true, force: true });
  }
});
