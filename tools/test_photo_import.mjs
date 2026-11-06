// Run: node --test tools/test_photo_import.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const P = createRequire(import.meta.url)('../assets/js/photo-import.js');

// Roughly what Tesseract gives back for a two-part cookbook page
const page = `
CRISPY CHICKPEAS WITH GREENS

Serves 4   PREP 10 MIN   COOK 1 HR 5 MIN

This is the dinner I make when the fridge is
nearly empty and everyone is hungry.

2 cans (15 oz) chickpeas, drained
3 Tbsp olive oil
½ tsp smoked paprika
For the greens:
1 bunch kale, stems removed and
finely chopped
Kosher salt

1. Heat the oven to 425°F. Pat the chickpeas
dry and toss with the oil and paprika.

2. Roast for 25 minutes, shaking the pan
halfway, until deeply golden and crack-
ling.
3. Wilt the kale in the hot pan and serve.
112
`;

test('splits a cookbook page into parts', () => {
  const r = P.splitText(page);
  assert.equal(r.title, 'Crispy Chickpeas with Greens');
  assert.equal(r.yield, 'Serves 4');
  assert.equal(r.prep_time, '10');
  assert.equal(r.cook_time, '65');
  assert.equal(r.total_time, '75');
  assert.match(r.notes, /^This is the dinner .* nearly empty and everyone is hungry\.$/);
  assert.deepEqual(r.ingredients, [
    '2 cans (15 oz) chickpeas, drained',
    '3 Tbsp olive oil',
    '½ tsp smoked paprika',
    'For the greens:',
    '1 bunch kale, stems removed and finely chopped',
    'Kosher salt',
  ]);
  assert.deepEqual(r.directions, [
    'Heat the oven to 425°F. Pat the chickpeas dry and toss with the oil and paprika.',
    'Roast for 25 minutes, shaking the pan halfway, until deeply golden and crackling.',
    'Wilt the kale in the hot pan and serve.',
  ]);
});

test('uses explicit section headings', () => {
  const r = P.splitText(`Simple Vinaigrette
Ingredients
Olive oil
Red wine vinegar
Dijon mustard
Method
Shake everything together in a jar.
Season to taste.`);
  assert.equal(r.title, 'Simple Vinaigrette');
  assert.deepEqual(r.ingredients, ['Olive oil', 'Red wine vinegar', 'Dijon mustard']);
  assert.deepEqual(r.directions, ['Shake everything together in a jar. Season to taste.']);
});

test('empty or junk text gives an empty recipe, not an error', () => {
  const r = P.splitText('');
  assert.equal(r.title, '');
  assert.deepEqual(r.ingredients, []);
  assert.deepEqual(r.directions, []);
  assert.equal(P.splitText('  \n 12 \n').title, '');
});

test('minutesOf', () => {
  assert.equal(P.minutesOf('1 hr 15 min'), '75');
  assert.equal(P.minutesOf('1.5 hours'), '90');
  assert.equal(P.minutesOf('20 minutes'), '20');
  assert.equal(P.minutesOf('overnight'), '');
});

test('import ids pass the workflows\' check', () => {
  for (let i = 0; i < 50; i++) assert.match(P.newId(), /^[a-z0-9-]{6,40}$/);
});
