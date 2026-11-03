// Run: node --test tools/test_recipe_edits.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const { applyChanges } = createRequire(import.meta.url)('../assets/js/recipe-edits.js');

const SAMPLE = `---
layout: recipe
title: Soup
tags:
- Soup
- Easy
ingredients:
- 1 onion
directions:
- Cook it.
date_added: 2026-11-02
season:
- all
rating: null
kid_friendly: false
yield: 4 servings
---
Body text stays.
`;

test('only edited keys change; everything else is byte-identical', () => {
  const { text, changed } = applyChanges(SAMPLE, { title: 'Better Soup', kid_friendly: true });
  assert.ok(changed);
  assert.equal(text, SAMPLE.replace('title: Soup', 'title: Better Soup').replace('kid_friendly: false', 'kid_friendly: true'));
});

test('lists are rewritten and quoted when needed', () => {
  const { text } = applyChanges(SAMPLE, { ingredients: ['2 onions', '1 cup herbs: basil, dill', '10'] });
  assert.match(text, /ingredients:\n- 2 onions\n- '1 cup herbs: basil, dill'\n- '10'\ndirections:/);
});

test('optional fields are added, and removed when empty', () => {
  let r = applyChanges(SAMPLE, { prep_time: '15', cuisine: 'Thai' });
  assert.match(r.text, /yield: 4 servings\nprep_time: '15'\ncuisine: Thai\n---/);
  r = applyChanges(SAMPLE, { yield: '', tags: [] });
  assert.doesNotMatch(r.text, /yield|tags|Easy/);
});

test('no-op edit reports unchanged', () => {
  assert.equal(applyChanges(SAMPLE, { title: 'Soup' }).changed, false);
});

test('rejects bad input', () => {
  assert.throws(() => applyChanges(SAMPLE, { title: '  ' }), /can't be empty/);
  assert.throws(() => applyChanges(SAMPLE, { prep_time: '12 min' }), /whole number/);
  assert.throws(() => applyChanges(SAMPLE, { difficulty: 'wild' }), /one of/);
  assert.throws(() => applyChanges(SAMPLE, { season: ['monsoon'] }), /unknown season/);
  assert.throws(() => applyChanges(SAMPLE, { rating: 5 }), /can't edit/);
  assert.throws(() => applyChanges('no front matter', { title: 'x' }), /front matter/);
});

// ---- sync against a fake GitHub (Git Data API) ----
const store = {};
globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const E = createRequire(import.meta.url)('../assets/js/recipe-edits.js');
const C = { REPO: 'o/r', BRANCH: 'main', BASE: '', token: () => 't', escapeHtml: (s) => String(s) };

function fakeGitHub({ moveOnce = false } = {}) {
  const files = { '_recipes/a.md': SAMPLE, '_recipes/b.md': SAMPLE.replace('Soup', 'Stew') };
  const gh = { head: 'c1', commits: [], moved: false, log: [] };
  globalThis.fetch = async (url, opts = {}) => {
    const path = url.replace('https://api.github.com/repos/o/r', '');
    const method = opts.method || 'GET';
    const body = opts.body ? JSON.parse(opts.body) : null;
    const ok = (data) => ({ ok: true, status: 200, json: async () => data });
    const fail = (status, message) => ({ ok: false, status, json: async () => ({ message }) });
    gh.log.push(method + ' ' + path.split('?')[0]);
    if (path === '/git/ref/heads/main') return ok({ object: { sha: gh.head } });
    if (path.startsWith('/contents/')) {
      const name = decodeURIComponent(path.slice('/contents/'.length).split('?')[0]);
      return files[name] ? ok({ content: Buffer.from(files[name]).toString('base64') }) : fail(404, 'Not Found');
    }
    if (path.startsWith('/git/commits/')) return ok({ tree: { sha: 't-' + gh.head } });
    if (path === '/git/trees') { gh.tree = body.tree; return ok({ sha: 'tree-new' }); }
    if (path === '/git/commits') { gh.commits.push(body); return ok({ sha: 'c-' + gh.commits.length }); }
    if (method === 'PATCH') {
      if (moveOnce && !gh.moved) { gh.moved = true; gh.head = 'c-other'; return fail(422, 'Update is not a fast forward'); }
      gh.head = body.sha; return ok({});
    }
    throw new Error('unexpected ' + method + ' ' + path);
  };
  return gh;
}

test('sync commits every queued recipe once and clears the queue', async () => {
  const gh = fakeGitHub();
  E.queueEdit('a', { title: 'A2' });
  E.queueEdit('a', { kid_friendly: true });
  E.queueEdit('b', { yield: '8 servings' });
  assert.equal(E.pendingCount(), 2);
  const r = await E.sync(C);
  assert.equal(r.committed, 2);
  assert.equal(gh.commits.length, 1);
  assert.deepEqual(gh.tree.map((f) => f.path), ['_recipes/a.md', '_recipes/b.md']);
  assert.match(gh.tree[0].content, /title: A2/);
  assert.match(gh.tree[0].content, /kid_friendly: true/);
  assert.equal(E.pendingCount(), 0);
});

test('sync retries on a non-fast-forward and keeps unusable edits queued', async () => {
  const gh = fakeGitHub({ moveOnce: true });
  E.queueEdit('a', { title: 'A3' });
  E.queueEdit('ghost', { title: 'Nope' });
  const r = await E.sync(C);
  assert.equal(r.committed, 1);
  assert.equal(gh.commits.length, 2);                 // first attempt rejected, second landed
  assert.equal(gh.commits[1].parents[0], 'c-other');  // rebuilt on the new head
  assert.deepEqual(r.failed.map((f) => f.slug), ['ghost']);
  assert.deepEqual(Object.keys(JSON.parse(store.mise_pending_edits)), ['ghost']);
});
