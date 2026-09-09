/* A classic worker keeps synchronous WASM inference off the controls/UI thread.
 * MediaPipe 0.10.32 CommonJS bundle is self-hosted by prepare-vision.mjs. */
self.exports = {};
importScripts('/vision/vision.js');
let model;
self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'init') {
      const files = await self.exports.FilesetResolver.forVisionTasks('/vision/wasm');
      model = await self.exports.PoseLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: '/vision/pose_landmarker_lite.task', delegate: 'CPU' },
        runningMode: 'VIDEO', numPoses: 1,
        minPoseDetectionConfidence: 0.6, minPosePresenceConfidence: 0.6,
        minTrackingConfidence: 0.6,
      });
      self.postMessage({ type: 'ready' });
    } else if (data.type === 'frame') {
      if (!model) throw new Error('Pose model is not ready');
      const result = model.detectForVideo(data.bitmap, data.timestamp);
      self.postMessage({ type: 'result', landmarks: result.landmarks[0] || [], timestamp: data.timestamp });
    }
  } catch (error) {
    self.postMessage({ type: 'error', message: error instanceof Error ? error.message : String(error) });
  } finally { data.bitmap?.close(); }
};
