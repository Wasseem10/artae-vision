const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function summarize(report) {
  assert.equal(report.schemaVersion, 1);
  assert.equal(report.dirty, false);
  assert.equal(report.results.length, 33);
  assert.equal(new Set(report.results.map(c => c.id)).size, 33);
  const rows = report.results.map(c => {
    assert.ok(typeof c.expectedFall === 'boolean' && c.duration > 0);
    assert.equal(c.frames.length, Math.ceil(c.duration * 10), `Incomplete ${c.id}`);
    c.frames.forEach((f, i) => {
      assert.equal(f.requestedSeconds, i / 10);
      assert.ok(Number.isFinite(f.decodedSeconds) &&
        f.requestedSeconds - f.decodedSeconds <= .050001 &&
        f.decodedSeconds - f.requestedSeconds <= .002001);
      for (const key of ['baseline', 'candidate']) {
        assert.ok(Array.isArray(f[key]));
        assert.ok(f[key].every(t => Number.isInteger(t.id) && t.id > 0 &&
          typeof t.temporalHit === 'boolean' && typeof t.windowHit === 'boolean'));
      }
    });
    const result = { id: c.id, scope: c.scope, expectedFall: c.expectedFall,
      videoSha256: c.videoSha256, durationSeconds: c.duration, sampledFrames: c.frames.length };
    for (const key of ['baseline', 'candidate']) {
      const events = c.frames.flatMap(f => f[key].filter(t => t.temporalHit)
        .map(t => ({ seconds: f.requestedSeconds, trackId: t.id })));
      assert.deepEqual(events, c[key].temporalEvents, 'Event count must agree with full trace');
      result[key] = { alerted: events.length > 0, events };
    }
    return result;
  });
  const groups = {};
  for (const scope of new Set(rows.map(c => c.scope))) {
    const clips = rows.filter(c => c.scope === scope);
    groups[scope] = { clips: clips.length, falls: clips.filter(c => c.expectedFall).length,
      activities: clips.filter(c => !c.expectedFall).length,
      activityVideoSeconds: clips.filter(c => !c.expectedFall).reduce((n, c) => n + c.durationSeconds, 0),
      sampledFrames: clips.reduce((n, c) => n + c.sampledFrames, 0) };
    for (const key of ['baseline', 'candidate']) groups[scope][key] = {
      fallClipsAlerted: clips.filter(c => c.expectedFall && c[key].alerted).length,
      activityClipsAlerted: clips.filter(c => !c.expectedFall && c[key].alerted).length,
    };
  }
  return { groups, rows };
}

function main() {
  const [input, output] = process.argv.slice(2);
  assert.ok(input && output, 'Pass full-report.json new-summary.json');
  const bytes = fs.readFileSync(input), report = JSON.parse(bytes);
  // Verify the recorded source against its committed revision, not mutable files.
  for (const [key, file] of Object.entries({
    './candidate': 'scripts/experiments/motion-association.cjs',
    './browser-pose': 'apps/web/src/lib/browser-pose.ts',
    './pose-window-fall': 'apps/web/src/lib/pose-window-fall.ts',
    './multi-person-fall': 'apps/web/src/lib/multi-person-fall.ts',
    harness: 'scripts/experiments/compare-motion-association.cjs',
  })) assert.equal(sha(execFileSync('git', ['show', `${report.revision}:${file}`], { cwd: root })),
    report.fingerprint[key], `Source mismatch ${file}`);
  const result = { schemaVersion: 1, scope: report.scope, promoted: false,
    reason: 'Candidate regresses on all five positive clips detected by baseline; synthetic association tests do not establish video accuracy.',
    captureRevision: report.revision, fullReportSha256: sha(bytes),
    browser: report.browser, samplerRef: report.samplerRef,
    manifestSha256: report.manifestSha256, fingerprint: report.fingerprint, ...summarize(report) };
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
}
if (require.main === module) main();
module.exports = { summarize };
