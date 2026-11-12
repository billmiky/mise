/*
 * Salad Maker: the bowl-building logic behind /salad-maker/, kept free of the DOM
 * so tools/test_salad_maker.mjs can test it.
 *
 * A bowl is { slotKey: [option names] } for every slot in _data/salads.yml.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SaladMaker = factory();
})(typeof self !== 'undefined' ? self : this, function () {

  function emptyBowl(slots) {
    var bowl = {};
    slots.forEach(function (s) { bowl[s.key] = []; });
    return bowl;
  }

  function copy(bowl) {
    var out = {};
    Object.keys(bowl).forEach(function (k) { out[k] = bowl[k].slice(); });
    return out;
  }

  function slotOf(slots, key) {
    for (var i = 0; i < slots.length; i++) if (slots[i].key === key) return slots[i];
    return null;
  }

  function sameName(a, b) { return String(a).trim().toLowerCase() === String(b).trim().toLowerCase(); }

  function indexOfName(list, name) {
    for (var i = 0; i < list.length; i++) if (sameName(list[i], name)) return i;
    return -1;
  }

  // Add or remove one option; a single-choice slot (the dressing) swaps instead
  function toggle(slots, bowl, key, name) {
    var slot = slotOf(slots, key);
    var out = copy(bowl);
    var list = out[key] || (out[key] = []);
    var i = indexOfName(list, name);
    if (i !== -1) list.splice(i, 1);
    else if (slot && slot.single) out[key] = [name];
    else list.push(name);
    return out;
  }

  function isEmpty(bowl) {
    return Object.keys(bowl).every(function (k) { return !bowl[k].length; });
  }

  function count(bowl) {
    return Object.keys(bowl).reduce(function (n, k) { return n + bowl[k].length; }, 0);
  }

  function randInt(rng, lo, hi) { return lo + Math.floor(rng() * (hi - lo + 1)); }

  // n distinct names from the slot's options, avoiding `avoid` when there's room
  function sample(options, n, rng, avoid) {
    var names = options.map(function (o) { return o.name; });
    var fresh = names.filter(function (x) { return indexOfName(avoid || [], x) === -1; });
    var pool = fresh.length >= n ? fresh : names;
    pool = pool.slice();
    var out = [];
    while (out.length < n && pool.length) out.push(pool.splice(Math.floor(rng() * pool.length), 1)[0]);
    return out;
  }

  // Random picks for one slot, within its [min, max]; tries not to repeat what's there now
  function rollSlot(slot, rng, current) {
    var pick = slot.pick || [1, 1];
    var n = slot.single ? 1 : randInt(rng, pick[0], pick[1]);
    return sample(slot.options || [], n, rng, current);
  }

  function surprise(slots, rng, current) {
    rng = rng || Math.random;
    var bowl = {};
    slots.forEach(function (s) { bowl[s.key] = rollSlot(s, rng, current && current[s.key]); });
    return bowl;
  }

  function reroll(slots, bowl, key, rng) {
    var out = copy(bowl);
    var slot = slotOf(slots, key);
    if (slot) out[key] = rollSlot(slot, rng || Math.random, bowl[key]);
    return out;
  }

  function findOption(slot, name) {
    var opts = (slot && slot.options) || [];
    for (var i = 0; i < opts.length; i++) if (sameName(opts[i].name, name)) return opts[i];
    return null;
  }

  // Recipes linked from the picked options: [{ name, recipe }]
  function linkedRecipes(slots, bowl) {
    var out = [];
    slots.forEach(function (s) {
      (bowl[s.key] || []).forEach(function (name) {
        var o = findOption(s, name);
        if (o && o.recipe) out.push({ name: o.name, recipe: o.recipe });
      });
    });
    return out;
  }

  /* What to shop for. Each option buys its `buy` list (default: its own name, lowercased).
     `have(text)` says whether the pantry already has something; those go in `have`.
     Duplicates (carrots from the veggies and the dressing) are listed once. */
  function groceryItems(slots, bowl, have) {
    var buy = [], got = [], seen = {};
    slots.forEach(function (s) {
      (bowl[s.key] || []).forEach(function (name) {
        var o = findOption(s, name);
        var items = (o && o.buy && o.buy.length) ? o.buy : [String(name).trim().toLowerCase()];
        items.forEach(function (text) {
          var k = text.toLowerCase();
          if (!text || seen[k]) return;
          seen[k] = true;
          (have && have(text) ? got : buy).push(text);
        });
      });
    });
    return { buy: buy, have: got };
  }

  // A name for an unnamed bowl: its dressing or protein and base, e.g. "Nuoc Cham Rice Vermicelli"
  function suggestName(bowl) {
    var lead = (bowl.dressing && bowl.dressing[0]) || (bowl.protein && bowl.protein[0]) || '';
    var base = (bowl.base && bowl.base[0]) || (bowl.leaves && bowl.leaves[0]) || '';
    var name = [lead, base].filter(Boolean).join(' & ');
    return name ? name + ' Salad' : 'My Salad';
  }

  /* ---- Saved salads (the `saved:` list in _data/salads.yml) ---- */

  function fromSaved(slots, entry) {
    var bowl = emptyBowl(slots);
    slots.forEach(function (s) {
      var v = entry && entry[s.key];
      if (typeof v === 'string') v = [v];
      bowl[s.key] = Array.isArray(v) ? v.map(String).filter(Boolean) : [];
    });
    return bowl;
  }

  function toSaved(slots, name, bowl) {
    var entry = { name: String(name).trim() };
    slots.forEach(function (s) { entry[s.key] = (bowl[s.key] || []).slice(); });
    return entry;
  }

  // Replace a salad with the same name (any case) or add it; returns a new list
  function upsert(saved, entry) {
    var list = (saved || []).slice();
    for (var i = 0; i < list.length; i++) {
      if (sameName(list[i].name, entry.name)) { list[i] = entry; return list; }
    }
    list.push(entry);
    return list;
  }

  function remove(saved, name) {
    return (saved || []).filter(function (e) { return !sameName(e.name, name); });
  }

  // Which saved salad (if any) the bowl matches exactly
  function matchSaved(slots, saved, bowl) {
    for (var i = 0; i < (saved || []).length; i++) {
      var b = fromSaved(slots, saved[i]);
      var same = slots.every(function (s) {
        var x = b[s.key], y = bowl[s.key] || [];
        return x.length === y.length && x.every(function (n) { return indexOfName(y, n) !== -1; });
      });
      if (same) return saved[i];
    }
    return null;
  }

  return {
    emptyBowl: emptyBowl, toggle: toggle, isEmpty: isEmpty, count: count,
    surprise: surprise, reroll: reroll, linkedRecipes: linkedRecipes, groceryItems: groceryItems,
    suggestName: suggestName, fromSaved: fromSaved, toSaved: toSaved, upsert: upsert, remove: remove,
    matchSaved: matchSaved
  };
});
