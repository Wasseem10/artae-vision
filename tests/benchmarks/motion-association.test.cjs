const { test } = require('node:test');
const assert = require('node:assert/strict');
const { MotionAssociation, assignment } = require('../../scripts/experiments/motion-association.cjs');
const pose = (x, y = .3) => ({ x, y, verticality: .9, aspect: .5, visibility: .95 });
const factory = () => ({ update: () => false, status: 'unarmed' });
const tracker = () => new MotionAssociation(factory, factory);

test('global association avoids the locally cheapest pair that strands another observation', () => {
  assert.deepEqual(assignment([[.1, .12], [.11, Infinity]], .221), [1, 0]);
});
test('unmatched observations never force an invalid match', () => {
  assert.deepEqual(assignment([[Infinity], [0.1]], .221), [-1, 0]);
});
test('person identity survives primary slot exchange and raw pose reordering', () => {
  const t = tracker();
  assert.deepEqual(t.update(pose(.2), [pose(.2), pose(.8)], 0).map(x => x.id), [1, 2]);
  const result = t.update(pose(.8), [pose(.8), pose(.2)], .1);
  assert.deepEqual(result.map(x => x.id), [2, 1]);
  assert.equal(result[0].source, 'primary');
});
test('two people with established opposite velocities keep identities across a crossing', () => {
  const t = tracker();
  for (let i = 0; i <= 4; i++) t.update(null, [pose(.2 + i * .05), pose(.8 - i * .05)], i / 10);
  const result = t.update(null, [pose(.6), pose(.4)], .8);
  assert.deepEqual(result.map(x => x.id), [1, 2]);
});
test('ambiguous overlap clears old histories', () => {
  const t = tracker();
  t.update(null, [pose(.4), pose(.6)], 0);
  assert.deepEqual(t.update(null, [pose(.5)], .1), []);
  assert.equal(t.update(null, [pose(.5)], .2)[0].id, 3);
});
test('long gaps and rewound source clocks create fresh histories', () => {
  const t = tracker();
  assert.equal(t.update(pose(.2), [], 0)[0].id, 1);
  assert.equal(t.update(pose(.2), [], 1)[0].id, 2);
  assert.equal(t.update(pose(.2), [], .1)[0].id, 3);
});
test('missing observations do not appear as newly observed people', () => {
  const t = tracker();
  t.update(pose(.2), [], 0);
  assert.deepEqual(t.update(null, [], .1), []);
  assert.equal(t.update(pose(.2), [], .2)[0].id, 1);
});
test('invalid features and invalid clocks cannot enter a rule', () => {
  const t = tracker();
  assert.deepEqual(t.update(pose(NaN), [], 0), []);
  assert.deepEqual(t.update(pose(.2), [], NaN), []);
});
