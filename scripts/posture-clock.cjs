// Pure contracts for a local browser/media clock experiment. No model inference.
const assert = require('node:assert/strict');

function exactSeconds(value) {
  assert.equal(typeof value, 'string');
  const match = /^(-?\d+)\/([1-9]\d*)$/.exec(value);
  assert.ok(match, 'Expected a rational timestamp');
  const seconds = Number(match[1]) / Number(match[2]);
  assert.ok(Number.isFinite(seconds), 'Invalid rational timestamp');
  return seconds;
}

function classifyClock(mediaTime, rawPTS, firstPTS, tolerance = 0.000002) {
  assert.ok([mediaTime, rawPTS, firstPTS, tolerance].every(Number.isFinite));
  assert.ok(mediaTime >= 0 && rawPTS >= firstPTS && firstPTS >= 0 && tolerance > 0);
  const rawDeltaSeconds = mediaTime - rawPTS;
  const normalizedDeltaSeconds = mediaTime - (rawPTS - firstPTS);
  const rawMatch = Math.abs(rawDeltaSeconds) <= tolerance;
  const normalizedMatch = Math.abs(normalizedDeltaSeconds) <= tolerance;
  return { rawDeltaSeconds, normalizedDeltaSeconds, rawMatch, normalizedMatch,
    classification: rawMatch && normalizedMatch ? 'ambiguous' : rawMatch ? 'raw-presentation' : normalizedMatch ? 'first-frame-zero' : 'neither' };
}

// Caller-side planning only. Preserve the scheduled tick separately; request a
// real source frame instead of weakening the sampler's future-frame rejection.
function planSample(scheduledSeconds, verifiedFirstPTS, duration) {
  assert.ok([scheduledSeconds, verifiedFirstPTS, duration].every(Number.isFinite));
  assert.ok(scheduledSeconds >= 0 && verifiedFirstPTS >= 0 && duration > verifiedFirstPTS);
  const requestedSeconds = Math.max(scheduledSeconds, verifiedFirstPTS);
  assert.ok(requestedSeconds < duration, 'Sample is outside source duration');
  return { scheduledSeconds, requestedSeconds, verifiedFirstPTS };
}

function resolveRange(header, size) {
  assert.ok(Number.isSafeInteger(size) && size > 0);
  if (header === undefined) return { status: 200, start: 0, end: size - 1 };
  const match = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!match || (!match[1] && !match[2])) return null;
  let start, end;
  if (!match[1]) {
    const suffix = Number(match[2]);
    if (!Number.isSafeInteger(suffix) || suffix <= 0) return null;
    start = Math.max(0, size - suffix); end = size - 1;
  } else {
    start = Number(match[1]);
    end = match[2] ? Number(match[2]) : size - 1;
    if (![start, end].every(Number.isSafeInteger) || start >= size || end < start) return null;
    end = Math.min(end, size - 1);
  }
  return { status: 206, start, end };
}

module.exports = { exactSeconds, classifyClock, planSample, resolveRange };
