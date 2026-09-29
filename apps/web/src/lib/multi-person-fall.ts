import { BrowserPoseRule, type PoseFeatures } from "./browser-pose";
import { PoseWindowFallRule, type PoseWindowModel } from "./pose-window-fall";

type Track = {
  id: number;
  x: number;
  y: number;
  lastSeen: number;
  temporal: BrowserPoseRule;
  window: PoseWindowFallRule;
};

export type TrackedPose = {
  index: number;
  id: number;
  features: PoseFeatures;
  temporalHit: boolean;
  windowHit: boolean;
  status: BrowserPoseRule["status"];
};

const MAX_MATCH_DISTANCE = 0.22;
const MAX_GAP_SECONDS = 0.9;
const AMBIGUITY_MARGIN = 0.04;

/** Local, session-only track numbers. They do not identify a person across runs. */
export class MultiPersonFallTracker {
  private tracks: Track[] = [];
  private nextId = 1;

  constructor(private readonly model: PoseWindowModel, private readonly maxPeople = 4) {}

  update(features: PoseFeatures[], t: number): TrackedPose[] {
    if (!Number.isFinite(t)) return [];
    this.tracks = this.tracks.filter((track) => t >= track.lastSeen && t - track.lastSeen <= MAX_GAP_SECONDS);
    const active = this.tracks;
    const seen = new Set<number>();
    const assigned = new Map<number, Track>();
    const ambiguous = new Set<number>();
    // Falling changes vertical position rapidly; horizontal position carries
    // more association weight in the fixed-camera browser workflow.
    const distances = features.map((feature) => active.map((track) =>
      Math.hypot(feature.x - track.x, (feature.y - track.y) * 0.4)));

    // If two old tracks are equally plausible, discard their motion history.
    // A swapped identity must not turn one person's standing pose and another
    // person's descent into a fall alert.
    features.forEach((_, index) => {
      const near = distances[index].map((distance, trackIndex) => ({ distance, trackIndex }))
        .filter((item) => item.distance <= MAX_MATCH_DISTANCE)
        .sort((a, b) => a.distance - b.distance);
      if (near.length > 1 && near[1].distance - near[0].distance < AMBIGUITY_MARGIN) {
        ambiguous.add(index);
        near.forEach((item) => seen.add(active[item.trackIndex].id));
      }
    });
    this.tracks = this.tracks.filter((track) => !seen.has(track.id));
    const pairs = features.flatMap((_, index) => ambiguous.has(index) ? [] : active.flatMap((track, trackIndex) => {
      const distance = distances[index][trackIndex];
      return seen.has(track.id) || distance > MAX_MATCH_DISTANCE ? [] : [{ index, track, distance }];
    })).sort((a, b) => a.distance - b.distance);
    const usedTracks = new Set<number>();
    for (const pair of pairs) {
      if (assigned.has(pair.index) || usedTracks.has(pair.track.id)) continue;
      assigned.set(pair.index, pair.track);
      usedTracks.add(pair.track.id);
    }

    const result: TrackedPose[] = [];
    const reservedTracks = new Set([...assigned.values()].map((track) => track.id));
    features.forEach((feature, index) => {
      if (ambiguous.has(index)) return;
      let track = assigned.get(index);
      if (!track) {
        if (this.tracks.length >= this.maxPeople) {
          const displaced = this.tracks.filter((candidate) => !reservedTracks.has(candidate.id) && !usedTracks.has(candidate.id))
            .sort((a, b) => a.lastSeen - b.lastSeen)[0];
          if (!displaced) return;
          this.tracks = this.tracks.filter((candidate) => candidate !== displaced);
        }
        track = {
          id: this.nextId++, x: feature.x, y: feature.y, lastSeen: t,
          temporal: new BrowserPoseRule("fall"),
          window: new PoseWindowFallRule(this.model),
        };
        this.tracks.push(track);
      }
      track.x = feature.x;
      track.y = feature.y;
      track.lastSeen = t;
      result.push({
        index, id: track.id, features: feature,
        temporalHit: track.temporal.update(feature, t),
        windowHit: track.window.update(feature, t),
        status: track.temporal.status,
      });
      usedTracks.add(track.id);
    });
    this.tracks = this.tracks.filter((track) => {
      if (!usedTracks.has(track.id)) {
        track.temporal.update(null, t);
        track.window.update(null, t);
      }
      return t - track.lastSeen <= MAX_GAP_SECONDS;
    });
    return result;
  }
}
