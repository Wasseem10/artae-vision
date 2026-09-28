// Publish the locked subject result without copying participant video or pose traces.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const input = path.join(root, 'artifacts/gmdcsa24/evaluation.json');
const output = path.join(root, 'docs/benchmarks/gmdcsa24-subject-holdout-v1.json');
const report = JSON.parse(fs.readFileSync(input, 'utf8'));

assert.equal(report.status, 'complete');
assert.equal(report.dataset.datasetId, 'gmdcsa24-v2.1');
assert.equal(report.results.length, 80);
assert.equal(report.results.filter((item) => item.category === 'fall').length, 38);
assert.equal(report.results.filter((item) => item.category === 'daily_activity').length, 42);
assert.ok(report.results.every((item) => item.partition === 'holdout'));
assert.equal(report.provenance.localGitDirty, false);
assert.equal(report.provenance.candidate.name, 'PoseWindowLogistic/v1');

const fields = [
  'id', 'name', 'category', 'partition', 'subjectId', 'expectedEvents',
  'eventStartSeconds', 'sourceGitBlobSha1', 'videoSha256', 'durationSeconds',
  'framesAnalyzed', 'framesWithPose', 'detectedAtSeconds',
  'postureBaselineDetectedAtSeconds', 'windowModelDetectedAtSeconds',
  'meanInferenceMs', 'p95InferenceMs',
];
const compact = {
  schemaVersion: 1,
  note: 'Subject-separated research evaluation. Original videos and per-frame poses are excluded.',
  sourceReportSchemaVersion: report.schemaVersion,
  generatedAt: report.generatedAt,
  scoringUnit: report.scoringUnit,
  sampleIntervalSeconds: report.sampleIntervalSeconds,
  dataset: report.dataset,
  provenance: report.provenance,
  summary: report.summary,
  postureBaselineSummary: report.postureBaselineSummary,
  windowModelSummary: report.windowModelSummary,
  partitions: report.partitions,
  results: report.results.map((item) => Object.fromEntries(fields.map((field) => [field, item[field]]))),
  limitation: report.limitation,
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(compact, null, 2)}\n`);
console.log(`${output}: ${compact.results.length} clips, ${fs.statSync(output).size} bytes`);
