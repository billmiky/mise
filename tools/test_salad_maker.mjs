// Run: node --test tools/test_salad_maker.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const SM = createRequire(import.meta.url)('../assets/js/salad-maker.js');

const SLOTS = [
  { key: 'base', name: 'Base', pick: [1, 1], options: [{ name: 'Farro' }, { name: 'Quinoa' }, { name: 'Rice vermicelli', buy: ['rice vermicelli noodles'] }] },
  { key: 'veggies', name: 'Veggies', pick: [2, 3], options: [{ name: 'Carrots' }, { name: 'Cucumber' }, { name: 'Radishes' }, { name: 'Kimchi' }] },
  { key: 'dressing', name: 'Dressing', pick: [1, 1], single: true, options: [
    { name: 'Nuoc Cham', recipe: 'nuoc-cham', buy: ['fish sauce', 'limes', 'garlic'] },
    { name: 'Carrot Ginger', recipe: 'carrot-ginger', buy: ['carrots', 'ginger'] },
    { name: 'Lemon Tahini', buy: ['lemons', 'tahini'] },
  ] },
];

// A seeded random so the shuffle tests are repeatable
function rng(seed) {
  return () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
}

test('toggle adds and removes; the dressing slot only holds one', () => {
  let b = SM.emptyBowl(SLOTS);
  b = SM.toggle(SLOTS, b, 'veggies', 'Carrots');
  b = SM.toggle(SLOTS, b, 'veggies', 'Cucumber');
  assert.deepEqual(b.veggies, ['Carrots', 'Cucumber']);
  b = SM.toggle(SLOTS, b, 'veggies', 'carrots');
  assert.deepEqual(b.veggies, ['Cucumber'], 'matching ignores case');
  b = SM.toggle(SLOTS, b, 'dressing', 'Nuoc Cham');
  b = SM.toggle(SLOTS, b, 'dressing', 'Lemon Tahini');
  assert.deepEqual(b.dressing, ['Lemon Tahini'], 'a second dressing replaces the first');
});

test('toggle does not change the bowl it was given', () => {
  const b = SM.emptyBowl(SLOTS);
  SM.toggle(SLOTS, b, 'base', 'Farro');
  assert.deepEqual(b.base, []);
});

test('surprise picks within each slot\'s range, with no repeats', () => {
  for (let seed = 1; seed < 60; seed++) {
    const b = SM.surprise(SLOTS, rng(seed));
    assert.equal(b.base.length, 1);
    assert.ok(b.veggies.length >= 2 && b.veggies.length <= 3, `veggies ${b.veggies}`);
    assert.equal(new Set(b.veggies).size, b.veggies.length);
    assert.equal(b.dressing.length, 1);
  }
});

test('reroll changes only that slot and tries for something new', () => {
  const b = { base: ['Farro'], veggies: ['Carrots', 'Cucumber'], dressing: ['Nuoc Cham'] };
  for (let seed = 1; seed < 30; seed++) {
    const r = SM.reroll(SLOTS, b, 'dressing', rng(seed));
    assert.notEqual(r.dressing[0], 'Nuoc Cham');
    assert.deepEqual(r.base, ['Farro']);
    assert.deepEqual(r.veggies, ['Carrots', 'Cucumber']);
  }
});

test('grocery items use `buy`, merge duplicates and split out the pantry', () => {
  const b = { base: ['Rice vermicelli'], veggies: ['Carrots', 'Kimchi'], dressing: ['Carrot Ginger'] };
  const g = SM.groceryItems(SLOTS, b, (t) => t === 'ginger');
  assert.deepEqual(g.buy, ['rice vermicelli noodles', 'carrots', 'kimchi'], 'carrots listed once');
  assert.deepEqual(g.have, ['ginger']);
});

test('typed-in options go on the list as written', () => {
  const b = { base: [], veggies: ['Roasted Delicata'], dressing: [] };
  assert.deepEqual(SM.groceryItems(SLOTS, b).buy, ['roasted delicata']);
});

test('linked recipes come from the picked options', () => {
  const b = { base: ['Farro'], veggies: [], dressing: ['Nuoc Cham'] };
  assert.deepEqual(SM.linkedRecipes(SLOTS, b), [{ name: 'Nuoc Cham', recipe: 'nuoc-cham' }]);
});

test('saved salads round-trip and are matched to the bowl', () => {
  const b = { base: ['Quinoa'], veggies: ['Cucumber', 'Radishes'], dressing: ['Lemon Tahini'] };
  const entry = SM.toSaved(SLOTS, '  Spring  ', b);
  assert.equal(entry.name, 'Spring');
  assert.deepEqual(SM.fromSaved(SLOTS, entry), b);

  // Older entries may hold one value as a string, or leave a slot out
  assert.deepEqual(SM.fromSaved(SLOTS, { name: 'x', base: 'Farro' }), { base: ['Farro'], veggies: [], dressing: [] });

  const reordered = { base: ['Quinoa'], veggies: ['Radishes', 'Cucumber'], dressing: ['Lemon Tahini'] };
  assert.equal(SM.matchSaved(SLOTS, [entry], reordered), entry, 'order inside a slot does not matter');
  assert.equal(SM.matchSaved(SLOTS, [entry], { ...b, dressing: [] }), null);
});

test('upsert replaces by name (any case); remove drops it', () => {
  const list = [{ name: 'Thai' }, { name: 'Classic' }];
  const up = SM.upsert(list, { name: 'thai', base: ['Farro'] });
  assert.equal(up.length, 2);
  assert.deepEqual(up[0], { name: 'thai', base: ['Farro'] });
  assert.equal(list[0].name, 'Thai', 'the original list is untouched');
  assert.equal(SM.upsert(list, { name: 'Korean' }).length, 3);
  assert.deepEqual(SM.remove(list, 'CLASSIC'), [{ name: 'Thai' }]);
});

test('suggested names lead with the dressing, then the base', () => {
  assert.equal(SM.suggestName({ base: ['Farro'], dressing: ['Nuoc Cham'] }), 'Nuoc Cham & Farro Salad');
  assert.equal(SM.suggestName({ base: [], dressing: [] }), 'My Salad');
});
