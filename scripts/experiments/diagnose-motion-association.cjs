// Explain discarded histories without altering the archived candidate's outputs.
// This replays existing observations; it is not a new inference or accuracy run.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { MotionAssociation } = require('./motion-association.cjs');
const { summarize } = require('./summarize-motion-association.cjs');
const { loadRules } = require('./primary-history-stress.cjs');
const root = path.resolve(__dirname, '../..');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');

function diagnose(report, makeTracker) {
  summarize(report); // Complete 10 Hz capture, unique clips and event agreement.
  return report.results.map(clip => {
    const tracker = makeTracker(), droppedHistories = [], createdIds = new Set();
    let ambiguousFrames = 0, fusionSuppressed = 0, capacitySuppressed = 0;
    for (const frame of clip.frames) {
      const actual = tracker.update(frame.primary, frame.multi, frame.requestedSeconds);
      assert.deepEqual(actual, frame.candidate,
        `Candidate replay diverged: ${clip.id} at ${frame.requestedSeconds}`);
      const d = tracker.lastDiagnostics;
      assert.equal(d.invalidClock, false);
      assert.equal(d.invalidObservations, 0, 'Archived observations must be valid');
      if (d.ambiguousObservations.length) ambiguousFrames++;
      fusionSuppressed += d.fusionSuppressed;
      capacitySuppressed += d.capacitySuppressed;
      d.createdIds.forEach(id => createdIds.add(id));
      droppedHistories.push(...d.droppedHistories.map(h => ({ seconds: d.seconds, ...h })));
    }
    const firstBaselineAlert = clip.baseline.temporalEvents[0]?.seconds ?? null;
    const counts = Object.fromEntries(['ambiguous', 'expired', 'capacity', 'clock-reset']
      .map(reason => [reason, droppedHistories.filter(h => h.reason === reason).length]));
    // A diagnostic window, not an annotated ground-truth fall interval.
    const beforeBaselineAlert = firstBaselineAlert === null ? null : droppedHistories.filter(h =>
      h.seconds >= Math.max(0, firstBaselineAlert - 3) && h.seconds <= firstBaselineAlert);
    return { id: clip.id, scope: clip.scope, expectedFall: clip.expectedFall,
      sampledFrames: clip.frames.length, replayMatchesEveryFrame: true,
      historiesCreated: createdIds.size, ambiguousFrames, fusionSuppressed,
      capacitySuppressed, dropsByReason: counts,
      armedHistoriesDropped: droppedHistories.filter(h => ['upright', 'descending'].includes(h.status)).length,
      descendingHistoriesDropped: droppedHistories.filter(h => h.status === 'descending').length,
      firstBaselineAlertSeconds: firstBaselineAlert,
      threeSecondsBeforeBaselineAlert: beforeBaselineAlert, droppedHistories };
  });
}

function verifyArchive(bytes, expected) {
  assert.equal(sha(bytes), expected.fullReportSha256, 'Archived report digest mismatch');
  const report = JSON.parse(bytes);
  assert.equal(report.revision, expected.captureRevision, 'Archived capture revision mismatch');
  return report;
}

function main() {
  const [input, output, dependencies = path.join(root, 'apps/web')] = process.argv.slice(2);
  assert.ok(input && output, 'Pass archived-report.json new-diagnostics.json [web-dependencies]');
  const expected = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-association-v1.json')));
  const report = verifyArchive(fs.readFileSync(input), expected);
  const rules = loadRules(dependencies);
  for (const [file, digest] of Object.entries(rules.sourceHashes)) {
    const key = file.endsWith('fall-window-model.json') ? 'windowModel' : './' + path.basename(file, '.ts');
    assert.equal(digest, report.fingerprint[key], `Rule/model changed: ${file}`);
  }
  const rows = diagnose(report, () => new MotionAssociation(
    () => new rules.BrowserRule('fall'), () => new rules.WindowRule(rules.model)));
  const result = { schemaVersion: 1, scope: 'Offline diagnosis of previously examined development observations',
    promoted: false, newInference: false, sourceReportSha256: expected.fullReportSha256,
    captureRevision: report.revision, instrumentationSha256: sha(fs.readFileSync(require.resolve('./motion-association.cjs'))),
    diagnosticScriptSha256: sha(fs.readFileSync(__filename)),
    rules: rules.sourceHashes, clips: rows.length,
    sampledFrames: rows.reduce((n, c) => n + c.sampledFrames, 0), rows };
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(rows.map(({ droppedHistories, ...row }) => row), null, 2));
}
if (require.main === module) main();
module.exports = { diagnose, verifyArchive };
