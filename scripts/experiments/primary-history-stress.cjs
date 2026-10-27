// Replay the unchanged production rule on constructed feature sequences.
// Oracle resets use fixture actor labels unavailable to the live detector.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { score } = require('../score-primary-continuity.cjs');
const root = path.resolve(__dirname, '../..');
const hash = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');

function expandCases(spec) {
  assert.equal(spec.schemaVersion, 1, 'Unsupported cases');
  assert.equal(spec.intervalSeconds, 0.1, 'Expected 0.1 second grid');
  assert.ok(spec.cases.length > 0, 'Empty cases');
  for (const pose of Object.values(spec.poses)) {
    for (const field of ['x', 'y', 'verticality', 'aspect', 'visibility']) {
      assert.ok(Number.isFinite(pose[field]), `Invalid pose field: ${field}`);
    }
    for (const field of ['x', 'y', 'verticality', 'visibility']) {
      assert.ok(pose[field] >= 0 && pose[field] <= 1, `Out-of-range field: ${field}`);
    }
    assert.ok(pose.aspect > 0, 'Invalid aspect');
  }
  const ids = new Set();
  return spec.cases.map((item) => {
    assert.ok(typeof item.id === 'string' && item.id && !ids.has(item.id), 'Duplicate/missing case ID');
    ids.add(item.id);
    assert.equal(typeof item.expectedFall, 'boolean', 'Missing fixture expectation');
    assert.ok(item.bystander === undefined || typeof item.bystander === 'boolean', 'Invalid bystander');
    if (item.bystander) assert.ok(Object.hasOwn(spec.poses, 'bystander'), 'Missing bystander features');
    assert.ok(item.segments.length > 0, 'Empty sequence');
    const frames = [];
    for (const segment of item.segments) {
      assert.ok(Number.isInteger(segment.from) && segment.from === frames.length &&
        Number.isInteger(segment.through) && segment.through >= segment.from && segment.through < 10000,
      'Sequence must have complete, ordered, bounded frame coverage');
      assert.ok(segment.actor === null || (typeof segment.actor === 'string' && segment.actor.length > 0), 'Invalid actor');
      assert.equal(segment.actor === null, segment.pose === null, 'Missing observation must have no actor or pose');
      assert.ok(segment.pose === null || Object.hasOwn(spec.poses, segment.pose), 'Unknown pose');
      for (let index = segment.from; index <= segment.through; index++) {
        frames.push({ seconds: index / 10, actor: segment.actor,
          primary: segment.pose === null ? null : { ...spec.poses[segment.pose] } });
      }
    }
    return { id: item.id, expectedFall: item.expectedFall, frames,
      bystander: item.bystander ? { ...spec.poses.bystander } : null };
  });
}

