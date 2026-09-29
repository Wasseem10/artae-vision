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
const development = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/gmdcsa24/development-subjects-1-2.json')));
const examined = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/gmdcsa24/evaluation.json')));
for (const config of [
  { model: 'fall-window-model.json', predictions: 'pose-window-dev-predictions.json', results: development.results },
  { model: 'fall-window-model-v2.json', predictions: 'pose-window-v2-dev-predictions.json', results: [...development.results, ...examined.results] },
]) {
  const model = JSON.parse(fs.readFileSync(path.join(root, 'apps/web/src/lib', config.model)));
  const expected = JSON.parse(fs.readFileSync(path.join(root, 'artifacts/gmdcsa24', config.predictions)));
  for (const result of config.results) {
    const rule = new PoseWindowFallRule(model);
    const actual = [];
    for (const frame of result.poseTrace) {
      const feature = frame.y === null ? null : {
        x: 0.5, y: frame.y, verticality: frame.verticality, aspect: frame.aspect,
        visibility: 1,
      };
      if (rule.update(feature, frame.seconds)) actual.push(frame.seconds);
    }
    assert.deepEqual(actual, expected[result.id], `${config.model} runtime differs on ${result.id}`);
  }
  console.log(`${config.model}: Python and TypeScript agreed on ${config.results.length} examined clips`);
}
