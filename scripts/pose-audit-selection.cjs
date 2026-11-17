const assert = require('node:assert/strict');

// A selection is fixed before inference or visual annotation. No labels needed.
function validateSelection(selection, manifest) {
  assert.ok(Array.isArray(selection.frames) && selection.frames.length, 'Empty frame selection');
  const seen = new Set();
  const cases = new Set(manifest.cases.map((row) => row.id));
  for (const frame of selection.frames) {
    assert.ok(cases.has(frame.caseId), `Unknown case: ${frame.caseId}`);
    assert.ok(Number.isFinite(frame.seconds) && frame.seconds >= 0 &&
      Math.abs(frame.seconds * 10 - Math.round(frame.seconds * 10)) < 1e-8,
    'Samples must be nonnegative finite times on the 0.1 second grid');
    const key = `${frame.caseId}:${frame.seconds}`;
    assert.ok(!seen.has(key), `Duplicate sample: ${key}`);
    seen.add(key);
  }
}

module.exports = { validateSelection };