function loadRules(dependenciesRoot) {
  const ts = require(require.resolve('typescript', { paths: [dependenciesRoot] }));
  const sources = {}, sourceHashes = {}, cache = {};
  for (const name of ['browser-pose', 'pose-window-fall', 'multi-person-fall']) {
    const filename = `apps/web/src/lib/${name}.ts`;
    const bytes = fs.readFileSync(path.join(root, filename));
    sourceHashes[filename] = hash(bytes);
    const compiled = ts.transpileModule(bytes.toString('utf8'), { reportDiagnostics: true,
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
    assert.ok(!compiled.diagnostics.some((row) => row.category === ts.DiagnosticCategory.Error), 'Transpilation failed');
    sources[`./${name}`] = compiled.outputText;
  }
  const requireRule = (name) => {
    assert.ok(Object.hasOwn(sources, name), `Unexpected import: ${name}`);
    if (!cache[name]) {
      cache[name] = {};
      vm.runInThisContext(`(function(exports, require) {${sources[name]}\n})`, { filename: name })(cache[name], requireRule);
    }
    return cache[name];
  };
  const modelFile = 'apps/web/src/lib/fall-window-model.json';
  const modelBytes = fs.readFileSync(path.join(root, modelFile));
  sourceHashes[modelFile] = hash(modelBytes);
  return { FusedRule: requireRule('./multi-person-fall').FusedMultiPersonFallRule,
    BrowserRule: requireRule('./browser-pose').BrowserPoseRule,
    WindowRule: requireRule('./pose-window-fall').PoseWindowFallRule,
    model: JSON.parse(modelBytes), sourceHashes, typescriptVersion: ts.version };
}

function runStress(spec, FusedRule, model) {
  const cases = expandCases(spec);
  const results = cases.map((item) => {
    const baseline = new FusedRule(model);
    let control = new FusedRule(model), previousActor = null;
    const actorBoundarySeconds = [];
    const runs = { baseline: { temporalEvents: [], windowSuggestionEvents: [], primaryPhaseTransitions: [] },
      oracleResetControl: { temporalEvents: [], windowSuggestionEvents: [], primaryPhaseTransitions: [] } };
    for (const frame of item.frames) {
      if (frame.actor !== null) {
        if (previousActor !== null && previousActor !== frame.actor) {
          control = new FusedRule(model);
          actorBoundarySeconds.push(frame.seconds);
        }
        previousActor = frame.actor;
      }
      let multi = [frame.primary, item.bystander].filter(Boolean);
      if (Math.round(frame.seconds * 10) % 2) multi = multi.toReversed();
      for (const [name, rule] of [['baseline', baseline], ['oracleResetControl', control]]) {
        const tracks = rule.update(structuredClone(frame.primary), structuredClone(multi), frame.seconds);
        const run = runs[name];
        for (const [flag, field] of [['temporalHit', 'temporalEvents'], ['windowHit', 'windowSuggestionEvents']]) {
          const ids = tracks.filter((row) => row[flag]).map((row) => row.id);
          if (ids.length) run[field].push({ seconds: frame.seconds, trackIds: ids });
        }
        const phase = tracks.find((row) => row.source === 'primary')?.status ?? 'unobserved';
        if (run.primaryPhaseTransitions.at(-1)?.phase !== phase) {
          run.primaryPhaseTransitions.push({ seconds: frame.seconds, phase });
        }
      }
    }
    return { id: item.id, expectedFall: item.expectedFall, frames: item.frames.length,
      actorBoundarySeconds, ...runs };
  });
  const summarize = (key) => ({
    syntheticFallCasesAlerted: results.filter((row) => row.expectedFall && row[key].temporalEvents.length).length,
    syntheticNonfallCasesAlerted: results.filter((row) => !row.expectedFall && row[key].temporalEvents.length).length,
  });
  return { results, summary: { syntheticFallCases: results.filter((row) => row.expectedFall).length,
    syntheticNonfallCases: results.filter((row) => !row.expectedFall).length,
    baseline: summarize('baseline'), oracleResetControl: summarize('oracleResetControl') } };
}

function observeWindow(capture, annotations, captureSha256, sourceHashes) {
  const matched = score(capture, annotations, captureSha256);
  for (const [name, expected] of Object.entries(sourceHashes)) {
    assert.equal(capture.sourceHashes[name], expected, `Observation used different source: ${name}`);
  }
  const observations = matched.observations.map((row, index) => {
    const primary = capture.results[index].tracks.find((track) => track.source === 'primary');
    if (primary) {
      assert.ok(['unarmed', 'upright', 'descending', 'alerted'].includes(primary.status), 'Unknown primary phase');
      assert.equal(typeof primary.temporalHit, 'boolean', 'Invalid temporal alert');
      assert.equal(typeof primary.windowHit, 'boolean', 'Invalid window suggestion');
    }
    return { seconds: row.seconds, primaryId: row.primaryId, association: row.status, actor: row.actor,
      phase: primary?.status ?? 'unobserved', temporalHit: primary?.temporalHit ?? false,
      windowSuggestionHit: primary?.windowHit ?? false };
  });
  return { scope: 'Unchanged rule state in a previously captured selected window; provisional actor associations, no counterfactual video result',
    captureSha256, captureCodeRevision: capture.codeRevision, reviewStatus: annotations.reviewStatus,
    summary: { frames: observations.length,
      ambiguousFrames: observations.filter((row) => row.association === 'ambiguous').length,
      phaseCounts: Object.fromEntries([...new Set(observations.map((row) => row.phase))]
        .map((phase) => [phase, observations.filter((row) => row.phase === phase).length])),
      temporalAlertFrames: observations.filter((row) => row.temporalHit).length,
      windowSuggestionFrames: observations.filter((row) => row.windowSuggestionHit).length },
    observations };
}

function main() {
  assert.ok([4, 6].includes(process.argv.length),
    'Usage: node scripts/experiments/primary-history-stress.cjs dependencies-root output.json [capture.json annotations.json]');
  const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
  assert.equal(git('status', '--porcelain'), '', 'Commit scoped code before replay');
  const codeRevision = git('rev-parse', 'HEAD');
  const rules = loadRules(path.resolve(process.argv[2]));
  const specBytes = fs.readFileSync(path.join(__dirname, 'primary-history-cases-v1.json'));
  const report = { schemaVersion: 1,
    scope: 'Constructed pose features, no video inference, held-out validation, detector change, or field accuracy claim',
    control: 'Oracle restarts the entire fused rule only at explicit fixture actor changes; uses unavailable identity labels and is not a deployable association algorithm',
    codeRevision, localGitDirty: false, nodeVersion: process.version,
    typescriptVersion: rules.typescriptVersion, sourceHashes: rules.sourceHashes,
    casesSha256: hash(specBytes), ...runStress(JSON.parse(specBytes), rules.FusedRule, rules.model) };
  if (process.argv.length === 6) {
    const bytes = fs.readFileSync(process.argv[4]);
    const annotationBytes = fs.readFileSync(process.argv[5]);
    report.observedWindow = observeWindow(JSON.parse(bytes), JSON.parse(annotationBytes), hash(bytes), rules.sourceHashes);
    report.observedWindow.annotationsSha256 = hash(annotationBytes);
  }
  assert.equal(git('rev-parse', 'HEAD'), codeRevision, 'Revision changed during replay');
  assert.equal(git('status', '--porcelain'), '', 'Checkout changed during replay');
  const output = path.resolve(process.argv[3]);
  const relative = path.relative(path.join(root, 'artifacts'), output);
  assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Output must be inside local artifacts');
  assert.ok(!fs.existsSync(output), 'Refusing to overwrite an earlier report');
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report.summary));
}

if (require.main === module) {
  try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { expandCases, loadRules, runStress, observeWindow };
