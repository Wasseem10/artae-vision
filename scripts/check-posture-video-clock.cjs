// Probe first/last browser-presented frames of all seven verified source videos.
// Read an exact committed evaluation sampler; do not change it or run inference.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { exactSeconds, classifyClock, resolveRange } = require('./posture-clock.cjs');
const root = path.resolve(__dirname, '..');
const hash = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
async function hashFile(file) {
  const digest = crypto.createHash('sha256');
  for await (const block of fs.createReadStream(file)) digest.update(block);
  return digest.digest('hex');
}

async function main() {
  const options = { mediaRoot: path.join(root, 'artifacts/posture-source-media'),
    samplerRef: 'origin/codex/evaluation-presented-frames' };
  for (let i = 2; i < process.argv.length; i += 2) {
    const key = { '--media-root': 'mediaRoot', '--sampler-ref': 'samplerRef', '--output': 'output' }[process.argv[i]];
    assert.ok(key && process.argv[i + 1], 'Use --output FILE [--media-root DIR] [--sampler-ref REF]');
    options[key] = process.argv[i + 1];
  }
  assert.ok(options.output, '--output is required');
  const output = path.resolve(options.output);
  assert.ok(!fs.existsSync(output), 'Choose a fresh output path');
  assert.equal(git('status', '--porcelain'), '', 'A clean committed checkout is required');
  const revision = git('rev-parse', 'HEAD');
  const samplerRevision = git('rev-parse', '--verify', `${options.samplerRef}^{commit}`);
  const samplerPath = 'apps/web/src/lib/evaluation-video-frame.ts';
  const samplerSource = execFileSync('git', ['show', `${samplerRevision}:${samplerPath}`], { cwd: root });
  const dependencyRoot = path.resolve(process.env.ARTAE_PLAYWRIGHT_ROOT || path.join(root, 'apps/web'));
  const { chromium } = require(require.resolve('playwright', { paths: [dependencyRoot] }));
  const ts = require(require.resolve('typescript', { paths: [dependencyRoot] }));
  const samplerJS = ts.transpileModule(samplerSource.toString('utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const reportPath = path.join(root, 'docs/benchmarks/posture-media-v1.json');
  const evidenceBytes = await fsp.readFile(reportPath);
  const evidence = JSON.parse(evidenceBytes);
  const lockBytes = await fsp.readFile(path.join(root, 'docs/benchmarks/posture-source-v1.lock.json'));
  const lock = JSON.parse(lockBytes);
  assert.equal(evidence.source_lock_sha256, hash(lockBytes));
  assert.equal(evidence.provenance.working_tree_dirty, false);
  const candidates = lock.videos.filter((v) => v.role === 'candidate-evaluation');
  assert.equal(candidates.length, 7);
  assert.equal(evidence.clips.length, candidates.length);
  const mediaRoot = await fsp.realpath(options.mediaRoot);
  const sources = [];
  for (const entry of candidates) {
    assert.match(entry.path, /^valid\/fall_detection_(?:[4-9]|10)\.mp4$/);
    const clip = evidence.clips.find((c) => c.path === entry.path);
    assert.ok(clip && clip.media_status === 'hash-verified-fully-decoded');
    assert.equal(clip.sha256, entry.sha256);
    const file = await fsp.realpath(path.join(mediaRoot, entry.path));
    assert.ok(file.startsWith(mediaRoot + path.sep));
    assert.equal((await fsp.stat(file)).size, entry.size);
    assert.equal(await hashFile(file), entry.sha256, `Source mismatch: ${entry.path}`);
    sources.push({ entry, clip, file });
  }
  const errors = [];
  const server = http.createServer(async (req, res) => {
    try {
      if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405).end(); return; }
      if (req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' });
        res.end('<!doctype html><html><title>Local source clock check</title><body></body></html>'); return;
      }
      const match = /^\/media\/([0-6])\.mp4$/.exec(req.url);
      if (!match) { res.writeHead(404).end(); return; }
      const source = sources[Number(match[1])];
      const range = resolveRange(req.headers.range, source.entry.size);
      if (!range) { res.writeHead(416, { 'Content-Range': `bytes */${source.entry.size}` }).end(); return; }
      const headers = { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store',
        'Content-Length': range.end - range.start + 1 };
      if (range.status === 206) headers['Content-Range'] = `bytes ${range.start}-${range.end}/${source.entry.size}`;
      res.writeHead(range.status, headers);
      if (req.method === 'HEAD') { res.end(); return; }
      const stream = fs.createReadStream(source.file, { start: range.start, end: range.end });
      stream.on('error', (error) => { errors.push(error.message); res.destroy(error); });
      res.on('close', () => stream.destroy());
      stream.pipe(res);
    } catch (error) { errors.push(error.message); res.destroy(error); }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true,
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    const context = await browser.newContext({ viewport: { width: 960, height: 640 } });
    let blockedRequests = 0;
    await context.route('**/*', (route) => {
      if (new URL(route.request().url()).origin !== origin) { blockedRequests++; return route.abort(); }
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(origin);
    await page.addScriptTag({ content: `window.clockSampler = (() => { const exports = {}; ${samplerJS}; return exports; })();` });
    const clips = [];
    for (let index = 0; index < sources.length; index++) {
      const source = sources[index];
      const observed = await page.evaluate(async ({ url }) => {
        const video = document.createElement('video');
        video.muted = true; video.playsInline = true; video.preload = 'auto';
        video.style.width = '800px'; document.body.replaceChildren(video);
        const observations = [];
        const nativeCallback = video.requestVideoFrameCallback.bind(video);
        video.requestVideoFrameCallback = (callback) => nativeCallback((now, metadata) => {
          observations.push({ mediaTime: metadata.mediaTime, presentedFrames: metadata.presentedFrames,
            width: metadata.width, height: metadata.height });
          callback(now, metadata);
        });
        let startSample;
        const ready = new Promise((resolve, reject) => {
          video.addEventListener('loadedmetadata', () => {
            // Exercise the actual committed sampler on the initial zero tick.
            startSample = window.clockSampler.seekPresentedFrame(video, 0, () => false, 8000)
              .then((value) => ({ accepted: true, value }), (error) => ({ accepted: false, error: error.message }));
            resolve();
          }, { once: true });
          video.addEventListener('error', () => reject(new Error('Video metadata failed')), { once: true });
          setTimeout(() => reject(new Error('Video metadata timed out')), 10000);
        });
        video.src = url; video.load();
        try {
          await ready;
          const sampler = await startSample;
          if (!observations.length) throw new Error('No first frame presented');
          const first = observations[0];
          const last = await new Promise((resolve, reject) => {
            const timer = setTimeout(() => { video.cancelVideoFrameCallback(handle); reject(new Error('Last frame timed out')); }, 8000);
            const handle = nativeCallback((_, metadata) => {
              clearTimeout(timer);
              resolve({ mediaTime: metadata.mediaTime, presentedFrames: metadata.presentedFrames,
                width: metadata.width, height: metadata.height });
            });
            video.currentTime = video.duration - 0.0001;
          });
          return { duration: video.duration, first, last, zeroTickSampler: sampler };
        } finally { video.pause(); video.removeAttribute('src'); video.load(); video.remove(); }
      }, { url: `${origin}/media/${index}.mp4` });
      const firstPTS = exactSeconds(source.clip.decode.first_pts_seconds_exact);
      const lastPTS = exactSeconds(source.clip.decode.last_pts_seconds_exact);
      assert.equal(observed.first.presentedFrames, 1, 'First observation must be the first presented frame');
      assert.ok(observed.last.presentedFrames > observed.first.presentedFrames);
      for (const sample of [observed.first, observed.last]) {
        assert.equal(sample.width, source.clip.decode.width); assert.equal(sample.height, source.clip.decode.height);
      }
      const clip = { path: source.entry.path, media_sha256: source.entry.sha256,
        raw_first_pts_seconds_exact: source.clip.decode.first_pts_seconds_exact,
        raw_last_pts_seconds_exact: source.clip.decode.last_pts_seconds_exact,
        observed, firstClock: classifyClock(observed.first.mediaTime, firstPTS, firstPTS),
        lastClock: classifyClock(observed.last.mediaTime, lastPTS, firstPTS) };
      clips.push(clip);
      console.log(JSON.stringify({ path: clip.path, first: clip.firstClock.classification,
        last: clip.lastClock.classification, zeroTickAccepted: observed.zeroTickSampler.accepted }));
    }
    assert.deepEqual(errors, [], 'Browser/server errors prevent publishing evidence');
    assert.equal(blockedRequests, 0, 'Unexpected nonlocal page request');
    for (const source of sources) assert.equal(await hashFile(source.file), source.entry.sha256);
    assert.equal(git('rev-parse', 'HEAD'), revision); assert.equal(git('status', '--porcelain'), '');
    const result = { schema_version: 1, purpose: 'first/last browser video clock check, no detector inference',
      benchmark_eligible: false, label_clock_verified: false, source_media_evidence_sha256: hash(evidenceBytes),
      source_lock_sha256: hash(lockBytes), code_revision: revision, working_tree_dirty: false,
      script_sha256: hash(await fsp.readFile(__filename)),
      contract_sha256: hash(await fsp.readFile(path.join(__dirname, 'posture-clock.cjs'))),
      sampler_revision: samplerRevision, sampler_path: samplerPath, sampler_sha256: hash(samplerSource),
      browser: browser.version(), playwright: require(require.resolve('playwright/package.json', { paths: [dependencyRoot] })).version,
      typescript: ts.version, node: process.version, tolerance_seconds: 0.000002, blocked_requests: blockedRequests,
      browser_server_errors: errors, clips };
    await fsp.mkdir(path.dirname(output), { recursive: true });
    await fsp.writeFile(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => { server.close(resolve); server.closeAllConnections(); });
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
