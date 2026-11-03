/* Recipe edit queue + one-commit sync (no GitHub Actions).

   The recipe editor saves changes to this device (localStorage). "Sync" then
   applies every queued edit to the latest recipe files on main and commits them
   all at once with the Git Data API, so any number of edits is one commit and
   one Pages rebuild.

   Pure functions (applyChanges etc.) live at the top so they can be unit-tested
   in Node (see tools/test_recipe_edits.mjs). Keep them in step with
   tools/update_recipe.py. */
(function (root) {
  var DIFFICULTIES = ['easy', 'medium', 'hard'];
  var SEASONS = ['all', 'spring', 'summer', 'fall', 'winter'];

  // kind: text | minutes | choice | bool | lines | seasons; second item = optional
  var FIELDS = {
    title: ['text', false],
    ingredients: ['lines', false],
    directions: ['lines', false],
    prep_time: ['minutes', true],
    cook_time: ['minutes', true],
    total_time: ['minutes', true],
    yield: ['text', true],
    difficulty: ['choice', true],
    kid_friendly: ['bool', false],
    season: ['seasons', false],
    tags: ['lines', true],
    category: ['text', true],
    cuisine: ['text', true]
  };

  /* ---- Validation (mirrors clean() in update_recipe.py) ---- */
  // Returns the cleaned value, or null to drop an optional key. Throws Error if invalid.
  function clean(key, kind, optional, value) {
    if (kind === 'bool') {
      if (typeof value !== 'boolean') throw new Error("'" + key + "' must be true or false");
      return value;
    }
    if (kind === 'lines' || kind === 'seasons') {
      if (typeof value === 'string') value = value.split(/\r?\n/);
      if (!Array.isArray(value) || !value.every(function (v) { return typeof v === 'string'; })) {
        throw new Error("'" + key + "' must be a list of text");
      }
      var items = value.map(function (v) { return v.trim(); }).filter(Boolean);
      if (kind === 'seasons') {
        var bad = items.filter(function (s) { return SEASONS.indexOf(s) === -1; });
        if (bad.length) throw new Error('unknown season(s) ' + bad.join(', '));
        return items.length ? items : ['all'];
      }
      if (!items.length) {
        if (optional) return null;
        throw new Error("'" + key + "' can't be empty");
      }
      return items;
    }
    if (typeof value !== 'string' && typeof value !== 'number') throw new Error("'" + key + "' must be text");
    var text = String(value).trim();
    if (!text) {
      if (optional) return null;
      throw new Error("'" + key + "' can't be empty");
    }
    if (kind === 'minutes') {
      if (!/^\d{1,4}$/.test(text)) throw new Error("'" + key + "' must be a whole number of minutes");
      return String(parseInt(text, 10));
    }
    if (kind === 'choice') {
      text = text.toLowerCase();
      if (DIFFICULTIES.indexOf(text) === -1) throw new Error("'" + key + "' must be one of " + DIFFICULTIES.join(', '));
    }
    return text;
  }

  /* ---- YAML output ----
     Only the edited keys are rewritten; everything else in the file is left
     byte-for-byte as it was. Strings are written plain when that is unambiguous
     YAML and single-quoted otherwise (same look as the existing files). */
  function needsQuote(s) {
    if (!s) return true;
    if (/^\s|\s$/.test(s)) return true;
    if (/^[-?:,\[\]{}#&*!|>'"%@`]/.test(s)) return true;
    if (/: |:$| #/.test(s)) return true;
    if (/^(true|false|yes|no|on|off|y|n|null|~)$/i.test(s)) return true;
    if (/^[\d.,_:+\-eExXoObBaAcCdDfF]+$/.test(s) && /^[-+.]?\d/.test(s)) return true; // numbers, times, hex
    if (/^\d{4}-\d{1,2}-\d{1,2}/.test(s)) return true;                              // dates
    return false;
  }

  function scalar(value) {
    var s = String(value).replace(/[\r\n\t]+/g, ' ').replace(/[\u0000-\u001f\u007f]/g, '');
    return needsQuote(s) ? "'" + s.replace(/'/g, "''") + "'" : s;
  }

  function block(key, kind, value) {
    if (kind === 'bool') return [key + ': ' + (value ? 'true' : 'false')];
    if (kind === 'lines' || kind === 'seasons') {
      return [key + ':'].concat(value.map(function (v) { return '- ' + scalar(v); }));
    }
    return [key + ': ' + scalar(value)];
  }

  var KEY_LINE = /^([A-Za-z_][\w-]*):(?:\s|$)/;

  /* Apply {field: value} changes to the text of a recipe file.
     Returns {text, changed}. Throws Error with a readable message if invalid. */
  function applyChanges(text, changes) {
    if (!changes || typeof changes !== 'object' || !Object.keys(changes).length) throw new Error('no changes given');
    var unknown = Object.keys(changes).filter(function (k) { return !FIELDS[k]; });
    if (unknown.length) throw new Error("can't edit field(s) " + unknown.join(', '));

    var m = /^---\n([\s\S]*?)\n---[ \t]*(?:\n|$)/.exec(text);
    if (!m) throw new Error('could not parse front matter');

    // Split the front matter into top-level key blocks (a key line plus its indented / "- " lines)
    var blocks = [];
    m[1].split('\n').forEach(function (line) {
      var k = KEY_LINE.exec(line);
      if (k || !blocks.length) blocks.push({ key: k ? k[1] : null, lines: [line] });
      else blocks[blocks.length - 1].lines.push(line);
    });

    Object.keys(changes).forEach(function (key) {
      var spec = FIELDS[key];
      var cleaned = clean(key, spec[0], spec[1], changes[key]);
      var at = -1;
      blocks.forEach(function (b, i) { if (b.key === key) at = i; });
      if (cleaned === null) {
        if (at !== -1) blocks.splice(at, 1);
      } else if (at !== -1) {
        // keep any trailing blank/comment lines that followed the old value
        blocks[at].lines = block(key, spec[0], cleaned);
      } else {
        blocks.push({ key: key, lines: block(key, spec[0], cleaned) });
      }
    });

    var fm = [].concat.apply([], blocks.map(function (b) { return b.lines; })).join('\n');
    if (fm === m[1]) return { text: text, changed: false };
    return { text: text.slice(0, 4) + fm + text.slice(4 + m[1].length), changed: true };
  }

  /* ---- Queue (localStorage) ---- */
  var KEY = 'mise_pending_edits';

  function readQueue() {
    try {
      var q = JSON.parse(localStorage.getItem(KEY) || '{}');
      return q && typeof q === 'object' ? q : {};
    } catch (e) { return {}; }
  }

  function writeQueue(q) {
    try {
      if (Object.keys(q).length) localStorage.setItem(KEY, JSON.stringify(q));
      else localStorage.removeItem(KEY);
    } catch (e) {}
    try { document.dispatchEvent(new CustomEvent('cd-edits-changed')); } catch (e) {}
  }

  function pendingFor(slug) { return readQueue()[slug] || {}; }
  function pendingCount() { return Object.keys(readQueue()).length; }

  // Later edits to the same field replace earlier ones
  function queueEdit(slug, changes) {
    var q = readQueue();
    var merged = {};
    [q[slug] || {}, changes].forEach(function (o) { Object.keys(o).forEach(function (k) { merged[k] = o[k]; }); });
    q[slug] = merged;
    writeQueue(q);
  }

  function discard(slug) {
    var q = readQueue();
    delete q[slug];
    writeQueue(q);
  }

  /* ---- Sync: every queued edit in one commit ---- */
  function bytesToText(b64) {
    var bin = atob(String(b64).replace(/\s/g, ''));
    return new TextDecoder().decode(Uint8Array.from(bin, function (c) { return c.charCodeAt(0); }));
  }

  async function sync(C) {
    var snapshot = readQueue();
    var slugs = Object.keys(snapshot);
    if (!slugs.length) return { committed: 0, failed: [] };

    var t = C.token();
    if (!t) throw new Error('No GitHub token — save one on the <a href="' + C.BASE + '/import/">Import page</a>');
    var BRANCH = C.BRANCH || 'main';
    var base = 'https://api.github.com/repos/' + C.REPO;
    var headers = { 'Authorization': 'token ' + t, 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json' };

    async function api(method, path, body) {
      var res = await fetch(base + path, { method: method, headers: headers, cache: 'no-store', body: body ? JSON.stringify(body) : undefined });
      var data = null;
      try { data = await res.json(); } catch (e) {}
      if (!res.ok) {
        // Say what GitHub actually answered and which step it was, so a permissions
        // problem can be told apart from a missing repo, a protected branch, etc.
        var step = method + ' ' + path.split('?')[0].replace(/_recipes\/.*/, '_recipes/…');
        var why = (data && data.message) || 'HTTP ' + res.status;
        var err = new Error(res.status === 401
          ? 'GitHub token was rejected — update it on the <a href="' + C.BASE + '/import/">Import page</a>'
          : 'GitHub said “' + C.escapeHtml(why) + '” (' + res.status + ') on ' + C.escapeHtml(step) +
            (res.status === 403 || res.status === 404 ? '. Check the token has <em>Contents: Read and write</em> and includes ' + C.REPO + '.' : ''));
        err.status = res.status;
        throw err;
      }
      return data;
    }

    for (var attempt = 0; attempt < 4; attempt++) {
      var head = (await api('GET', '/git/ref/heads/' + BRANCH)).object.sha;
      var files = [], done = [], failed = [];

      for (var i = 0; i < slugs.length; i++) {
        var slug = slugs[i];
        var path = '_recipes/' + slug + '.md';
        try {
          var file = await api('GET', '/contents/' + path.split('/').map(encodeURIComponent).join('/') + '?ref=' + head);
          var out = applyChanges(bytesToText(file.content), snapshot[slug]);
          if (out.changed) files.push({ path: path, mode: '100644', type: 'blob', content: out.text });
          done.push(slug);
        } catch (e) {
          if (e.status && e.status !== 404) throw e;
          failed.push({ slug: slug, error: e.status === 404 ? 'recipe file not found' : e.message });
        }
      }

      if (files.length) {
        var commit = await api('GET', '/git/commits/' + head);
        var tree = await api('POST', '/git/trees', { base_tree: commit.tree.sha, tree: files });
        var names = done.filter(function (s) { return files.some(function (f) { return f.path === '_recipes/' + s + '.md'; }); });
        var message = names.length === 1 ? 'Edit ' + names[0] : 'Edit ' + names.length + ' recipes\n\n' + names.join('\n');
        var created = await api('POST', '/git/commits', { message: message, tree: tree.sha, parents: [head] });
        try {
          await api('PATCH', '/git/refs/heads/' + BRANCH, { sha: created.sha });
        } catch (e) {
          if ((e.status === 422 || e.status === 409) && attempt < 3) continue; // main moved — redo on the new head
          throw e;
        }
      }

      // Drop what was synced, but keep any edit made while this was running
      var now = readQueue();
      done.forEach(function (s) {
        if (JSON.stringify(now[s]) === JSON.stringify(snapshot[s])) delete now[s];
      });
      writeQueue(now);
      return { committed: files.length, failed: failed };
    }
    throw new Error('Could not sync — main kept changing. Try again.');
  }

  var api = {
    FIELDS: FIELDS,
    applyChanges: applyChanges,
    pendingFor: pendingFor,
    pendingCount: pendingCount,
    queueEdit: queueEdit,
    discard: discard,
    sync: sync
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root && root.Chowdown) root.Chowdown.edits = api;
})(typeof window !== 'undefined' ? window : null);

/* ---- "Sync" pill: shown on every page while edits are waiting ---- */
(function () {
  if (typeof document === 'undefined' || !window.Chowdown || !window.Chowdown.edits) return;
  var C = window.Chowdown, E = C.edits, pill = null, busy = false;

  function label() {
    var n = E.pendingCount();
    return busy ? 'Syncing…' : '↑ Sync ' + n + ' edit' + (n === 1 ? '' : 's');
  }

  function render() {
    var n = E.pendingCount();
    if (!n && !busy) { if (pill) { pill.remove(); pill = null; } return; }
    if (!pill) {
      pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'bauhaus-btn cd-sync-pill';
      pill.style.cssText = 'position:fixed;right:16px;z-index:999;bottom:calc(var(--bottom-nav-h,0px) + 16px + env(safe-area-inset-bottom));';
      pill.addEventListener('click', run);
      document.body.appendChild(pill);
    }
    pill.disabled = busy;
    pill.textContent = label();
  }

  async function run() {
    if (busy) return;
    busy = true; render();
    try {
      var r = await E.sync(C);
      var msg = r.committed
        ? '✓ Synced ' + r.committed + ' recipe' + (r.committed === 1 ? '' : 's') + ' — the site rebuilds in about a minute.'
        : 'Nothing to change — already up to date.';
      if (r.failed.length) {
        msg += ' Couldn’t apply: ' + r.failed.map(function (f) { return C.escapeHtml(f.slug) + ' (' + C.escapeHtml(f.error) + ')'; }).join('; ');
      }
      C.toast(msg, r.failed.length ? 'err' : 'ok', r.failed.length ? 9000 : 6000);
    } catch (e) {
      C.toast(e.message || 'Sync failed', 'err', 8000);
    }
    busy = false; render();
  }

  document.addEventListener('cd-edits-changed', render);
  window.addEventListener('storage', render);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render); else render();
})();
