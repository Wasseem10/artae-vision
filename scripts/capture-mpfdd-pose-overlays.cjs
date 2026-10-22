// Local research-only capture. No production server, model change, or media upload.
// See docs/mpfdd-pose-overlay-audit.md for arguments and interpretation limits.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { validateSelection } = require('./pose-audit-selection.cjs');

const root = path.resolve(__dirname, '..');
const hash = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const readJson = async (file) => JSON.parse(await fs.readFile(file, 'utf8'));

async function main() {
  const args = {};
  for (let i = 2; i < process.argv.length; i += 2) {
    assert.ok(process.argv[i].startsWith('--') && process.argv[i + 1], 'Expected --name value');
    const name = process.argv[i].slice(2);
    assert.ok(['media-root', 'vision-root', 'dependencies-root', 'reference-report', 'samples', 'output-dir'].includes(name), `Unknown argument: ${name}`);
    assert.ok(!args[name], `Duplicate argument: ${name}`);
    args[name] = path.resolve(process.argv[i + 1]);
  }
  for (const name of ['media-root', 'vision-root', 'dependencies-root', 'reference-report']) {
    assert.ok(args[name], `Missing --${name}`);
  }
  const { chromium } = require(require.resolve('playwright', { paths: [args['dependencies-root']] }));
  const ts = require(require.resolve('typescript', { paths: [args['dependencies-root']] }));
  assert.equal(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim(), '',
    'Commit scoped source before replay; inputs and outputs must stay ignored');
  const codeRevision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
  const labelsPath = args['samples'] || path.join(root, 'docs/benchmarks/mpfdd-visible-person-labels-v1.json');
  const selectionSha256 = hash(await fs.readFile(labelsPath));
  const labels = await readJson(labelsPath);
  const manifestPath = path.join(args['media-root'], 'manifest.json');
  const manifest = await readJson(manifestPath);
  const reference = await readJson(args['reference-report']);
  assert.equal(hash(await fs.readFile(manifestPath)), labels.manifestSha256, 'Changed manifest');
  assert.equal(hash(await fs.readFile(args['reference-report'])), labels.browserReportSha256, 'Changed reference');
  assert.equal(manifest.sourceRevision, labels.sourceRevision);
  validateSelection(labels, manifest);
  const sourceHashes = {};
  const modules = [];
  for (const name of ['browser-pose', 'pose-window-fall', 'multi-person-fall']) {
    const file = `apps/web/src/lib/${name}.ts`;
    const bytes = await fs.readFile(path.join(root, file));
    sourceHashes[file] = hash(bytes);
    assert.equal(sourceHashes[file], reference.provenance.localSourceHashes[file], `Changed rule source: ${file}`);
    const code = ts.transpileModule(bytes.toString(), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    }}).outputText;
    modules.push(`${JSON.stringify(`./${name}`)}: (exports, require) => {${code}\n}`);
  }
  const modelFile = 'apps/web/src/lib/fall-window-model.json';
  const windowModel = await readJson(path.join(root, modelFile));
  sourceHashes[modelFile] = hash(await fs.readFile(path.join(root, modelFile)));
  assert.equal(sourceHashes[modelFile], reference.provenance.localSourceHashes[modelFile]);
  const bundle = `const modules={${modules.join(',')}}; const cache={};
    const require=(name)=>{if(!cache[name]){cache[name]={}; modules[name](cache[name],require);} return cache[name];};
    window.auditRules={...require('./browser-pose'),...require('./multi-person-fall')};`;
  const assets = new Map();
  for (const name of ['pose-worker.js', 'vision.js', 'pose_landmarker_lite.task',
    'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm',
    'wasm/vision_wasm_nosimd_internal.js', 'wasm/vision_wasm_nosimd_internal.wasm']) {
    const bytes = await fs.readFile(path.join(args['vision-root'], name));
    assets.set(`/vision/${name}`, bytes);
    sourceHashes[`runtime/${name}`] = hash(bytes);
  }
  assert.equal(sourceHashes['runtime/pose-worker.js'], hash(await fs.readFile(path.join(root, 'apps/web/public/vision/pose-worker.js'))));
  assert.equal(sourceHashes['runtime/pose_landmarker_lite.task'], reference.provenance.detector.modelSha256);
  const cases = manifest.cases.filter((item) => labels.frames.some((frame) => frame.caseId === item.id));
  assert.equal(new Set(labels.frames.map((frame) => frame.caseId)).size, cases.length);
  for (const item of cases) {
    const filename = path.resolve(args['media-root'], item.sourcePath);
    assert.ok(filename.startsWith(args['media-root'] + path.sep), 'Media outside input directory');
    const bytes = await fs.readFile(filename);
    assert.equal(hash(bytes), item.videoSha256, `Changed media: ${item.id}`);
    assets.set(`/media/${item.id}.mp4`, bytes);
  }
  const outputBase = args['output-dir'] || path.join(root, 'artifacts/mpfdd-pose-overlays');
  const relativeOutput = path.relative(path.join(root, 'artifacts'), outputBase);
  assert.ok(relativeOutput && !relativeOutput.startsWith('..') && !path.isAbsolute(relativeOutput),
    'Output directory must be inside this checkout artifacts directory');
  await fs.mkdir(outputBase, { recursive: true });
  // Keep successful captures intact, including when a later replay fails.
  const output = await fs.mkdtemp(path.join(outputBase, 'capture-'));
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost').pathname;
    if (request.method !== 'GET') { response.writeHead(405).end(); return; }
    if (url === '/') { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><title>Local pose audit</title>'); return; }
    const bytes = assets.get(url);
    if (!bytes) { response.writeHead(404).end(); return; }
    response.setHeader('Content-Type', url.endsWith('.wasm') ? 'application/wasm' :
      url.endsWith('.js') ? 'text/javascript' : url.endsWith('.mp4') ? 'video/mp4' : 'application/octet-stream');
    if (url.endsWith('.mp4')) {
      response.setHeader('Accept-Ranges', 'bytes');
      if (request.headers.range) {
        const match = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range);
        const start = match ? Number(match[1]) : bytes.length;
        const end = match && match[2] ? Math.min(Number(match[2]), bytes.length - 1) : bytes.length - 1;
        if (start > end || start >= bytes.length) { response.writeHead(416).end(); return; }
        response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${bytes.length}`,
          'Content-Length': end - start + 1 });
        response.end(bytes.subarray(start, end + 1)); return;
      }
    }
    response.setHeader('Content-Length', bytes.length);
    response.end(bytes);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  let browser;
  const results = [];
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.addScriptTag({ content: bundle });
    for (const item of cases) {
      const targets = labels.frames.filter((frame) => frame.caseId === item.id).map((frame) => frame.seconds);
      const frames = await page.evaluate(async ({ id, targets, windowModel }) => {
        const worker = new Worker('/vision/pose-worker.js');
        const request = (type, data, transfer = []) => new Promise((resolve, reject) => {
          const timeout = setTimeout(() => { cleanup(); reject(new Error('Pose worker timeout')); }, 30000);
          const cleanup = () => { clearTimeout(timeout); worker.removeEventListener('message', receive); worker.removeEventListener('error', fail); };
          const fail = () => { cleanup(); reject(new Error('Pose worker failed')); };
          const receive = ({ data }) => {
            if (data.type === 'error' || data.type === type) {
              cleanup(); data.type === 'error' ? reject(new Error(data.message)) : resolve(data);
            }
          };
          worker.addEventListener('message', receive); worker.addEventListener('error', fail);
          worker.postMessage(data, transfer);
        });
        const video = document.createElement('video');
        video.muted = true;
        document.body.append(video);
        const canvas = document.createElement('canvas');
        const captured = [];
        try {
          await request('ready', { type: 'init', numPoses: 4 });
          await new Promise((resolve, reject) => {
            video.onloadeddata = resolve; video.onerror = () => reject(new Error('Video decode failed'));
            video.src = `/media/${id}.mp4`; video.load();
          });
          if (targets.some((time) => time >= video.duration)) throw new Error('Sample outside video');
          canvas.width = video.videoWidth; canvas.height = video.videoHeight;
          const context = canvas.getContext('2d');
          const fused = new window.auditRules.FusedMultiPersonFallRule(windowModel);
          for (let index = 0; index <= Math.round(Math.max(...targets) * 10); index++) {
            const seconds = index / 10;
            // seeked/currentTime alone can leave a stale decoded frame. Require
            // a presented frame at the requested timestamp before inference.
            const decodedSeconds = await new Promise((resolve, reject) => {
              let callback;
              const timeout = setTimeout(() => { video.cancelVideoFrameCallback(callback); reject(new Error('Decoded video frame timeout')); }, 10000);
              callback = video.requestVideoFrameCallback((_, metadata) => {
                clearTimeout(timeout);
                if (Math.abs(metadata.mediaTime - seconds) > 0.001) reject(new Error(`Wrong decoded timestamp: ${metadata.mediaTime} vs ${seconds}`));
                else resolve(metadata.mediaTime);
              });
              // Enter the frame slightly past its boundary to avoid a seek
              // rounding down to the preceding frame. Verify actual mediaTime.
              video.currentTime = seconds + 0.001;
            });
            const bitmap = await createImageBitmap(video);
            const reply = await request('result', { type: 'frame', bitmap, timestamp: seconds * 1000 }, [bitmap]);
            const raw = (reply.poses || []).map((landmarks, rawIndex) => ({ rawIndex, landmarks,
              features: window.auditRules.poseFeatures(landmarks, canvas.width, canvas.height) }));
            const usable = raw.filter((pose) => pose.features);
            const primary = window.auditRules.poseFeatures(reply.primaryLandmarks || [], canvas.width, canvas.height);
            const tracks = fused.update(primary, usable.map((pose) => pose.features), seconds);
            if (!targets.includes(seconds)) continue;
            context.drawImage(video, 0, 0);
            const draw = (landmarks, color, label) => {
              context.strokeStyle = color; context.fillStyle = color; context.lineWidth = 2;
              for (const [a, b] of window.auditRules.POSE_CONNECTIONS) {
                if ((landmarks[a]?.visibility || 0) < 0.6 || (landmarks[b]?.visibility || 0) < 0.6) continue;
                context.beginPath(); context.moveTo(landmarks[a].x * canvas.width, landmarks[a].y * canvas.height);
                context.lineTo(landmarks[b].x * canvas.width, landmarks[b].y * canvas.height); context.stroke();
              }
              const anchor = landmarks[11];
              if (anchor) { context.font = 'bold 18px sans-serif'; context.fillText(label, anchor.x * canvas.width, anchor.y * canvas.height - 8); }
            };
            draw(reply.primaryLandmarks || [], '#ffffff', 'primary');
            raw.forEach((pose) => draw(pose.landmarks, ['#00dfff', '#ff66dd', '#ffee33', '#44ff66'][pose.rawIndex], `raw ${pose.rawIndex}`));
            context.fillStyle = '#111111'; context.fillRect(0, 0, canvas.width, 27);
            context.fillStyle = '#ffffff'; context.font = '16px sans-serif';
            context.fillText(`${id} @ ${seconds}s | raw ${raw.length} | usable ${usable.length} | fused ${tracks.length}`, 8, 19);
            captured.push({ seconds, decodedSeconds, width: canvas.width, height: canvas.height, raw,
              primaryLandmarks: reply.primaryLandmarks, primaryFeatures: primary, tracks,
              png: canvas.toDataURL('image/png').split(',')[1] });
          }
          return captured;
        } finally { worker.terminate(); video.removeAttribute('src'); video.load(); video.remove(); }
      }, { id: item.id, targets, windowModel });
      for (const frame of frames) {
        const name = `${item.id}-${frame.seconds}.png`;
        const image = Buffer.from(frame.png, 'base64');
        await fs.writeFile(path.join(output, name), image);
        delete frame.png;
        const archived = reference.results.find((row) => row.id === item.id).observationTrace.find((row) => row.seconds === frame.seconds);
        results.push({ caseId: item.id, videoSha256: item.videoSha256, ...frame,
          overlayFile: name, overlaySha256: hash(image),
          archivedCounts: { raw: archived.rawPoseCount, usable: archived.usablePoseCount, fused: archived.trackIds.length },
          countsMatchArchive: frame.raw.length === archived.rawPoseCount &&
            frame.raw.filter((pose) => pose.features).length === archived.usablePoseCount && frame.tracks.length === archived.trackIds.length });
      }
    }
    assert.equal(execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), codeRevision,
      'Code revision changed during capture');
    assert.equal(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim(), '',
      'Checkout changed during capture');
    assert.equal(hash(await fs.readFile(labelsPath)), selectionSha256, 'Selection changed during capture');
    const report = { schemaVersion: 1, scope: 'Local pose-overlay diagnostic on examined frames; no promotion or accuracy score',
      codeRevision, localGitDirty: false, browserVersion: browser.version(), typescriptVersion: ts.version,
      selectionSha256,
      manifestSha256: labels.manifestSha256, referenceReportSha256: labels.browserReportSha256,
      sampleIntervalSeconds: 0.1, seekOffsetSeconds: 0.001,
      warmup: 'Every sample from 0 through the last requested timestamp, fresh worker per clip; decoded timestamps verified',
      sourceHashes, results };
    await fs.writeFile(path.join(output, 'capture.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({ output, sampledFrames: results.length, countsMatchingArchive: results.filter((row) => row.countsMatchArchive).length }));
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
