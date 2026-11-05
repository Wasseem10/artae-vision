// Fresh local inference for review context. Never reconstructs historical poses.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const samplerRef = 'f670e4bf1a0202514ab6ad3a5d5d07fbb136806b';

function summarize(report, packet) {
  const { packetId, ...content } = packet;
  assert.equal(sha(JSON.stringify(content)), packetId, 'Packet integrity changed');
  assert.equal(report.packetId, packetId, 'Wrong packet');
  assert.equal(report.schemaVersion, 1);
  assert.equal(report.newInference, true); assert.equal(report.promoted, false);
  const clips = [...new Set(packet.frames.map(f => f.clipId))];
  assert.deepEqual(report.sources.map(s => s.id), clips, 'Source coverage changed');
  for (const source of report.sources)
    assert.ok(packet.frames.filter(f => f.clipId === source.id).every(f => f.videoSha256 === source.videoSha256), 'Changed source digest');
  assert.equal(report.warmupSamples, clips.reduce((n, id) => n + Math.max(...packet.frames.filter(f => f.clipId === id).map(f => Math.round(f.requestedSeconds * 10))) + 1, 0), 'Incomplete warmup');
  assert.equal(report.frames.length, packet.frames.length, 'Incomplete capture');
  const rows = report.frames.map((frame, index) => {
    const original = packet.frames[index];
    assert.equal(frame.key, original.key, 'Frame order changed');
    assert.equal(frame.requestedSeconds, original.requestedSeconds);
    assert.ok(Number.isFinite(frame.decodedSeconds) && Math.abs(frame.decodedSeconds - original.decodedSeconds) <= .002, 'Presented timestamp changed');
    assert.ok(Number.isInteger(frame.width) && frame.width > 0 && Number.isInteger(frame.height) && frame.height > 0);
    assert.match(frame.imageSha256, /^[a-f0-9]{64}$/);
    assert.ok(frame.poses.length <= 4);
    for (const pose of [frame.primaryLandmarks, ...frame.poses]) {
      assert.ok(pose.length === 0 || pose.length === 33, 'Incomplete skeleton');
      for (const point of pose) {
        assert.ok(['x', 'y', 'z', 'visibility'].every(k => Number.isFinite(point[k])), 'Nonfinite landmark');
      }
    }
    frame.observations.forEach((observation, i) => {
      assert.ok(['x', 'y', 'verticality', 'aspect', 'visibility'].every(k => Number.isFinite(observation.features[k])), 'Invalid derived features');
      if (observation.slot === 'primary') assert.equal(i, 0, 'Primary order changed');
      else {
        const offset = frame.observations[0]?.slot === 'primary' ? 1 : 0;
        assert.equal(observation.slot, `multi-${i - offset}`, 'Multi slot order changed');
        assert.ok(Number.isInteger(observation.rawIndex) && observation.rawIndex >= 0 && observation.rawIndex < frame.poses.length, 'Missing raw pose');
        if (i > offset) assert.ok(observation.rawIndex > frame.observations[i - 1].rawIndex, 'Raw pose order changed');
      }
    });
    const sameSlots = frame.observations.length === original.observations.length &&
      frame.observations.every((o, i) => o.slot === original.observations[i].slot);
    // This is slot-wise reproduction, not person association or an ID metric.
    const exactFeatures = sameSlots && frame.observations.every((o, i) =>
      ['x', 'y', 'verticality', 'aspect', 'visibility'].every(k =>
        Number.isFinite(o.features[k]) && o.features[k] === original.observations[i].features[k]));
    return { key: frame.key, originalObservations: original.observations.length,
      freshObservations: frame.observations.length, rawMultiPoses: frame.poses.length,
      primaryPosePresent: frame.primaryLandmarks.length === 33, sameSlots, exactFeatures,
      decodedSeconds: frame.decodedSeconds, imageSha256: frame.imageSha256 };
  });
  return { schemaVersion: 1, packetId, newInference: true, promoted: false,
    scope: 'Selected development frames; fresh skeleton context, not original archived poses or identity ground truth',
    revision: report.revision, browser: report.browser, fingerprint: report.fingerprint,
    sources: report.sources, warmupSamples: report.warmupSamples, frameCount: rows.length,
    exactFeatureFrames: rows.filter(r => r.exactFeatures).length, rows };
}

