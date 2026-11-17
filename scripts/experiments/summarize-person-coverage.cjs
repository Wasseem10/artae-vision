// Conditional annotation diagnostics, not detector accuracy or ground truth.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { validatePacket } = require('./compare-motion-reviews.cjs');
const { validateReview } = require('./motion-review-labels.cjs');
const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');

function summarizeCoverage(packet, review) {
  validatePacket(packet);
  validateReview(review, packet);
  const frames = packet.frames.map((frame, index) => {
    assert.ok(frame.observations.every(o => /^(primary|multi-[0-9]+)$/.test(o.slot)),
      'Unknown observation stream; refusing to omit a slot');
    const row = review.frames[index];
    const streams = {};
    for (const stream of ['primary', 'multi', 'combined']) {
      const assignments = row.assignments.filter(a => stream === 'combined' ||
        (stream === 'primary' ? a.slot === 'primary' : a.slot.startsWith('multi-')));
      const personAssignments = assignments.filter(a => a.actor.startsWith('person-'));
      const assignedPeople = new Set(personAssignments.map(a => a.actor)).size;
      const unresolvedObservations = assignments.filter(a => ['uncertain', 'unreviewed'].includes(a.actor)).length;
      streams[stream] = {
        observations: assignments.length,
        assignedPersonObservations: personAssignments.length,
        assignedPeople,
        extraAssignmentsToSamePerson: personAssignments.length - assignedPeople,
        nonPersonObservations: assignments.filter(a => a.actor === 'non-person').length,
        unresolvedObservations,
        // Unknown observations may be non-person, duplicates, or distinct actors.
        // Bounds are conditional on the supplied count and person assignments.
        unrepresentedPeople: row.visiblePeople === null ? null : {
          minimum: Math.max(0, row.visiblePeople - assignedPeople - unresolvedObservations),
          maximum: row.visiblePeople - assignedPeople,
        },
      };
    }
    return { key: frame.key, clipId: frame.clipId, visiblePeople: row.visiblePeople, streams };
  });
  return {
    schemaVersion: 1, packetId: packet.packetId,
    purpose: 'Per-frame observation coverage conditional on supplied annotations',
    newInference: false, adjudicated: false, promoted: false,
    warning: 'These are annotation diagnostics, not recall, accuracy, verified identities or ground truth. Combined includes overlapping primary and raw multi observations, not fused tracks. Frames are selected development failures, not independent samples. Unknown assignments remain unresolved.',
    input: { reviewJsonSha256: digest(review), status: review.status, reviewer: review.reviewer,
      declaredReviewStatus: review.reviewStatus ?? null,
      declaredHumanAdjudicated: review.humanAdjudicated ?? null },
    totals: { clips: new Set(frames.map(f => f.clipId)).size, frames: frames.length,
      observations: frames.reduce((sum, f) => sum + f.streams.combined.observations, 0),
      unreviewedCountFrames: frames.filter(f => f.visiblePeople === null).length },
    frames,
  };
}

if (require.main === module) {
  try {
    const [packetPath, reviewPath, outputPath, ...extra] = process.argv.slice(2);
    assert.ok(packetPath && reviewPath && outputPath && !extra.length,
      'Usage: node summarize-person-coverage.cjs <packet.json> <review.json> <new-output.json>');
    const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
    const result = summarizeCoverage(read(packetPath), read(reviewPath));
    result.sourceSha256 = Object.fromEntries([
      __filename, require.resolve('./compare-motion-reviews.cjs'), require.resolve('./motion-review-labels.cjs'),
    ].map(file => [require('node:path').basename(file), crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]));
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
    console.log(JSON.stringify({ output: outputPath, ...result.totals, adjudicated: false }));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { summarizeCoverage };
