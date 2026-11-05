// Run: node --test tools/test_recipe_matrix.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const MM = createRequire(import.meta.url)('../assets/js/recipe-matrix.js');

const slaw = { t: 'Lemon-Tahini Slaw', tg: ['side', 'salad', 'vegan'], time: 15, d: 'easy', n: 8, s: 3,
  g: 'cabbage lemon juice tahini cilantro scallions rice vinegar' };
const lasagna = { t: 'Spinach Lasagna', tg: ['dinner', 'italian', 'pasta', 'baking'], time: 120, d: 'medium', n: 16, s: 11,
  g: 'lasagna noodles ricotta mozzarella parmesan heavy cream butter all-purpose flour spinach' };
const pasta = { t: '20-Minute Cheesy Skillet Pasta', tg: ['dinner', 'pasta'], time: 20, d: 'easy', n: 8, s: 4,
  g: 'pasta butter cheddar cheese whole milk' };
const rolls = { t: 'Shrimp Summer Rolls With Nuoc Cham', tg: ['dinner', 'vietnamese', 'shrimp'], time: 75, d: 'medium', n: 15, s: 9,
  g: 'rice paper shrimp lettuce mint cilantro cucumber fish sauce lime juice rice vinegar' };

test('raw scores point the right way on each axis', () => {
  const s = MM.score;
  assert.ok(s(slaw).x < s(lasagna).x, 'slaw is fresher than lasagna');
  assert.ok(s(rolls).x < s(pasta).x, 'summer rolls are fresher than cheesy pasta');
  assert.ok(s(slaw).y < s(lasagna).y, 'slaw is quicker than lasagna');
  assert.ok(s(pasta).y < s(rolls).y, 'skillet pasta is quicker than summer rolls');
});

test('peanut butter is not butter', () => {
  const base = { t: 'Noodles', tg: [], time: 20 };
  assert.ok(MM.score({ ...base, g: 'unsalted butter' }).x > MM.score({ ...base, g: 'peanut butter' }).x);
});

test('four recipes, one in each quadrant', () => {
  const placed = MM.layout([rolls, lasagna, slaw, pasta]);
  const hood = (p) => MM.neighbourhood(p.x, p.y).id;
  assert.deepEqual(placed.map(hood), ['market-day', 'sunday-supper', 'fast-fresh', 'cozy-weeknight']);
  placed.forEach((p) => assert.ok(Math.abs(p.x) <= MM.LIMIT && Math.abs(p.y) <= MM.LIMIT));
});

test('a pinned recipe keeps exactly its spot', () => {
  const placed = MM.layout([slaw, { ...lasagna, m: ['-4', '-1.5'] }, { ...pasta, m: { x: 9, y: 0 } }]);
  assert.deepEqual([placed[1].x, placed[1].y, placed[1].pinned], [-4, -1.5, true]);
  assert.equal(placed[2].x, 5, 'pins are clamped to the plane');
  assert.equal(MM.layout([{ ...slaw, m: [null, null] }])[0].pinned, false);
});

test('deterministic, and the whole plane gets used', () => {
  assert.deepEqual(MM.layout([slaw, lasagna]), MM.layout([slaw, lasagna]));
  const many = [];
  for (let i = 0; i < 60; i++) many.push({ ...[slaw, lasagna, pasta, rolls][i % 4], t: 'recipe ' + i });
  const pts = MM.layout(many);
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  assert.ok(Math.min(...xs) < -3 && Math.max(...xs) > 3);
  assert.ok(Math.min(...ys) < -3 && Math.max(...ys) > 3);
});

test('nearest and neighbourhoods', () => {
  const placed = MM.layout([rolls, lasagna, slaw, pasta]);
  const near = MM.nearest(placed, 4, 4, 2);
  assert.equal(near.length, 2);
  assert.equal(near[0].recipe.t, 'Spinach Lasagna');
  assert.equal(MM.neighbourhood(-1, 1).id, 'market-day');
  assert.equal(MM.neighbourhood(0, 0).id, 'sunday-supper');
  assert.equal(MM.neighbourhood(-0.1, -0.1).id, 'fast-fresh');
  assert.equal(MM.neighbourhood(3, -2).id, 'cozy-weeknight');
});

test('course comes from the tags', () => {
  assert.equal(MM.course({ tg: ['dinner', 'dessert'] }), 'dessert');
  assert.equal(MM.course({ tg: ['breakfast', 'snack'] }), 'breakfast');
  assert.equal(MM.course({ tg: 'lunch|side' }), 'main');
  assert.equal(MM.course({ tg: ['salad'] }), 'side');
  assert.equal(MM.course({ tg: ['sauce'] }), 'other');
});
