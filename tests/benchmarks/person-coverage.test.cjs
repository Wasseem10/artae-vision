const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { summarizeCoverage } = require('../../scripts/experiments/summarize-person-coverage.cjs');
const { blankReview } = require('../../scripts/experiments/motion-review-labels.cjs');
const sha = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
function fixture(actors = ['person-1', 'person-1', 'person-1'], visiblePeople = 2) {
  const content = { schemaVersion: 1, frames: [{ key: 'clip@1', clipId: 'clip',
    observations: actors.map((_, i) => ({ slot: i ? `multi-${i - 1}` : 'primary' })) }] };
  const packet = { ...content, packetId: sha(content) };
  const review = blankReview(packet);
  review.frames[0].visiblePeople = visiblePeople;
  review.frames[0].assignments.forEach((a, i) => { a.actor = actors[i]; });
  return { packet, review };
}
const frame = ({ packet, review }) => summarizeCoverage(packet, review).frames[0];

test('duplicate observations cannot hide an unrepresented actor; sources remain separate', () => {
  const row = frame(fixture());
  assert.equal(row.streams.primary.extraAssignmentsToSamePerson, 0);
  assert.equal(row.streams.multi.extraAssignmentsToSamePerson, 1);
  assert.equal(row.streams.combined.extraAssignmentsToSamePerson, 2);
  for (const stream of Object.values(row.streams)) {
    assert.equal(stream.assignedPeople, 1);
    assert.deepEqual(stream.unrepresentedPeople, { minimum: 1, maximum: 1 });
  }
});

test('uncertain and unreviewed slots widen conditional bounds instead of becoming misses or people', () => {
  const row = frame(fixture(['person-1', 'uncertain', 'unreviewed'], 4));
  assert.deepEqual(row.streams.combined.unrepresentedPeople, { minimum: 1, maximum: 3 });
  assert.deepEqual(row.streams.multi.unrepresentedPeople, { minimum: 2, maximum: 4 });
  assert.equal(row.streams.combined.unresolvedObservations, 2);
  assert.equal(row.streams.combined.nonPersonObservations, 0);
});

test('unknown count stays null and zero-person/empty frames stay explicit', () => {
  const unknown = fixture(['person-1', 'uncertain'], null);
  const report = summarizeCoverage(unknown.packet, unknown.review);
  assert.equal(report.totals.unreviewedCountFrames, 1);
  for (const stream of Object.values(report.frames[0].streams)) assert.equal(stream.unrepresentedPeople, null);
  for (const stream of Object.values(frame(fixture([], 2)).streams)) {
    assert.equal(stream.observations, 0);
    assert.deepEqual(stream.unrepresentedPeople, { minimum: 2, maximum: 2 });
  }
  const zero = frame(fixture(['non-person', 'uncertain'], 0)).streams.combined;
  assert.equal(zero.nonPersonObservations, 1);
  assert.equal(zero.unresolvedObservations, 1);
  assert.deepEqual(zero.unrepresentedPeople, { minimum: 0, maximum: 0 });
});

test('distinct multi observations can cover actors missed by primary, without cross-frame identity totals', () => {
  const { packet, review } = fixture(['person-1', 'person-1', 'person-2']);
  const result = summarizeCoverage(packet, review);
  assert.deepEqual(result.frames[0].streams.primary.unrepresentedPeople, { minimum: 1, maximum: 1 });
  assert.deepEqual(result.frames[0].streams.multi.unrepresentedPeople, { minimum: 0, maximum: 0 });
  assert.equal('people' in result.totals, false);
});

test('packet tampering, missing assignments and unknown streams fail closed', () => {
  for (const mutate of [v => { v.packet.frames[0].key = 'tampered'; },
    v => v.review.frames[0].assignments.pop(),
    v => { v.review.frames[0].visiblePeople = 0; },
    v => {
      v.packet.frames[0].observations[1].slot = v.review.frames[0].assignments[1].slot = 'other';
      const { packetId, ...content } = v.packet;
      v.packet.packetId = v.review.packetId = sha(content);
    }]) {
    const value = fixture(); mutate(value);
    assert.throws(() => summarizeCoverage(value.packet, value.review));
  }
});

test('published provisional draft retains all four uncertainties and no adjudication claim', () => {
  const packet = require('../../docs/benchmarks/motion-review-packet-v1.json');
  const review = require('../../docs/benchmarks/motion-review-ai-draft-v1.json');
  const before = JSON.stringify(review);
  const report = summarizeCoverage(packet, review);
  assert.deepEqual(report.totals, { clips: 5, frames: 21, observations: 52, unreviewedCountFrames: 0 });
  assert.equal(report.frames.reduce((n, f) => n + f.streams.combined.unresolvedObservations, 0), 4);
  assert.equal(report.input.declaredHumanAdjudicated, false);
  assert.equal(report.adjudicated, false);
  assert.equal(report.promoted, false);
  assert.equal(report.newInference, false);
  assert.equal(JSON.stringify(review), before);
  assert.match(report.warning, /not recall/);
});

test('CLI records code provenance, refuses overwrites and leaves no report for invalid input', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'artae-person-coverage-'));
  try {
    const value = fixture();
    const paths = ['packet', 'review'].map(key => {
      const file = path.join(folder, `${key}.json`);
      fs.writeFileSync(file, JSON.stringify(value[key])); return file;
    });
    const output = path.join(folder, 'coverage.json');
    const run = destination => spawnSync(process.execPath,
      [path.resolve(__dirname, '../../scripts/experiments/summarize-person-coverage.cjs'), ...paths, destination], { encoding: 'utf8' });
    assert.equal(run(output).status, 0);
    const original = fs.readFileSync(output, 'utf8');
    assert.equal(Object.keys(JSON.parse(original).sourceSha256).length, 3);
    for (const hash of Object.values(JSON.parse(original).sourceSha256)) assert.match(hash, /^[a-f0-9]{64}$/);
    assert.equal(run(output).status, 1);
    assert.equal(fs.readFileSync(output, 'utf8'), original);
    assert.equal(run(paths[1]).status, 1);
    assert.deepEqual(JSON.parse(fs.readFileSync(paths[1])), value.review);
    fs.writeFileSync(paths[1], '{}');
    assert.equal(run(path.join(folder, 'invalid.json')).status, 1);
    assert.equal(fs.existsSync(path.join(folder, 'invalid.json')), false);
  } finally {
    assert.equal(path.dirname(path.resolve(folder)), path.resolve(os.tmpdir()));
    fs.rmSync(folder, { recursive: true, force: true });
  }
});
