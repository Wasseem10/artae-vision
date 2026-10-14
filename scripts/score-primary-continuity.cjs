// Local diagnostic, not MOT identity ground truth or a detector promotion gate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const hash = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');

function score(capture, annotations, captureSha256) {
  assert.equal(capture.schemaVersion, 1, 'Unsupported capture');
  assert.equal(annotations.schemaVersion, 1, 'Unsupported annotations');
  assert.equal(capture.localGitDirty, false, 'Capture must come from clean code');
  assert.equal(annotations.captureSha256, captureSha256, 'Annotation/capture mismatch');
  assert.equal(annotations.selectionSha256, capture.selectionSha256, 'Selection mismatch');
  assert.equal(annotations.reviewStatus, 'provisional-ai-overlay-review', 'Only provisional annotations supported');
  assert.equal(capture.sampleIntervalSeconds, 0.1, 'Expected 0.1 second samples');
  assert.ok(Array.isArray(capture.results) && capture.results.length >= 2, 'Need adjacent samples');
  assert.equal(annotations.frames.length, capture.results.length, 'Incomplete annotations');
  const actors = new Set(Object.keys(annotations.actors));
  assert.ok(actors.size >= 2, 'Need scene-local actor descriptors');
  const observations = [];
  const keys = new Set();
  for (let index = 0; index < capture.results.length; index++) {
    const frame = capture.results[index];
    const label = annotations.frames[index];
    const key = `${frame.caseId}:${frame.seconds}`;
    assert.ok(!keys.has(key), 'Duplicate frame'); keys.add(key);
    assert.ok(Number.isFinite(frame.seconds) && frame.seconds >= 0 && Number.isFinite(frame.decodedSeconds) &&
      Math.abs(frame.decodedSeconds - frame.seconds) <= 0.001, 'Invalid presented time');
    if (index) {
      const previous = capture.results[index - 1];
      assert.equal(frame.caseId, previous.caseId, 'One clip per diagnostic');
      assert.ok(Math.abs(frame.seconds - previous.seconds - 0.1) < 1e-8, 'Nonadjacent or unordered samples');
    }
    assert.equal(label.caseId, frame.caseId, 'Case mismatch');
    assert.equal(label.seconds, frame.seconds, 'Time mismatch');
    assert.equal(label.overlaySha256, frame.overlaySha256, 'Changed overlay');
    const primary = frame.tracks.filter((track) => track.source === 'primary');
    assert.equal(primary.length, frame.primaryFeatures ? 1 : 0, 'Primary track/feature mismatch');
    if (primary.length) assert.ok(Number.isInteger(primary[0].id) && primary[0].id > 0, 'Invalid primary ID');
    assert.ok(['matched', 'ambiguous', 'unobserved'].includes(label.status), 'Unknown match status');
    assert.equal(label.status === 'unobserved', !frame.primaryFeatures, 'Observation status mismatch');
    if (label.status === 'matched') assert.ok(actors.has(label.actor), 'Unknown actor');
    else assert.equal(label.actor, null, 'Uncertain frames must not assign an actor');
    observations.push({ caseId: frame.caseId, videoSha256: frame.videoSha256,
      seconds: frame.seconds, decodedSeconds: frame.decodedSeconds,
      primaryId: primary[0]?.id ?? null, status: label.status, actor: label.actor,
      rawPoses: frame.raw.length, usablePoses: frame.raw.filter((row) => row.features).length,
      fusedIds: frame.tracks.map((track) => track.id), countsMatchArchive: frame.countsMatchArchive,
      overlaySha256: frame.overlaySha256 });
  }
  const transitions = observations.slice(1).map((to, index) => {
    const from = observations[index];
    let outcome = 'unknown';
    if (from.status === 'matched' && to.status === 'matched') {
      outcome = from.actor === to.actor ? 'same-person' : 'different-person';
    }
    return { fromSeconds: from.seconds, toSeconds: to.seconds, outcome,
      samePrimaryId: from.primaryId !== null && from.primaryId === to.primaryId };
  });
  return { schemaVersion: 1, reviewStatus: annotations.reviewStatus,
    scope: 'Selected development window; provisional visual association, no MOT identity score or fall accuracy claim',
    captureSha256, selectionSha256: capture.selectionSha256, captureCodeRevision: capture.codeRevision,
    browserVersion: capture.browserVersion, manifestSha256: capture.manifestSha256,
    referenceReportSha256: capture.referenceReportSha256, sourceHashes: capture.sourceHashes,
    actors: annotations.actors,
    summary: { frames: observations.length, adjacentPairs: transitions.length,
      matchedFrames: observations.filter((row) => row.status === 'matched').length,
      ambiguousFrames: observations.filter((row) => row.status === 'ambiguous').length,
      unobservedFrames: observations.filter((row) => row.status === 'unobserved').length,
      comparablePairs: transitions.filter((row) => row.outcome !== 'unknown').length,
      sameIdDifferentPersonPairs: transitions.filter((row) => row.outcome === 'different-person' && row.samePrimaryId).length,
      countsMatchingArchive: observations.filter((row) => row.countsMatchArchive).length },
    observations, transitions };
}

if (require.main === module) {
  try {
    assert.equal(process.argv.length, 5, 'Usage: node score-primary-continuity.cjs capture.json annotations.json output.json');
    const bytes = fs.readFileSync(process.argv[2]);
    const annotationBytes = fs.readFileSync(process.argv[3]);
    const report = score(JSON.parse(bytes), JSON.parse(annotationBytes), hash(bytes));
    report.annotationsSha256 = hash(annotationBytes);
    fs.writeFileSync(process.argv[4], JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report.summary));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { score };
