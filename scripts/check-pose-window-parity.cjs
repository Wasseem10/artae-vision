// Compare Python training replay and the exact TypeScript browser rule on local pose traces.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const typescript = require(require.resolve('typescript', { paths: [path.join(root, 'apps/web')] }));
const source = fs.readFileSync(path.join(root, 'apps/web/src/lib/pose-window-fall.ts'), 'utf8');
const compiled = typescript.transpileModule(source, {
  compilerOptions: { module: typescript.ModuleKind.CommonJS, target: typescript.ScriptTarget.ES2022 },
}).outputText;
const localModule = { exports: {} };
new Function('module', 'exports', compiled)(localModule, localModule.exports);
const { PoseWindowFallRule } = localModule.exports;
const model = JSON.parse(fs.readFileSync(path.join(root, 'apps/web/src/lib/fall-window-model.json')));
const report = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/gmdcsa24/evaluation.json')));
const expected = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/gmdcsa24/pose-window-dev-predictions.json')));

for (const result of report.results) {
  const rule = new PoseWindowFallRule(model);
  const actual = [];
  for (const frame of result.poseTrace) {
    const feature = frame.y === null ? null : {
      x: 0.5, y: frame.y, verticality: frame.verticality, aspect: frame.aspect,
      visibility: 1,
    };
    if (rule.update(feature, frame.seconds)) actual.push(frame.seconds);
  }
  assert.deepEqual(actual, expected[result.id], `Runtime differs on ${result.id}`);
}
console.log(`Python and TypeScript agreed on all ${report.results.length} development clips`);