async function main() {
  const [visionArg, depsArg, outputArg] = process.argv.slice(2);
  assert.ok(outputArg, 'Pass vision-root dependencies-root new-artifacts-directory');
  assert.equal(git('status', '--porcelain'), '', 'Commit scoped code before capture');
  const revision = git('rev-parse', 'HEAD');
  const vision = path.resolve(visionArg), output = path.resolve(outputArg);
  assert.ok(output.startsWith(path.join(root, 'artifacts') + path.sep), 'Keep media local in ignored artifacts');
  assert.ok(!fs.existsSync(output), 'Never overwrite evidence');
  const packet = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-review-packet-v1.json')));
  const paired = JSON.parse(fs.readFileSync(path.join(root, 'docs/benchmarks/motion-association-v1.json')));
  const manifestBytes = fs.readFileSync(path.join(vision, 'mpfdd/manifest.json'));
  assert.equal(sha(manifestBytes), paired.manifestSha256);
  const manifest = JSON.parse(manifestBytes);
  const sources = [...new Set(packet.frames.map(f => f.clipId))].map(id => {
    const target = packet.frames.filter(f => f.clipId === id);
    const media = path.resolve(vision, id.startsWith('demo-') ? `samples/${id.slice(5)}` :
      `mpfdd/${manifest.cases.find(c => c.id === id).sourcePath}`);
    assert.ok(media.startsWith(vision + path.sep));
    const bytes = fs.readFileSync(media);
    assert.ok(target.every(f => f.videoSha256 === sha(bytes)), 'Changed source video');
    return { id, bytes, videoSha256: sha(bytes), ticks: target.map(f => Math.round(f.requestedSeconds * 10)) };
  });
  const { chromium } = require(require.resolve('playwright', { paths: [path.resolve(depsArg)] }));
  const ts = require(require.resolve('typescript', { paths: [path.resolve(depsArg)] }));
  const assets = new Map(), fingerprint = {}, modules = [];
  const poseBytes = fs.readFileSync(path.join(root, 'apps/web/src/lib/browser-pose.ts'));
  const sampler = execFileSync('git', ['show', `${samplerRef}:apps/web/src/lib/evaluation-video-frame.ts`], { cwd: root });
  for (const [name, bytes] of [['./browser-pose', poseBytes], ['./sampler', sampler]]) {
    fingerprint[name] = sha(bytes); assert.equal(fingerprint[name], paired.fingerprint[name]);
    const code = ts.transpileModule(bytes.toString(), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
    modules.push(`${JSON.stringify(name)}:(module,exports)=>{${code}\n}`);
  }
  for (const name of Object.keys(paired.fingerprint).filter(k => k.startsWith('runtime/'))) {
    const file = name.slice('runtime/'.length), bytes = fs.readFileSync(path.join(vision, file));
    fingerprint[name] = sha(bytes); assert.equal(fingerprint[name], paired.fingerprint[name], `Changed ${name}`);
    assets.set('/vision/' + file, bytes);
  }
  fingerprint.harness = sha(fs.readFileSync(__filename));
  const template = fs.readFileSync(path.join(__dirname, 'motion-pose-context.html'), 'utf8');
  fingerprint.template = sha(template);
  for (const source of sources) assets.set(`/media/${source.id}`, source.bytes);
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (req.method !== 'GET') return res.writeHead(405).end();
    if (pathname === '/') return res.end('<!doctype html><title>Fresh local pose context</title><style>body{margin:0}canvas{display:block}</style>');
    const bytes = assets.get(pathname);
    if (!bytes) return res.writeHead(404).end();
    res.setHeader('Content-Type', pathname.endsWith('.js') ? 'text/javascript' : pathname.endsWith('.wasm') ? 'application/wasm' : pathname.startsWith('/media/') ? 'video/mp4' : 'application/octet-stream');
    const range = req.headers.range;
    if (range) {
      const match = /^bytes=(\d+)-(\d*)$/.exec(range);
      const start = match ? Number(match[1]) : NaN, end = match?.[2] ? Math.min(Number(match[2]), bytes.length - 1) : bytes.length - 1;
      if (!Number.isSafeInteger(start) || start < 0 || start > end) return res.writeHead(416).end();
      res.writeHead(206, { 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${start}-${end}/${bytes.length}` });
      return res.end(bytes.subarray(start, end + 1));
    }
    res.setHeader('Content-Length', bytes.length); res.end(bytes);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true,
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } });
    const origin = `http://127.0.0.1:${server.address().port}`, blocked = [], errors = [];
    await page.route('**/*', route => {
      if (new URL(route.request().url()).origin === origin) return route.continue();
      blocked.push(route.request().url()); return route.abort();
    });
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(origin);
    await page.addScriptTag({ content: `const modules={${modules.join(',')}};const cache={};window.localRequire=name=>{if(!cache[name]){const m={exports:{}};modules[name](m,m.exports);cache[name]=m.exports;}return cache[name];};` });
    fs.mkdirSync(output, { recursive: true });
    const frames = [];
    await page.exposeFunction('retainFrame', async frame => {
      const image = `frame-${String(frames.length).padStart(2, '0')}.png`;
      const bytes = await page.locator('#capture').screenshot({ path: path.join(output, image) });
      frames.push({ ...frame, image, imageSha256: sha(bytes) });
    });
    let warmupSamples = 0;
    for (const source of sources) {
      warmupSamples += await page.evaluate(async ({ id, ticks }) => {
        const { poseFeatures } = window.localRequire('./browser-pose');
        const { seekPresentedFrame } = window.localRequire('./sampler');
        const worker = new Worker('/vision/pose-worker.js'), video = document.createElement('video');
        video.muted = true; document.body.append(video);
        const request = (payload, transfer = []) => new Promise((resolve, reject) => {
          const cleanup = () => { clearTimeout(timer); worker.onmessage = null; worker.onerror = null; };
          const timer = setTimeout(() => { cleanup(); reject(new Error('Worker timeout')); }, 45000);
          worker.onerror = () => { cleanup(); reject(new Error('Worker failure')); };
          worker.onmessage = ({ data }) => { cleanup(); data.type === 'error' ? reject(new Error(data.message)) : resolve(data); };
          worker.postMessage(payload, transfer);
        });
        const canvas = document.createElement('canvas'); canvas.id = 'capture'; document.body.append(canvas);
        try {
          await request({ type: 'init', numPoses: 4 });
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Media timeout')), 15000);
            video.onloadeddata = () => { clearTimeout(timer); resolve(); };
            video.onerror = () => { clearTimeout(timer); reject(new Error('Media error')); };
            video.src = `/media/${id}`; video.load();
          });
          const width = Math.min(1280, video.videoWidth), height = Math.round(video.videoHeight * width / video.videoWidth);
          canvas.width = width; canvas.height = height;
          const ctx = canvas.getContext('2d'), last = Math.max(...ticks);
          if (!(last / 10 < video.duration)) throw new Error('Requested frame outside media');
          for (let tick = 0; tick <= last; tick++) {
            const presented = await seekPresentedFrame(video, tick / 10);
            ctx.drawImage(video, 0, 0, width, height);
            const bitmap = await createImageBitmap(canvas);
            const timestamp = (tick / 10) * 1000;
            const data = await request({ type: 'frame', timestamp, bitmap }, [bitmap]);
            if (data.type !== 'result' || data.timestamp !== timestamp) throw new Error('Worker response mismatch');
            if (ticks.includes(tick)) {
              const primary = poseFeatures(data.primaryLandmarks, width, height);
              const multi = data.poses.map((pose, rawIndex) => ({ rawIndex, features: poseFeatures(pose, width, height) })).filter(p => p.features);
              await window.retainFrame({ key: `${id}@${tick / 10}`, clipId: id, ...presented, width, height,
                primaryLandmarks: data.primaryLandmarks, poses: data.poses,
                observations: [...(primary ? [{ slot: 'primary', features: primary }] : []),
                  ...multi.map((p, i) => ({ slot: `multi-${i}`, ...p }))] });
            }
          }
          return last + 1;
        } finally { worker.terminate(); video.pause(); video.removeAttribute('src'); video.load(); video.remove(); canvas.remove(); }
      }, { id: source.id, ticks: source.ticks });
      console.log(`${source.id}: full skeletons retained for ${source.ticks.length} review frames`);
    }
    assert.deepEqual(blocked, []); assert.deepEqual(errors, []);
    assert.equal(git('rev-parse', 'HEAD'), revision); assert.equal(git('status', '--porcelain'), '');
    const report = { schemaVersion: 1, revision, packetId: packet.packetId, newInference: true, promoted: false,
      browser: browser.version(), node: process.version, typescript: ts.version, fingerprint,
      sources: sources.map(({ id, videoSha256 }) => ({ id, videoSha256 })), warmupSamples, frames };
    const summary = summarize(report, packet);
    const bytes = JSON.stringify(report, null, 2) + '\n';
    fs.writeFileSync(path.join(output, 'capture.json'), bytes, { flag: 'wx' });
    fs.writeFileSync(path.join(output, 'summary.json'), JSON.stringify({ ...summary, captureSha256: sha(bytes) }, null, 2) + '\n', { flag: 'wx' });
    fs.writeFileSync(path.join(output, 'index.html'), template.replace('/*CAPTURE*/ null', JSON.stringify(report).replace(/</g, '\\u003c')), { flag: 'wx' });
    console.log(JSON.stringify({ frames: summary.frameCount, exactFeatureFrames: summary.exactFeatureFrames, warmupSamples, output }));
  } finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
}
module.exports = { summarize };
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
