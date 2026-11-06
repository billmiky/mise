/* Photo import helpers for the Import page ("From a photo").
   - splitText(): turns OCR'd cookbook text into title / ingredients / directions (no Claude key)
   - shrink() / crop(): resize photos in the browser before they're uploaded
   - Stage: put photos on the photo-imports branch and read the workflow's result back
   splitText is pure so it can be tested: node --test tools/test_photo_import.mjs */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MisePhoto = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* ---------------- OCR text → recipe ---------------- */

  var FRACTIONS = '½⅓⅔¼¾⅛⅜⅝⅞';
  var QTY_RE = new RegExp('^(?:[\\d' + FRACTIONS + ']|(?:a|an|one|two|three|four|six)\\s+(?:pinch|handful|few|dash|cups?|tablespoons?|teaspoons?|large|medium|small|bunch|can|clove)\\b|pinch\\b|dash\\b|salt\\b|freshly\\b|kosher\\b|juice of\\b|zest of\\b)', 'i');
  var UNIT_RE = /\b(cups?|tbsp|tsp|tablespoons?|teaspoons?|oz|ounces?|lbs?|pounds?|grams?|g|kg|ml|liters?|cloves?|sticks?|cans?|pinch|bunch|sprigs?)\b/i;
  var ING_HEAD_RE = /^(ingredients|you will need|what you need)\s*:?$/i;
  var DIR_HEAD_RE = /^(directions|method|instructions|preparation|to make|steps)\s*:?$/i;
  var YIELD_RE = /^(serves|makes|yield|yields|servings|portions)\b[:\s]*(.*)$/i;
  var TIME_RE = /\b(prep(?:aration)?|cook(?:ing)?|total|active|bake|baking)\s*(?:time)?\s*[:\-]?\s*((?:\d+(?:\.\d+)?\s*(?:hours?|hrs|hr|h|minutes?|mins|min|m)\b\.?\s*(?:and\s*)?)+)/gi;
  var STEP_NUM_RE = /^(?:step\s*)?(\d{1,2})[\.\):]\s+/i;
  var NUMBERED_STEP_RE = /^(?:step\s*)?\d{1,2}[\.\):]\s+[A-Z]/;

  function minutesOf(s) {
    var h = /(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hours?)\b/i.exec(s);
    var m = /(\d+)\s*(?:m|min|mins|minutes?)\b/i.exec(s);
    var total = (h ? Math.round(parseFloat(h[1]) * 60) : 0) + (m ? parseInt(m[1], 10) : 0);
    return total ? String(total) : '';
  }

  function titleCase(s) {
    if (s !== s.toUpperCase() || !/[A-Z]/.test(s)) return s;
    return s.toLowerCase().replace(/(^|[\s\-(])([a-z])/g, function (_, a, b) { return a + b.toUpperCase(); })
      .replace(/\b(And|Or|With|Of|The|A|In|On|For)\b/g, function (w, _, i) { return i ? w.toLowerCase() : w; });
  }

  function isIngredient(line) {
    if (QTY_RE.test(line)) return true;
    if (line.length <= 45 && !/[.!?]$/.test(line) && (UNIT_RE.test(line) || line.split(/\s+/).length <= 4)) return true;
    return false;
  }

  function isSubheading(line) {
    return /:$/.test(line) && line.length <= 40 && !DIR_HEAD_RE.test(line) && !ING_HEAD_RE.test(line);
  }

  // Lines OCR splits mid-sentence or mid-word get joined back together
  function joinWrapped(a, b) {
    if (/[A-Za-z]-$/.test(a) && /^[a-z]/.test(b)) return a.slice(0, -1) + b;
    return a + ' ' + b;
  }

  function splitText(text) {
    var out = { title: '', yield: '', prep_time: '', cook_time: '', total_time: '',
                ingredients: [], directions: [], notes: '' };
    var raw = String(text || '').replace(/\r/g, '').split('\n').map(function (l) {
      return l.replace(/[|•·▪●]/g, ' ').replace(/\s+/g, ' ').trim();
    });

    // Times and yield can sit anywhere, often on one line ("PREP 10 MIN  COOK 1 HR")
    var lines = [];
    raw.forEach(function (l) {
      var found = false, m;
      TIME_RE.lastIndex = 0;
      while ((m = TIME_RE.exec(l))) {
        var key = /^prep|^active/i.test(m[1]) ? 'prep_time' : /^total/i.test(m[1]) ? 'total_time' : 'cook_time';
        if (!out[key]) out[key] = minutesOf(m[2]);
        found = true;
      }
      var y = YIELD_RE.exec(l);
      if (y && l.length < 60) {
        if (!out.yield) out.yield = l.replace(TIME_RE, '').replace(/[^\w).%]+$/, '').replace(/\s+/g, ' ').trim();
        return;
      }
      if (found && l.replace(TIME_RE, '').replace(/[^A-Za-z]/g, '').length < 6) return;
      if (/^\d{1,3}$/.test(l)) return;                         // page numbers
      lines.push(l);
    });

    var i = 0;
    while (i < lines.length && (!lines[i] || lines[i].length < 3 || !/[A-Za-z]{3}/.test(lines[i]))) i++;
    if (i < lines.length) out.title = titleCase(lines[i++].replace(/^[^\w"“']+|[^\w)!?"”']+$/g, ''));

    var mode = 'intro', step = '', notes = [];
    function endStep() { if (step) out.directions.push(step); step = ''; }
    for (; i < lines.length; i++) {
      var l = lines[i];
      if (!l) { if (mode === 'directions') endStep(); continue; }
      if (ING_HEAD_RE.test(l)) { mode = 'ingredients'; continue; }
      if (DIR_HEAD_RE.test(l)) { mode = 'directions'; continue; }

      // "1. Heat the oven…" is a step, not 1 of something
      if (mode !== 'directions' && NUMBERED_STEP_RE.test(l)) mode = 'directions';

      if (mode === 'intro') {
        if (isIngredient(l) || isSubheading(l)) mode = 'ingredients';
        else { notes.push(l); continue; }
      }
      if (mode === 'ingredients') {
        // The wrapped end of the previous ingredient ("…stems removed and / finely chopped")
        var prev = out.ingredients[out.ingredients.length - 1];
        if (prev && l.length < 40 && (/(,|\band|\bor|\()$/.test(prev) || (/^[a-z(]/.test(l) && !QTY_RE.test(l)))) {
          out.ingredients[out.ingredients.length - 1] = joinWrapped(prev, l);
          continue;
        }
        if (isIngredient(l) || isSubheading(l)) { out.ingredients.push(l); continue; }
        mode = 'directions';
      }
      var n = STEP_NUM_RE.exec(l);
      if (n) { endStep(); l = l.slice(n[0].length); }
      else if (step && /[.!?]$/.test(step) && /^[A-Z]/.test(l) && step.length > 120) endStep();
      step = step ? joinWrapped(step, l) : l;
    }
    endStep();
    out.notes = notes.reduce(function (acc, l) { return acc ? joinWrapped(acc, l) : l; }, '');
    if (!out.total_time && out.prep_time && out.cook_time) {
      out.total_time = String(+out.prep_time + +out.cook_time);
    }
    return out;
  }

  /* ---------------- Images (browser only) ---------------- */

  async function openImage(file) {
    if (typeof createImageBitmap === 'function') {
      try { return await createImageBitmap(file, { imageOrientation: 'from-image' }); } catch (e) {}
    }
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error('Couldn’t open “' + (file.name || 'photo') + '” — try a JPEG or PNG (or a screenshot of it)'));
      };
      img.src = url;
    });
  }

  // Draw (a crop box of) an image into a JPEG no larger than maxEdge on its long side.
  // box is [left, top, right, bottom] as fractions of the width/height.
  async function toJpeg(source, maxEdge, box) {
    var img = source instanceof Blob ? await openImage(source) : source;
    var w = img.width, h = img.height;
    box = box || [0, 0, 1, 1];
    var sx = box[0] * w, sy = box[1] * h, sw = (box[2] - box[0]) * w, sh = (box[3] - box[1]) * h;
    var scale = Math.min(1, maxEdge / Math.max(sw, sh));
    var canvas = document.createElement('canvas');
    canvas.width = Math.round(sw * scale);
    canvas.height = Math.round(sh * scale);
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (b) { b ? resolve(b) : reject(new Error('Couldn’t process the photo')); }, 'image/jpeg', 0.85);
    });
  }

  /* ---------------- Staging branch (browser only) ---------------- */

  var STAGE = 'photo-imports';

  function newId() {
    var d = new Date();
    var rand = Math.random().toString(36).slice(2, 8).padEnd(6, '0');
    return String(d.getFullYear()) + String(d.getMonth() + 1).padStart(2, '0') +
      String(d.getDate()).padStart(2, '0') + '-' + rand;
  }

  function Stage(C) {
    var api = 'https://api.github.com/repos/' + C.REPO;
    function headers(json) {
      var t = C.token();
      if (!t) throw new Error('No GitHub token — save one above');
      var h = { 'Authorization': 'token ' + t, 'Accept': 'application/vnd.github.v3+json' };
      if (json) h['Content-Type'] = 'application/json';
      return h;
    }
    async function call(method, path, body) {
      var resp = await fetch(api + path, { method: method, headers: headers(!!body), cache: 'no-store',
        body: body ? JSON.stringify(body) : undefined });
      var data = null;
      try { data = await resp.json(); } catch (e) {}
      return { status: resp.status, ok: resp.ok, data: data };
    }
    function fail(r) {
      if (r.status === 401) return new Error('GitHub token was rejected — update it above');
      if (r.status === 403 || r.status === 404) return new Error('GitHub token can’t write to ' + C.REPO + ' — it needs Contents: write');
      return new Error((r.data && r.data.message) || ('HTTP ' + r.status));
    }

    // The staging branch has no history in common with main: it only ever holds import folders
    async function ensureBranch() {
      var r = await call('GET', '/git/ref/heads/' + STAGE);
      if (r.ok) return;
      if (r.status !== 404) throw fail(r);
      var tree = await call('POST', '/git/trees', { tree: [{ path: 'README.md', mode: '100644', type: 'blob',
        content: 'Scratch space for photo imports (import.html). Each folder is one import; it is removed once the recipe is saved. Safe to delete.\n' }] });
      if (!tree.ok) throw fail(tree);
      var commit = await call('POST', '/git/commits', { message: 'Start photo-imports scratch branch', tree: tree.data.sha, parents: [] });
      if (!commit.ok) throw fail(commit);
      var ref = await call('POST', '/git/refs', { ref: 'refs/heads/' + STAGE, sha: commit.data.sha });
      if (!ref.ok && ref.status !== 422) throw fail(ref);       // 422: someone else just made it
    }

    function base64(blob) {
      return new Promise(function (resolve, reject) {
        var fr = new FileReader();
        fr.onload = function () { resolve(String(fr.result).split(',')[1]); };
        fr.onerror = function () { reject(fr.error); };
        fr.readAsDataURL(blob);
      });
    }

    async function put(path, blob, message) {
      var content = await base64(blob);
      for (var attempt = 0; attempt < 4; attempt++) {
        var existing = await call('GET', '/contents/' + path + '?ref=' + STAGE);
        var body = { message: message, content: content, branch: STAGE };
        if (existing.ok && existing.data && existing.data.sha) body.sha = existing.data.sha;
        var r = await call('PUT', '/contents/' + path, body);
        if (r.ok) return;
        if (r.status !== 409 && r.status !== 422) throw fail(r);  // 409: branch moved under us
        await new Promise(function (res) { setTimeout(res, 800 + Math.random() * 1200); });
      }
      throw new Error('Couldn’t upload ' + path + ' — try again');
    }

    async function result(id) {
      var r = await call('GET', '/contents/' + id + '/result.json?ref=' + STAGE + '&t=' + Date.now());
      if (r.status === 404) return null;
      if (!r.ok) throw fail(r);
      var bytes = Uint8Array.from(atob(r.data.content.replace(/\n/g, '')), function (c) { return c.charCodeAt(0); });
      return JSON.parse(new TextDecoder().decode(bytes));
    }

    // The newest run of a workflow started after `since` (ms), or null
    async function latestRun(workflow, since) {
      var r = await call('GET', '/actions/workflows/' + workflow + '/runs?event=workflow_dispatch&per_page=5');
      if (!r.ok) return null;
      var runs = (r.data.workflow_runs || []).filter(function (run) { return new Date(run.created_at).getTime() >= since; });
      runs.sort(function (a, b) { return new Date(a.created_at) - new Date(b.created_at); });
      return runs[0] || null;
    }

    return { ensureBranch: ensureBranch, put: put, result: result, latestRun: latestRun };
  }

  return { splitText: splitText, minutesOf: minutesOf, openImage: openImage, toJpeg: toJpeg,
           newId: newId, Stage: Stage, STAGE: STAGE };
});
