// Compare annotations for human adjudication. Neither input is ground truth.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const { validateReview } = require('./motion-review-labels.cjs');

const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const category = actor => actor.startsWith('person-') ? 'person' : actor;
const unresolved = actor => ['uncertain', 'unreviewed'].includes(actor);

function compareReviews(packet, left, right) {
  assert.equal(packet.schemaVersion, 1, 'Unknown packet schema');
  const { packetId, ...content } = packet;
  assert.equal(packetId, digest(content), 'Packet content does not match its digest');
  assert.ok(Array.isArray(packet.frames) && packet.frames.length > 0, 'Packet has no frames');
  const keys = new Set();
  for (const frame of packet.frames) {
    assert.ok(typeof frame.key === 'string' && frame.key && !keys.has(frame.key), 'Invalid or duplicate frame key');
    keys.add(frame.key);
    assert.ok(typeof frame.clipId === 'string' && frame.clipId, 'Missing clip identity');
    assert.ok(Array.isArray(frame.observations), 'Missing observations');
    const slots = frame.observations.map(observation => observation.slot);
    assert.ok(slots.every(slot => typeof slot === 'string' && slot), 'Invalid observation slot');
    assert.equal(new Set(slots).size, slots.length, 'Duplicate observation slot');
  }
  validateReview(left, packet);
  validateReview(right, packet);

  const clips = new Map();
  packet.frames.forEach((frame, index) => {
    if (!clips.has(frame.clipId)) clips.set(frame.clipId, {
      clipId: frame.clipId, frames: 0, observations: 0,
      unreviewedCounts: [], countDisagreements: [], unresolvedObservations: [],
      categoryDisagreements: [], identityComparisons: 0, identityConflicts: [],
      personPairs: [],
    });
    const clip = clips.get(frame.clipId);
    const a = left.frames[index];
    const b = right.frames[index];
    clip.frames++;
    const count = { frame: frame.key, left: a.visiblePeople, right: b.visiblePeople };
    if (a.visiblePeople === null || b.visiblePeople === null) clip.unreviewedCounts.push(count);
    else if (a.visiblePeople !== b.visiblePeople) clip.countDisagreements.push(count);
    frame.observations.forEach((observation, slotIndex) => {
      clip.observations++;
      const leftActor = a.assignments[slotIndex].actor;
      const rightActor = b.assignments[slotIndex].actor;
      const row = { frame: frame.key, slot: observation.slot, left: leftActor, right: rightActor };
      if (unresolved(leftActor) || unresolved(rightActor)) clip.unresolvedObservations.push(row);
      else if (category(leftActor) !== category(rightActor)) clip.categoryDisagreements.push(row);
      else if (category(leftActor) === 'person') clip.personPairs.push(row);
    });
  });

  const rows = [...clips.values()].map(({ personPairs, ...clip }) => {
    // Compare identity relationships, not arbitrary person-N names. Keeping the
    // pairs clip-local also prevents treating person-1 in two videos as one actor.
    for (let i = 0; i < personPairs.length; i++) {
      for (let j = i + 1; j < personPairs.length; j++) {
        const first = personPairs[i];
        const second = personPairs[j];
        const leftSame = first.left === second.left;
        const rightSame = first.right === second.right;
        clip.identityComparisons++;
        if (leftSame !== rightSame) clip.identityConflicts.push({
          first, second, withinFrame: first.frame === second.frame,
          left: leftSame ? 'same-person' : 'different-people',
          right: rightSame ? 'same-person' : 'different-people',
        });
      }
    }
    return clip;
  });
  const totals = { clips: rows.length, frames: 0, observations: 0,
    unreviewedCounts: 0, countDisagreements: 0, unresolvedObservations: 0,
    categoryDisagreements: 0, identityComparisons: 0, identityConflicts: 0 };
  for (const row of rows) {
    for (const key of Object.keys(totals).filter(key => key !== 'clips')) {
      totals[key] += Array.isArray(row[key]) ? row[key].length : row[key];
    }
  }
  const describe = review => ({
    jsonSha256: digest(review), status: review.status, reviewer: review.reviewer,
    // Preserve declarations as declarations, never proof of independence.
    declaredReviewStatus: review.reviewStatus ?? null,
    declaredHumanAdjudicated: review.humanAdjudicated ?? null,
  });
  return {
    schemaVersion: 1, packetId, purpose: 'Annotation comparison for human adjudication',
    newInference: false, adjudicated: false, promoted: false,
    warning: 'Agreement is not ground truth or detector accuracy. Uncertain labels remain unresolved. Identity comparisons are correlated observation pairs, not independent samples.',
    inputs: { left: describe(left), right: describe(right) }, totals, clips: rows,
  };
}

if (require.main === module) {
  try {
    const [packetPath, leftPath, rightPath, outputPath, ...extra] = process.argv.slice(2);
    assert.ok(packetPath && leftPath && rightPath && outputPath && !extra.length,
      'Usage: node compare-motion-reviews.cjs <packet.json> <left-review.json> <right-review.json> <new-output.json>');
    const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
    const result = compareReviews(read(packetPath), read(leftPath), read(rightPath));
    result.comparatorSha256 = crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex');
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
    console.log(JSON.stringify({ output: outputPath, ...result.totals, adjudicated: false }));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

module.exports = { compareReviews };
