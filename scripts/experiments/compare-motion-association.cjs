// Paired, local-only development comparison. Both rules see identical fresh
// worker output. No live detector change and no inferred ground-truth identity.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const samplerRef = 'f670e4bf1a0202514ab6ad3a5d5d07fbb136806b';

async function main() {
  const [visionArg, depsArg, outputArg] = process.argv.slice(2);
  assert.ok(visionArg && depsArg && outputArg, 'Pass vision-root dependencies-root new-output.json');
  assert.equal(git('status', '--porcelain'), '', 'Commit scoped code before capture');
  const revision = git('rev-parse', 'HEAD');
  const vision = path.resolve(visionArg), deps = path.resolve(depsArg), output = path.resolve(outputArg);
  assert.ok(output.startsWith(path.join(root, 'artifacts') + path.sep), 'Output must be local ignored artifacts');
  assert.ok(!fs.existsSync(output), 'Never overwrite evidence');
  const { chromium } = require(require.resolve('playwright', { paths: [deps] }));
  const ts = require(require.resolve('typescript', { paths: [deps] }));
  const fingerprint = {}, assets = new Map(), modules = [];
  function module(name, bytes, typescript = true) {
    fingerprint[name] = sha(bytes);
    const code = typescript ? ts.transpileModule(bytes.toString(), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    }}).outputText : bytes.toString();
    modules.push(`${JSON.stringify(name)}:(module,exports,require)=>{${code}\n}`);
  }
  for (const name of ['browser-pose', 'pose-window-fall', 'multi-person-fall'])
    module('./' + name, fs.readFileSync(path.join(root, `apps/web/src/lib/${name}.ts`)));
  module('./candidate', fs.readFileSync(path.join(__dirname, 'motion-association.cjs')), false);
  const sampler = execFileSync('git', ['show', `${samplerRef}:apps/web/src/lib/evaluation-video-frame.ts`], { cwd: root });
  assert.equal(sha(sampler), 'd281cf4041d74eb9241a443fe461f3bba9e87323d2a00084bb171a6c3402bac6');
  module('./sampler', sampler);
  const modelBytes = fs.readFileSync(path.join(root, 'apps/web/src/lib/fall-window-model.json'));
  fingerprint.windowModel = sha(modelBytes);
  fingerprint.harness = sha(fs.readFileSync(__filename));
  const manifestBytes = fs.readFileSync(path.join(vision, 'mpfdd/manifest.json'));
  assert.equal(sha(manifestBytes), '77b10d1a1eda79892e8915bd8b4d95be647f2e9f6e6afdc545469fde9f42b49d');
  const manifest = JSON.parse(manifestBytes);
  assert.equal(manifest.cases.length, 28);
  const cases = manifest.cases.map(c => ({ ...c, media: path.join(vision, 'mpfdd', c.sourcePath),
    expectedFall: c.expectedEvents > 0, scope: 'previously examined MPFDD development' }));
  // Public staged fall + ordinary sitting are demo controls, not held-out clips.
  for (const [file, expectedFall] of [['fall-lateral.mp4', true], ['fall-forward.mp4', true],
    ['fall-backwards.mp4', true], ['sitting.mp4', false], ['bending.mp4', false]]) {
    const media = path.join(vision, 'samples', file);
    assert.ok(fs.existsSync(media), `Missing demo control ${file}`);
    cases.push({ id: `demo-${file}`, media, expectedFall, videoSha256: sha(fs.readFileSync(media)),
      scope: 'staged demo control' });
  }
  for (const name of ['pose-worker.js', 'vision.js', 'pose_landmarker_lite.task',
    'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm',
    'wasm/vision_wasm_nosimd_internal.js', 'wasm/vision_wasm_nosimd_internal.wasm']) {
    const bytes = fs.readFileSync(path.join(vision, name));
    fingerprint[`runtime/${name}`] = sha(bytes); assets.set('/vision/' + name, bytes);
  }
  assert.equal(fingerprint['runtime/pose-worker.js'],
    sha(fs.readFileSync(path.join(root, 'apps/web/public/vision/pose-worker.js'))));
  for (const c of cases) {
    const bytes = fs.readFileSync(c.media);
    assert.equal(sha(bytes), c.videoSha256, `Changed video ${c.id}`);
    assets.set(`/media/${c.id}`, bytes);
  }
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (req.method !== 'GET') { res.writeHead(405).end(); return; }
    if (pathname === '/') { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>Local association comparison</title>'); return; }
    const bytes = assets.get(pathname);
    if (!bytes) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', pathname.endsWith('.js') ? 'text/javascript' :
      pathname.endsWith('.wasm') ? 'application/wasm' : pathname.startsWith('/media/') ? 'video/mp4' : 'application/octet-stream');
    if (req.headers.range) {
      const m = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range);
      const start = m ? Number(m[1]) : NaN, end = m && m[2] ? Math.min(Number(m[2]), bytes.length - 1) : bytes.length - 1;
      if (!Number.isSafeInteger(start) || start < 0 || start > end) { res.writeHead(416).end(); return; }
      res.writeHead(206, { 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${start}-${end}/${bytes.length}`, 'Content-Length': end - start + 1 });
      res.end(bytes.subarray(start, end + 1)); return;
    }
    res.setHeader('Content-Length', bytes.length); res.end(bytes);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    const launchArgs = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'];
    browser = await chromium.launch({ channel: 'chrome', headless: true, args: launchArgs });
    const page = await browser.newPage();
    const origin = `http://127.0.0.1:${server.address().port}`, blocked = [];
    await page.route('**/*', route => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      blocked.push(route.request().url()); return route.abort();
    });
    await page.goto(origin);
    await page.addScriptTag({ content: `const modules={${modules.join(',')}}; const cache={};
      window.ruleRequire=(name)=>{if(!cache[name]) {const m={exports:{}};cache[name]=m;modules[name](m,m.exports,window.ruleRequire);}return cache[name].exports;};` });
    const results = [];
    for (const c of cases) {
      const result = await page.evaluate(async ({ id, model }) => {
        const { poseFeatures, BrowserPoseRule } = window.ruleRequire('./browser-pose');
        const { PoseWindowFallRule } = window.ruleRequire('./pose-window-fall');
        const { FusedMultiPersonFallRule } = window.ruleRequire('./multi-person-fall');
        const { MotionAssociation } = window.ruleRequire('./candidate');
        const { seekPresentedFrame } = window.ruleRequire('./sampler');
        const baseline = new FusedMultiPersonFallRule(model);
        const candidate = new MotionAssociation(() => new BrowserPoseRule('fall'), () => new PoseWindowFallRule(model));
        const worker = new Worker('/vision/pose-worker.js'), video = document.createElement('video');
        video.muted = true; document.body.append(video);
        const request = (payload, transfer = []) => new Promise((resolve, reject) => {
          const timer = setTimeout(() => { cleanup(); reject(new Error('Worker timeout')); }, 45000);
          const cleanup = () => { clearTimeout(timer); worker.onmessage = null; worker.onerror = null; };
          worker.onerror = () => { cleanup(); reject(new Error('Worker failed')); };
          worker.onmessage = ({ data }) => { cleanup(); data.type === 'error' ? reject(new Error(data.message)) : resolve(data); };
          worker.postMessage(payload, transfer);
        });
        const frames = [];
        try {
          await request({ type: 'init', numPoses: 4 });
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Video load timeout')), 15000);
            video.onloadeddata = () => { clearTimeout(timer); resolve(); };
            video.onerror = () => { clearTimeout(timer); reject(new Error('Decode failed')); };
            video.src = `/media/${id}`; video.load();
          });
          const width = Math.min(1280, video.videoWidth), height = Math.round(video.videoHeight * width / video.videoWidth);
          const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
          const ctx = canvas.getContext('2d');
          for (let i = 0; i / 10 < video.duration; i++) {
            const time = i / 10;
            const presented = await seekPresentedFrame(video, time);
            ctx.drawImage(video, 0, 0, width, height);
            const bitmap = await createImageBitmap(canvas);
            const data = await request({ type: 'frame', bitmap, timestamp: time * 1000 }, [bitmap]);
            if (data.type !== 'result' || data.timestamp !== time * 1000) throw new Error('Mismatched result');
            const primary = poseFeatures(data.primaryLandmarks || [], width, height);
            const multi = data.poses.map(p => poseFeatures(p, width, height)).filter(Boolean);
            frames.push({ ...presented, primary, multi,
              baseline: baseline.update(primary, multi, time), candidate: candidate.update(primary, multi, time) });
          }
          return { duration: video.duration, width, height, frames };
        } finally { worker.terminate(); video.pause(); video.removeAttribute('src'); video.load(); video.remove(); }
      }, { id: c.id, model: JSON.parse(modelBytes) });
      const counts = {};
      for (const key of ['baseline', 'candidate']) counts[key] = {
        temporalEvents: result.frames.flatMap(f => f[key].filter(p => p.temporalHit).map(p => ({ seconds: f.requestedSeconds, trackId: p.id }))),
        windowSuggestions: result.frames.flatMap(f => f[key].filter(p => p.windowHit).map(p => ({ seconds: f.requestedSeconds, trackId: p.id }))),
      };
      results.push({ id: c.id, scope: c.scope, expectedFall: c.expectedFall,
        videoSha256: c.videoSha256, ...counts, ...result });
      console.log(`${c.id}: baseline ${counts.baseline.temporalEvents.length}, candidate ${counts.candidate.temporalEvents.length}, ${result.frames.length} frames`);
    }
    assert.deepEqual(blocked, [], 'Unexpected nonlocal request');
    assert.equal(git('rev-parse', 'HEAD'), revision); assert.equal(git('status', '--porcelain'), '');
    for (const c of cases) assert.equal(sha(fs.readFileSync(c.media)), c.videoSha256);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, JSON.stringify({ schemaVersion: 1, revision, dirty: false,
      scope: 'Development comparison only; no held-out accuracy or identity truth; not promoted',
      browser: browser.version(), node: process.version, typescript: ts.version, launchArgs,
      samplerRef, manifestSha256: sha(manifestBytes), fingerprint, results }, null, 2) + '\n', { flag: 'wx' });
    console.log(output);
  } finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
