// Prepare the untouched CAUCAFall v4 videos for the browser benchmark.
// Research footage and source metadata stay local and gitignored.
// Requires ffmpeg on PATH or ARTAE_FFMPEG pointing to an ffmpeg executable.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { pipeline } = require('node:stream/promises');
const { promisify } = require('node:util');
const { execFile } = require('node:child_process');

const exec = promisify(execFile);
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'apps/web/public/vision/caucafall');
const artifact = path.join(root, 'artifacts/caucafall');
const api = 'https://data.mendeley.com/public-api/datasets/7w7fccy7ky';
const version = 4;
const annotationUrl = 'https://huggingface.co/datasets/simplexsigil2/omnifall/resolve/83572a37b9e3081df8c06a56874b1d1f2a19386c/parquet/labels/train-00000-of-00001.parquet';
const annotationSha256 = 'a5169d3e95b26080527265516d415d068a83c3dea4cddca8d0828a8d2345fd3a';
const ffmpeg = process.env.ARTAE_FFMPEG || 'ffmpeg';
const activities = new Map([
  ['Fall backwards', 'backwards'], ['Fall forward', 'forward'],
  ['Fall left', 'left'], ['Fall right', 'right'], ['Fall sitting', 'sitting'],
  ['Hop', 'hop'], ['Kneel', 'kneel'], ['Pick up object', 'pickup'],
  ['Sit down', 'sitdown'], ['Walk', 'walk'],
]);

async function json(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

async function sha256(filename) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(filename)) hash.update(chunk);
  return hash.digest('hex');
}

async function mapLimit(items, limit, task) {
  let next = 0;
  await Promise.all(Array.from({ length: limit }, async () => {
    while (next < items.length) {
      const index = next++;
      await task(items[index], index);
    }
  }));
}

async function sourceIndex() {
  const folders = await json(`${api}/folders/${version}`);
  const rootFolder = folders.find((item) => item.name === 'CAUCAFall' && !item.parent_id);
  assert.ok(rootFolder, 'Missing CAUCAFall root folder');
  const subjects = folders.filter((item) => item.parent_id === rootFolder.id);
  assert.equal(subjects.length, 10, 'Expected ten subjects');
  const entries = folders.filter((item) => activities.has(item.name));
  assert.equal(entries.length, 100, 'Expected ten activities for ten subjects');
  const cases = [];
  await mapLimit(entries, 8, async (folder) => {
    const subject = subjects.find((item) => item.id === folder.parent_id);
    assert.ok(subject, `Unexpected parent for ${folder.name}`);
    const match = /^Subject\.(10|[1-9])$/.exec(subject.name);
    assert.ok(match, `Unexpected subject ${subject.name}`);
    const files = await json(`${api}/files?folder_id=${folder.id}&version=${version}&%24start=0&%24limit=1000`);
    const videos = files.filter((item) => /\.avi$/i.test(item.filename));
    assert.equal(videos.length, 1, `Expected one AVI in ${subject.name}/${folder.name}`);
    const video = videos[0];
    assert.match(video.content_details.sha256_hash, /^[a-f0-9]{64}$/);
    assert.match(video.filename, /^[A-Za-z0-9]+S(10|[1-9])\.avi$/);
    assert.ok(video.filename.endsWith(`S${match[1]}.avi`));
    cases.push({
      id: `cauca-s${match[1]}-${folder.name.startsWith('Fall') ? 'fall' : 'adl'}-${activities.get(folder.name)}`,
      subject: Number(match[1]), activity: folder.name, sourceFilename: video.filename,
      sourceFileId: video.id, sourceSha256: video.content_details.sha256_hash,
      sourceSize: video.size, downloadUrl: video.content_details.download_url,
    });
  });
  cases.sort((a, b) => a.subject - b.subject || a.activity.localeCompare(b.activity));
  assert.equal(new Set(cases.map((item) => item.id)).size, 100);
  return { datasetId: 'caucafall-v4', source: 'https://data.mendeley.com/datasets/7w7fccy7ky/4',
    license: 'CC BY 4.0', version, cases };
}

async function download(item) {
  const directory = path.join(output, `Subject.${item.subject}`);
  await fsp.mkdir(directory, { recursive: true });
  const source = path.join(directory, item.sourceFilename);
  if (!(await fsp.stat(source).catch(() => null)) || await sha256(source) !== item.sourceSha256) {
    const partial = `${source}.part`;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await fetch(item.downloadUrl);
        if (!response.ok || !response.body) throw new Error(`${response.status} ${item.downloadUrl}`);
        await pipeline(require('node:stream').Readable.fromWeb(response.body), fs.createWriteStream(partial));
        assert.equal((await fsp.stat(partial)).size, item.sourceSize, `Size mismatch: ${item.id}`);
        assert.equal(await sha256(partial), item.sourceSha256, `SHA-256 mismatch: ${item.id}`);
        await fsp.rename(partial, source);
        break;
      } catch (error) {
        await fsp.rm(partial, { force: true });
        if (attempt === 2) throw error;
        await new Promise((resolve) => setTimeout(resolve, 1000 * 2 ** attempt));
      }
    }
  }
  const target = path.join(directory, item.sourceFilename.replace(/\.avi$/i, '.mp4'));
  if (!(await fsp.stat(target).catch(() => null))) {
    const partial = `${target}.part.mp4`;
    try {
      await exec(ffmpeg, [
        '-hide_banner', '-loglevel', 'error', '-y', '-i', source,
        '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', partial,
      ], { maxBuffer: 8 * 1024 * 1024 });
      await fsp.rename(partial, target);
    } catch (error) {
      await fsp.rm(partial, { force: true });
      throw error;
    }
  }
  return { ...item, videoSha256: await sha256(target),
    videoUrl: `/vision/caucafall/Subject.${item.subject}/${path.basename(target)}` };
}

async function downloadAnnotations() {
  const filename = path.join(artifact, 'omnifall-labels.parquet');
  if ((await fsp.stat(filename).catch(() => null)) && await sha256(filename) === annotationSha256) return;
  const response = await fetch(annotationUrl);
  if (!response.ok || !response.body) throw new Error(`Could not fetch pinned OmniFall labels: ${response.status}`);
  const partial = `${filename}.part`;
  try {
    await pipeline(require('node:stream').Readable.fromWeb(response.body), fs.createWriteStream(partial));
    assert.equal(await sha256(partial), annotationSha256, 'OmniFall annotation SHA-256 changed');
    await fsp.rename(partial, filename);
  } catch (error) {
    await fsp.rm(partial, { force: true });
    throw error;
  }
}

(async () => {
  await fsp.mkdir(artifact, { recursive: true });
  await downloadAnnotations();
  const index = await sourceIndex();
  await fsp.writeFile(path.join(artifact, 'source-index.json'), JSON.stringify(index, null, 2) + '\n');
  let completed = 0;
  const prepared = [];
  await mapLimit(index.cases, 3, async (item) => {
    prepared.push(await download(item));
    completed++;
    if (completed % 10 === 0) console.log(`Downloaded, verified, and transcoded ${completed}/100 clips`);
  });
  prepared.sort((a, b) => a.subject - b.subject || a.activity.localeCompare(b.activity));
  await fsp.writeFile(path.join(artifact, 'prepared-index.json'), JSON.stringify({ ...index, cases: prepared }, null, 2) + '\n');
  console.log(`Prepared ${prepared.length} CAUCAFall videos locally`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
