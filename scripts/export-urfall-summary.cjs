// Publish auditable aggregate and per-clip outcomes without redistributing footage or pose traces.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const input = path.resolve(root, process.argv[2] || 'artifacts/urfall/evaluation.json');
const output = path.resolve(root, process.argv[3] || 'docs/benchmarks/urfall-browser-v2.json');
const run = JSON.parse(fs.readFileSync(input, 'utf8'));

assert.equal(run.status, 'complete');
assert.equal(run.results.length, run.summary.totalCases);
assert.equal(run.partitions.reduce((count, partition) => count + partition.cases, 0), run.results.length);

const fields = [
  'id', 'category', 'partition', 'expectedEvents', 'eventStartSeconds',
  'frameCount', 'sourceZipSha256', 'videoSha256', 'durationSeconds',
  'framesAnalyzed', 'framesWithPose', 'detectedAtSeconds',
  'postureBaselineDetectedAtSeconds', 'meanInferenceMs', 'p95InferenceMs',
];
const summary = {
  schemaVersion: 1,
  note: 'Derived results only. Original media and per-frame pose traces are excluded.',
  sourceReportSchemaVersion: run.schemaVersion,
  generatedAt: run.generatedAt,
  scoringUnit: run.scoringUnit,
  sampleIntervalSeconds: run.sampleIntervalSeconds,
  dataset: run.dataset,
  provenance: run.provenance,
  summary: run.summary,
  postureBaselineSummary: run.postureBaselineSummary,
  partitions: run.partitions,
  results: run.results.map((result) => Object.fromEntries(
    fields.map((field) => [field, result[field]]),
  )),
  limitation: run.limitation,
};

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(summary, null, 2)}\n`);
console.log(`${output}: ${summary.results.length} clips, ${fs.statSync(output).size} bytes`);
