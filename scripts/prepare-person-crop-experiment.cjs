// Download the pinned, research-only object model used by the person-crop replay.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const url = 'https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite';
const sha256 = '2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b';
const target = path.resolve(__dirname, '../artifacts/person-crops/efficientdet_lite0_uint8.tflite');

(async () => {
  let bytes;
  try { bytes = await fs.readFile(target); } catch {
    const response = await fetch(url);
    assert.ok(response.ok, `Object model download failed: ${response.status}`);
    bytes = Buffer.from(await response.arrayBuffer());
  }
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), sha256,
    'Object model integrity check failed');
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, bytes);
  console.log(`Verified person-crop experiment model: ${sha256}`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
