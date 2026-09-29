// Exploratory object-box + cropped-pose worker. Not used by the live product.
self.exports = {};
importScripts('/vision/vision.js');
let detector;
let primaryModel;
let cropModel;
let canvas;
let context;

self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'init') {
      const files = await self.exports.FilesetResolver.forVisionTasks('/vision/wasm');
      detector = await self.exports.ObjectDetector.createFromOptions(files, {
        baseOptions: { modelAssetPath: '/vision/person_detector.tflite', delegate: 'CPU' },
        runningMode: 'VIDEO', scoreThreshold: 0.35,
        categoryAllowlist: ['person'], maxResults: 4,
      });
      primaryModel = await self.exports.PoseLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: '/vision/pose_landmarker_lite.task', delegate: 'CPU' },
        runningMode: 'VIDEO', numPoses: 1,
        minPoseDetectionConfidence: 0.6, minPosePresenceConfidence: 0.6,
        minTrackingConfidence: 0.6,
      });
      cropModel = await self.exports.PoseLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: '/vision/pose_landmarker_lite.task', delegate: 'CPU' },
        runningMode: 'IMAGE', numPoses: 1,
        minPoseDetectionConfidence: 0.6, minPosePresenceConfidence: 0.6,
      });
      canvas = new OffscreenCanvas(384, 384);
      context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) throw new Error('Offscreen canvas unavailable');
      self.postMessage({ type: 'ready' });
    } else if (data.type === 'frame') {
      if (!detector || !cropModel || !primaryModel) throw new Error('Models are not ready');
      const began = performance.now();
      const primary = primaryModel.detectForVideo(data.bitmap, data.timestamp).landmarks[0] || [];
      const boxes = detector.detectForVideo(data.bitmap, data.timestamp).detections || [];
      const poses = [];
      for (const detection of boxes) {
        const box = detection.boundingBox;
        if (!box || box.width < 12 || box.height < 12) continue;
        const side = Math.max(box.width, box.height) * 1.35;
        const x = box.originX + box.width / 2 - side / 2;
        const y = box.originY + box.height / 2 - side / 2;
        context.clearRect(0, 0, 384, 384);
        context.drawImage(data.bitmap, x, y, side, side, 0, 0, 384, 384);
        const crop = cropModel.detect(canvas).landmarks[0];
        if (crop) poses.push(crop.map((point) => ({
          x: (x + point.x * side) / data.bitmap.width,
          y: (y + point.y * side) / data.bitmap.height,
          visibility: point.visibility,
        })));
      }
      self.postMessage({ type: 'result', poses, landmarks: poses[0] || [],
        primaryLandmarks: primary, timestamp: data.timestamp,
        inferenceMs: performance.now() - began });
    }
  } catch (error) {
    self.postMessage({ type: 'error', message: error instanceof Error ? error.message : String(error) });
  } finally { data.bitmap?.close(); }
};
