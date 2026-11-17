// Build a local-only review packet from the frozen comparison, not fresh inference.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync, spawnSync } = require('node:child_process');
const { verifyArchive } = require('./diagnose-motion-association.cjs');
const { summarize } = require('./summarize-motion-association.cjs');
const root = path.resolve(__dirname, '../..');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const read = file => JSON.parse(fs.readFileSync(file));

function selectFrames(report, diagnostics) {
  assert.equal(diagnostics.captureRevision, report.revision);
  assert.equal(diagnostics.newInference, false);
  const regressions = report.results.filter(c => c.baseline.temporalEvents.length && !c.candidate.temporalEvents.length);
  const frames = [];
  for (const clip of regressions) {
    const row = diagnostics.rows.find(c => c.id === clip.id);
    assert.ok(row, `Missing diagnostics: ${clip.id}`);
    const drops = row.threeSecondsBeforeBaselineAlert.filter(h =>
      h.reason === 'ambiguous' && ['upright', 'descending'].includes(h.status));
    assert.ok(drops.length, `Missing armed-history loss: ${clip.id}`);
    const ticks = [...new Set(drops.flatMap(h => [-1, 0, 1].map(delta => Math.round(h.seconds * 10) + delta)))].sort((a, b) => a - b);
    for (const tick of ticks) {
      const frame = clip.frames.find(f => f.requestedSeconds === tick / 10);
      assert.ok(frame, `Missing surrounding sample: ${clip.id} at ${tick / 10}`);
      frames.push({ key: `${clip.id}@${tick / 10}`, clipId: clip.id, videoSha256: clip.videoSha256,
        requestedSeconds: frame.requestedSeconds, decodedSeconds: frame.decodedSeconds,
        drops: drops.filter(h => h.seconds === frame.requestedSeconds),
        observations: [
          ...(frame.primary ? [{ slot: 'primary', features: frame.primary }] : []),
          ...frame.multi.map((features, index) => ({ slot: `multi-${index}`, features })),
        ] });
    }
  }
  return frames;
}

function extractFrame(ffmpeg, media, seconds) {
  // Decode from the start; select by presentation time rather than approximate input seeking.
  const result = spawnSync(ffmpeg, ['-hide_banner', '-nostdin', '-i', media, '-an',
    '-vf', `select=gte(t\\,${Math.max(0, seconds - 0.00001)}),showinfo,scale=w=min(1280\\,iw):h=-2`,
    '-frames:v', '1', '-fps_mode', 'vfr', '-f', 'image2pipe', '-vcodec', 'mjpeg', '-q:v', '3', 'pipe:1'],
  { maxBuffer: 20 * 1024 * 1024, windowsHide: true });
  assert.equal(result.status, 0, result.stderr?.toString() || String(result.error));
  const match = result.stderr.toString().match(/\bn:\s*0\s+pts:.*?pts_time:([0-9.e+-]+)/);
  assert.ok(match, 'Missing decoded presentation timestamp');
  const actual = Number(match[1]);
  assert.ok(Math.abs(actual - seconds) <= 0.002, `Image time ${actual} differs from archived frame ${seconds}`);
  assert.ok(result.stdout.length > 0, 'Empty image');
  return { bytes: result.stdout, presentationSeconds: actual };
}

function main() {
  const [archiveArg, visionArg, ffmpegArg, outputArg] = process.argv.slice(2);
  assert.ok(outputArg, 'Pass archive.json vision-root ffmpeg-executable new-artifacts-directory');
  const output = path.resolve(outputArg), vision = path.resolve(visionArg);
  assert.ok(output.startsWith(path.join(root, 'artifacts') + path.sep), 'Keep media in ignored local artifacts');
  assert.ok(!fs.existsSync(output), 'Never overwrite a review packet');
  const paired = read(path.join(root, 'docs/benchmarks/motion-association-v1.json'));
  const diagnosticsBytes = fs.readFileSync(path.join(root, 'docs/benchmarks/motion-association-diagnostics-v1.json'));
  const diagnostics = JSON.parse(diagnosticsBytes);
  assert.equal(diagnostics.sourceReportSha256, paired.fullReportSha256);
  const report = verifyArchive(fs.readFileSync(archiveArg), paired);
  summarize(report); // Validate complete capture and event agreement before selecting windows.
  const manifestBytes = fs.readFileSync(path.join(vision, 'mpfdd/manifest.json'));
  assert.equal(sha(manifestBytes), report.manifestSha256);
  const manifest = JSON.parse(manifestBytes);
  const frames = selectFrames(report, diagnostics);
  const sources = new Map();
  for (const frame of frames) {
    if (sources.has(frame.clipId)) continue;
    const source = frame.clipId.startsWith('demo-')
      ? path.join(vision, 'samples', frame.clipId.slice(5))
      : path.join(vision, 'mpfdd', manifest.cases.find(c => c.id === frame.clipId).sourcePath);
    assert.ok(path.resolve(source).startsWith(vision + path.sep), 'Media path escapes vision root');
    assert.equal(sha(fs.readFileSync(source)), frame.videoSha256, `Changed media: ${frame.clipId}`);
    sources.set(frame.clipId, source);
  }
  const ffmpegVersion = execFileSync(ffmpegArg, ['-version'], { encoding: 'utf8', windowsHide: true }).split(/\r?\n/)[0];
  // Validate all sources before making output. A failed extraction leaves an explicitly incomplete folder.
  fs.mkdirSync(output, { recursive: true });
  for (const [i, frame] of frames.entries()) {
    const image = extractFrame(ffmpegArg, sources.get(frame.clipId), frame.decodedSeconds);
    frame.image = `frame-${String(i).padStart(2, '0')}.jpg`;
    frame.imageSha256 = sha(image.bytes);
    frame.imagePresentationSeconds = image.presentationSeconds;
    fs.writeFileSync(path.join(output, frame.image), image.bytes, { flag: 'wx' });
  }
  const packet = { schemaVersion: 1, scope: 'Development review; no labels or accuracy claims',
    sourceReportSha256: paired.fullReportSha256, diagnosticsSha256: sha(diagnosticsBytes),
    captureRevision: report.revision, builderSha256: sha(fs.readFileSync(__filename)), ffmpegVersion,
    validatorSha256: sha(fs.readFileSync(path.join(__dirname, 'motion-review-labels.cjs'))),
    templateSha256: sha(fs.readFileSync(path.join(__dirname, 'motion-review.html'))),
    notes: 'Local media only. Centers are archived torso features, not skeletons or person identities. Use uncertain when a center cannot establish an association. Single review is not independent adjudication.',
    frames };
  packet.packetId = sha(JSON.stringify(packet));
  fs.writeFileSync(path.join(output, 'packet.json'), JSON.stringify(packet, null, 2) + '\n', { flag: 'wx' });
  const html = fs.readFileSync(path.join(__dirname, 'motion-review.html'), 'utf8')
    .replace('/*REVIEW_VALIDATOR*/', fs.readFileSync(path.join(__dirname, 'motion-review-labels.cjs'), 'utf8'))
    .replace('/*REVIEW_PACKET*/ null', JSON.stringify(packet).replace(/</g, '\\u003c'));
  fs.writeFileSync(path.join(output, 'index.html'), html, { flag: 'wx' });
  console.log(JSON.stringify({ output, packetId: packet.packetId, clips: sources.size, frames: frames.length,
    observations: frames.reduce((n, f) => n + f.observations.length, 0), labelsCompleted: 0 }));
}
if (require.main === module) main();
module.exports = { selectFrames, extractFrame };
