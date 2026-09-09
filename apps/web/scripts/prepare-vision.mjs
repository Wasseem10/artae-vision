// Self-host the pinned runtime. No camera images are sent to a model CDN.
import { cp, mkdir, access, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
await mkdir(resolve(root, 'public/vision'), { recursive: true });
await cp(resolve(root, 'node_modules/@mediapipe/tasks-vision/wasm'), resolve(root, 'public/vision/wasm'), { recursive: true });
await cp(resolve(root, 'node_modules/@mediapipe/tasks-vision/vision_bundle.cjs'), resolve(root, 'public/vision/vision.js'));
const licensePath = resolve(root, 'public/vision/LICENSE-APACHE-2.0.txt');
try { await access(licensePath); } catch {
  const response = await fetch('https://www.apache.org/licenses/LICENSE-2.0.txt');
  if (!response.ok) throw new Error('Could not acquire the runtime license text');
  const license = await response.text();
  if (!license.includes('Apache License') || !license.includes('Version 2.0')) throw new Error('Unexpected runtime license response');
  await writeFile(licensePath, license);
}
const target = resolve(root, 'public/vision/pose_landmarker_lite.task');
try { await access(target); } catch {
  const response = await fetch('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task');
  if (!response.ok) throw new Error(`Pose model download failed: ${response.status}`);
  await writeFile(target, new Uint8Array(await response.arrayBuffer()));
}
const digest = createHash('sha256').update(await readFile(target)).digest('hex');
if (digest !== '59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a') {
  throw new Error('Pose model integrity check failed. Do not serve this model.');
}
