// Independently implemented research candidate. No SPECTRA code or assets.
// Small (at most four people) exact assignment, with an explicit unmatched choice.
// This is not ByteTrack and does not infer identity from appearance.
const OPTIONS = Object.freeze({ maxPeople: 4, maxGap: 0.9, reach: 0.22,
  ambiguity: 0.04, predictionSeconds: 0.3, velocityBlend: 0.5 });

function distance(a, b) { return Math.hypot(a.x - b.x, (a.y - b.y) * 0.4); }
function valid(p) {
  return p && ['x', 'y', 'verticality', 'aspect', 'visibility'].every(k => Number.isFinite(p[k])) &&
    p.aspect > 0 && p.visibility >= 0 && p.visibility <= 1;
}

// Enumerate assignments rather than taking the nearest pair greedily.
// Each observation can match one track or pay the same fixed unmatched cost.
function assignment(costs, unmatched) {
  let best = Infinity, result = [];
  function visit(row, used, chosen, total) {
    if (total >= best) return;
    if (row === costs.length) { best = total; result = [...chosen]; return; }
    for (let col = 0; col < costs[row].length; col++) {
      if (used.has(col) || !Number.isFinite(costs[row][col])) continue;
      used.add(col); chosen.push(col);
      visit(row + 1, used, chosen, total + costs[row][col]);
      chosen.pop(); used.delete(col);
    }
    chosen.push(-1); visit(row + 1, used, chosen, total + unmatched); chosen.pop();
  }
  visit(0, new Set(), [], 0);
  return result;
}

class MotionAssociation {
  constructor(makeTemporal, makeWindow) {
    this.makeTemporal = makeTemporal; this.makeWindow = makeWindow;
    this.tracks = []; this.nextId = 1; this.lastTime = -Infinity;
    this.lastDiagnostics = null;
  }
  update(primary, multi, time) {
    // Research telemetry only: no actor labels, matching decisions or rule
    // outputs depend on these snapshots. IDs identify histories, not people.
    const diagnostics = this.lastDiagnostics = { seconds: Number.isFinite(time) ? time : null,
      invalidClock: !Number.isFinite(time), invalidObservations: 0,
      fusionSuppressed: 0, capacitySuppressed: 0, ambiguousObservations: [],
      matchedIds: [], createdIds: [], retainedMissingIds: [], droppedHistories: [] };
    const dropped = (track, reason) => diagnostics.droppedHistories.push({
      id: track.id, reason, status: track.temporal.status, lastObservedSeconds: track.time });
    if (!Number.isFinite(time)) return [];
    if (time <= this.lastTime) {
      this.tracks.forEach(t => dropped(t, 'clock-reset'));
      this.tracks = [];
    }
    this.lastTime = time;
    const observations = [];
    if (valid(primary)) observations.push({ features: primary, source: 'primary', index: -1 });
    else if (primary != null) diagnostics.invalidObservations++;
    multi.forEach((features, index) => {
      if (!valid(features)) { diagnostics.invalidObservations++; return; }
      // Use the existing fusion duplicate gate to isolate association changes.
      if (primary && distance(features, primary) <= 0.12 &&
          Math.abs(features.verticality - primary.verticality) <= 0.3) {
        diagnostics.fusionSuppressed++; return;
      }
      observations.push({ features, source: 'additional', index });
    });
    diagnostics.capacitySuppressed = Math.max(0, observations.length - OPTIONS.maxPeople);
    observations.splice(OPTIONS.maxPeople);
    this.tracks.filter(t => time - t.time > OPTIONS.maxGap).forEach(t => dropped(t, 'expired'));
    const previous = this.tracks.filter(t => time - t.time <= OPTIONS.maxGap);
    const costs = observations.map(o => previous.map(t => {
      const dt = Math.min(time - t.time, OPTIONS.predictionSeconds);
      const predicted = { x: t.features.x + t.vx * dt, y: t.features.y + t.vy * dt };
      const cost = distance(o.features, predicted);
      return cost <= OPTIONS.reach ? cost : Infinity;
    }));
    const rejectedRows = new Set(), rejectedTracks = new Set();
    // Ambiguous histories are discarded, not bridged through an overlap.
    costs.forEach((row, i) => {
      const near = row.map((value, j) => ({ value, j }))
        .filter(p => Number.isFinite(p.value)).sort((a, b) => a.value - b.value);
      if (near.length > 1 && near[1].value - near[0].value < OPTIONS.ambiguity) {
        rejectedRows.add(i);
        diagnostics.ambiguousObservations.push({ source: observations[i].source,
          index: observations[i].index, competingIds: near.map(p => previous[p.j].id) });
        near.forEach(p => rejectedTracks.add(p.j));
      }
    });
    const safe = costs.map((row, i) => row.map((cost, j) =>
      rejectedRows.has(i) || rejectedTracks.has(j) ? Infinity : cost));
    const matches = assignment(safe, OPTIONS.reach + 0.001);
    const used = new Set(), output = [], next = [];
    observations.forEach((o, i) => {
      if (rejectedRows.has(i)) return;
      const j = matches[i];
      let track = j < 0 ? null : previous[j];
      if (track) {
        diagnostics.matchedIds.push(track.id);
        used.add(j);
        const dt = time - track.time;
        if (dt > 0) {
          track.vx = (1 - OPTIONS.velocityBlend) * track.vx +
            OPTIONS.velocityBlend * (o.features.x - track.features.x) / dt;
          track.vy = (1 - OPTIONS.velocityBlend) * track.vy +
            OPTIONS.velocityBlend * (o.features.y - track.features.y) / dt;
        }
      } else {
        track = { id: this.nextId++, vx: 0, vy: 0,
          temporal: this.makeTemporal(), window: this.makeWindow() };
        diagnostics.createdIds.push(track.id);
      }
      track.features = { ...o.features }; track.time = time; next.push(track);
      output.push({ ...o, id: track.id,
        temporalHit: track.temporal.update(o.features, time),
        windowHit: track.window.update(o.features, time), status: track.temporal.status });
    });
    previous.forEach((track, j) => {
      if (used.has(j)) return;
      if (rejectedTracks.has(j)) { dropped(track, 'ambiguous'); return; }
      if (next.length >= OPTIONS.maxPeople) { dropped(track, 'capacity'); return; }
      track.temporal.update(null, time); track.window.update(null, time);
      diagnostics.retainedMissingIds.push(track.id);
      next.push(track);
    });
    this.tracks = next;
    return output;
  }
}
module.exports = { MotionAssociation, assignment, OPTIONS };
