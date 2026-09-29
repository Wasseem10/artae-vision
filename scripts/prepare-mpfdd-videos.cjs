// Download only the videos visible at the pinned MPFDD Git revision.
// Media and the manifest stay gitignored; no video is redistributed.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const REVISION = 'ec6cbcd81ed27e745ba5f6918192d7ec302d31c2';
const REPO = 'Hnnuliulei123456/MPFDD';
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'apps/web/public/vision/mpfdd');

function gitBlobSha1(buffer) {
  return crypto.createHash('sha1').update(`blob ${buffer.length}\0`).update(buffer).digest('hex');
}

async function checkedFetch(url) {
  const response = await fetch(url, { headers: { 'User-Agent': 'artae-research-benchmark' } });
  if (!response.ok) throw new Error(`${response.status} fetching ${url}`);
  return response;
}

async function main() {
  const tree = await (await checkedFetch(`https://api.github.com/repos/${REPO}/git/trees/${REVISION}?recursive=1`)).json();
  assert.equal(tree.truncated, false, 'Source tree must be complete');
  const videos = tree.tree.filter((item) => item.type === 'blob' && /^Scene_[1-4]\/S[1-4]-P[2-5]-F[0-5]-(ADL|FALL)-\d+\.mp4$/.test(item.path))
    .sort((a, b) => a.path.localeCompare(b.path));
  assert.equal(videos.length, 28, 'The pinned repository must expose exactly 28 videos');
  assert.equal(videos.reduce((sum, item) => sum + item.size, 0), 73046860, 'Source file sizes changed');
  const cases = [];
  for (const item of videos) {
    const match = /^Scene_([1-4])\/S([1-4])-P([2-5])-F([0-5])-(ADL|FALL)-(\d+)\.mp4$/.exec(item.path);
    assert.ok(match && match[1] === match[2]);
    const fallingPeople = Number(match[4]);
    assert.equal(match[5], fallingPeople ? 'FALL' : 'ADL');
    assert.ok(fallingPeople <= Number(match[3]));
    const destination = path.join(output, item.path);
    await fs.mkdir(path.dirname(destination), { recursive: true });
    let data;
    try { data = await fs.readFile(destination); } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    if (!data || data.length !== item.size || gitBlobSha1(data) !== item.sha) {
      data = Buffer.from(await (await checkedFetch(`https://raw.githubusercontent.com/${REPO}/${REVISION}/${item.path}`)).arrayBuffer());
      assert.equal(data.length, item.size, `Wrong media size: ${item.path}`);
      assert.equal(gitBlobSha1(data), item.sha, `Wrong Git blob: ${item.path}`);
      await fs.writeFile(`${destination}.download`, data);
      await fs.rename(`${destination}.download`, destination);
    }
    const sha256 = crypto.createHash('sha256').update(data).digest('hex');
    const id = `mpfdd-s${match[1]}-p${match[3]}-f${match[4]}-${match[5].toLowerCase()}-${match[6]}`;
    cases.push({
      id, name: `${match[3]} people · ${fallingPeople ? `${fallingPeople} labeled fallers` : 'daily activity'} · scene ${match[1]} · clip ${match[6]}`,
      category: fallingPeople ? 'fall' : 'daily_activity', partition: 'holdout',
      videoUrl: `/vision/mpfdd/${item.path}`, expectedEvents: fallingPeople ? 1 : 0,
      fallingPeopleCount: fallingPeople, sourcePath: item.path,
      videoSha256: sha256, sourceVideoSha256: sha256, sourceGitBlobSha1: item.sha,
    });
    console.log(`verified ${cases.length}/${videos.length}: ${item.path}`);
  }
  assert.equal(cases.filter((item) => item.category === 'fall').length, 22);
  assert.equal(cases.filter((item) => item.category === 'daily_activity').length, 6);
  const manifest = {
    schemaVersion: 1, datasetId: 'mpfdd-github-available-v1',
    source: `https://github.com/${REPO}/tree/${REVISION}`,
    citation: 'MPFDD: Multi-Person Falls Dataset, authors’ public GitHub repository.',
    license: 'No license was stated in the source repository on 2026-09-29; videos remain local and are not redistributed.',
    split: 'First-look, cross-source regression on 28 publicly accessible clips at the pinned revision; no training or tuning on this source before the first run.',
    labelNote: 'Filename provides people count, faller count, and fall/ADL class. No fall timing or person identity labels were provided; score only whether each clip alerted.',
    sourceRevision: REVISION, cases,
  };
  await fs.writeFile(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(`Prepared ${cases.length} clips: 22 fall, 6 daily activity; media remain ignored`);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
