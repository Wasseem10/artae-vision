// Shared by the offline review page and Node validation. No detector imports.
(function (root) {
  function validateReview(review, packet, complete = false) {
    function check(ok, message) { if (!ok) throw new Error(message); }
    check(review && review.schemaVersion === 1, 'Unknown review schema');
    check(review.packetId === packet.packetId, 'Review belongs to a different packet');
    check(['draft', 'single-review'].includes(review.status), 'Invalid review status');
    check(typeof review.reviewer === 'string', 'Reviewer must be text');
    check(Array.isArray(review.frames) && review.frames.length === packet.frames.length, 'Frame coverage changed');
    const finishing = complete || review.status === 'single-review';
    if (finishing) check(review.reviewer.trim().length > 0, 'Enter the reviewer name');
    packet.frames.forEach((frame, i) => {
      const row = review.frames[i];
      check(row && row.key === frame.key, 'Frame identity/order changed');
      check(row.visiblePeople === null || (Number.isSafeInteger(row.visiblePeople) && row.visiblePeople >= 0), 'Invalid visible-person count');
      check(typeof row.notes === 'string', 'Frame notes must be text');
      check(Array.isArray(row.assignments) && row.assignments.length === frame.observations.length, 'Observation coverage changed');
      const actors = new Set();
      row.assignments.forEach((a, j) => {
        check(a && a.slot === frame.observations[j].slot, 'Observation identity/order changed');
        check(typeof a.actor === 'string' && /^(unreviewed|uncertain|non-person|person-[1-9][0-9]*)$/.test(a.actor), 'Invalid actor label');
        if (a.actor.startsWith('person-')) actors.add(a.actor);
        if (finishing) {
          check(a.actor !== 'unreviewed', 'Unreviewed observations remain');
          if (['uncertain', 'non-person'].includes(a.actor)) check(row.notes.trim().length > 0, 'Explain uncertain/non-person labels in frame notes');
        }
      });
      if (row.visiblePeople !== null) check(actors.size <= row.visiblePeople, 'More assigned actors than visible people');
      if (finishing) check(row.visiblePeople !== null, 'Visible-person counts remain unreviewed');
    });
    return review;
  }
  function blankReview(packet) {
    return { schemaVersion: 1, packetId: packet.packetId, status: 'draft', reviewer: '',
      frames: packet.frames.map(f => ({ key: f.key, visiblePeople: null, notes: '',
        assignments: f.observations.map(o => ({ slot: o.slot, actor: 'unreviewed' })) })) };
  }
  const api = { validateReview, blankReview };
  if (typeof module !== 'undefined') module.exports = api;
  else root.motionReview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
