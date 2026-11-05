/*
 * The recipe map at the top of the Recipes tab: every recipe placed on one plane.
 *
 *   x  character   -5 fresh, bright & light   ->  +5 rich, hearty & comforting
 *   y  effort      -5 quick & easy            ->  +5 slow & involved
 *
 * Nobody has to score 350 recipes by hand: each axis gets a raw score from what the recipe already
 * says (title, tags, ingredients, total time, difficulty, how many ingredients and steps), then the
 * raw scores are spread over the plane by rank, so the map fills out instead of piling up in the
 * middle. A recipe can pin itself with `matrix: {x: 2, y: -3}` in its front matter; pinned recipes
 * keep exactly that spot.
 *
 * Recipes come in this shape (built from the recipe cards in _layouts/home.html):
 *   {t: title, tg: [tags, lower case], g: ingredient text, n: ingredient count, s: step count,
 *    time: total minutes (0 = unknown), d: difficulty, m: [x, y] (optional pin)}
 * Tested by tools/test_recipe_matrix.mjs.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MiseMatrix = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  var LIMIT = 5;
  /* how far the rank-spread recipes may go from the centre; leaves room for pinned extremes */
  var SPREAD = 4.6;
  /* share of the final position that comes from rank (even spread) vs the raw score (true distance) */
  var RANK_WEIGHT = 0.65;

  /* [pattern, weight] on the title. Negative pulls left (fresh) / down (quick). */
  var RICH_TITLE = [
    [/salad|slaw|ceviche|crudo|poke|summer rolls?|spring rolls?|lettuce wraps?|gazpacho|cucumber/, -2],
    [/nuoc cham|dressing|vinaigrette|pickle|chutney|salsa|herb/, -1],
    [/\bbowls?\b|grain bowl|chilled|cold|fresh|lime|lemon|ginger|green/, -0.6],
    [/stir[- ]?fry|broccolini|greens|cauliflower|tofu/, -0.4],
    [/casserole|lasagna|mac(aroni)? (and|&|n) cheese|gratin|pot pie|biscuits|gravy|cobbler/, 2],
    [/\bpie\b|cake|brownie|blondie|cookie|bars?\b|fudge|mochi|pudding|muffin|bread|squares/, 1.6],
    [/cheesy|creamy|buttery|fried|fritter|crispy|smothered|loaded|stuffed/, 1.2],
    [/braise|stew|chili|meatball|mashed|short ribs?|pulled|roast|carbonara|alfredo|risotto|bake\b|baked/, 1],
    [/curry|laksa|coconut|peanut|sesame|noodles|dumplings?|congee|soup/, 0.3]
  ];
  /* [pattern, weight] on the ingredient text, counted once each. */
  var RICH_INGREDIENTS = [
    [/(?<!(peanut|almond|cashew|nut|seed|apple|sesame|cocoa|shea|sunflower) )butter(?!nut| beans?| lettuce|milk)/, 0.9],
    [/heavy cream|whipping cream|sour cream|cream cheese|cr[eè]me fra[iî]che|half[- ]and[- ]half|mascarpone/, 1.2],
    [/cheese|parmesan|parmigiano|cheddar|mozzarella|gruy[eè]re|ricotta|pecorino|gouda|monterey|velveeta/, 1],
    [/bacon|sausage|chorizo|pork belly|ground beef|ground pork|short rib|chuck|brisket|pancetta|prosciutto/, 1],
    [/coconut milk|coconut cream/, 0.6],
    [/chocolate|cocoa|brown sugar|powdered sugar|condensed milk|caramel|marshmallow/, 1],
    [/all[- ]purpose flour|\bflour\b|bisquick|baking powder|panko|breadcrumbs/, 0.5],
    [/potato|pasta|spaghetti|macaroni|penne|rigatoni|udon|ramen|gnocchi|tortellini/, 0.5],
    [/mayonnaise|\bmayo\b|egg yolk|whole milk|buttermilk/, 0.4],
    [/lime|lemon/, -0.7],
    [/cilantro|\bmint\b|basil|\bdill\b|parsley|thai basil|chives|shiso/, -0.8],
    [/cucumber|radish|lettuce|romaine|arugula|spinach|kale|cabbage|bok choy|snap peas|watercress|herbs/, -0.8],
    [/vinegar|fish sauce|rice wine|ponzu|yuzu/, -0.5],
    [/fresh ginger|ginger|scallion|green onion|shallot|chile|jalape|serrano|thai chil/, -0.3],
    [/shrimp|salmon|\bfish\b|cod|halibut|tuna|scallop|tofu|edamame/, -0.3],
    [/tomato|mango|avocado|cherry tomato|fennel|celery/, -0.3]
  ];
  var RICH_TAGS = {
    salad: -2, vegan: -0.7, vietnamese: -0.8, thai: -0.4, japanese: -0.3, korean: -0.1, sauce: -0.6,
    seafood: -0.3, fish: -0.3, shrimp: -0.2, beverage: -1, tofu: -0.3,
    dessert: 2, baking: 1.4, southern: 1.2, american: 0.4, curry: 0.5, pasta: 0.8, sandwich: 0.4,
    breakfast: 0.3, brunch: 0.5, snack: 0.3, italian: 0.3, beef: 0.8, pork: 0.6, 'slow cooker': 0.6
  };

  var EFFORT_TITLE = [
    [/\b\d+[- ]?min(ute)?s?\b/, -1.6],
    [/\b\d+[- ]ingredient/, -1.2],
    [/\b(easy|quick|simple|weeknight|lazy|no[- ]cook|no[- ]bake|sheet[- ]pan|one[- ]pot|one[- ]pan|1[- ]pan|skillet)\b/, -0.8],
    [/\b(homemade|from scratch|layer|lasagna|dumplings?|pie|braised?|roast|bread|laksa|pho|ramen|party)\b/, 0.8]
  ];
  var EFFORT_TAGS = {
    quick: -1.2, weeknight: -1, sauce: -0.8, salad: -0.4, 'sheet pan': -0.5, 'one-pot': -0.4,
    'air fryer': -0.4, 'instant pot': -0.3, snack: -0.3,
    baking: 0.5, grill: 0.3, 'slow cooker': 1, 'crowd pleaser': 0.5
  };
  var DIFFICULTY = { easy: 0, medium: 1.2, hard: 2.4 };

  /* course: drives the dot colour and the legend chips */
  var COURSES = [
    { id: 'main', name: 'Mains' },
    { id: 'side', name: 'Sides & salads' },
    { id: 'breakfast', name: 'Breakfast' },
    { id: 'dessert', name: 'Sweets' },
    { id: 'other', name: 'Snacks & sauces' }
  ];

  function clamp(v) { return Math.max(-LIMIT, Math.min(LIMIT, v)); }
  function lower(v) { return String(v == null ? '' : v).toLowerCase(); }
  function tagsOf(r) {
    var tg = r.tg || [];
    if (typeof tg === 'string') tg = tg.split(/[|,]/);
    return tg.map(function (t) { return lower(t).trim(); }).filter(Boolean);
  }

  function words(text, table) {
    var sum = 0;
    for (var i = 0; i < table.length; i++) if (table[i][0].test(text)) sum += table[i][1];
    return sum;
  }
  function tagSum(tags, table) {
    var sum = 0;
    tags.forEach(function (t) { if (table[t]) sum += table[t]; });
    return sum;
  }

  function course(r) {
    var tags = tagsOf(r);
    var has = function (t) { return tags.indexOf(t) !== -1; };
    if (has('dessert')) return 'dessert';
    if (has('breakfast') || has('brunch')) return 'breakfast';
    if (has('dinner') || has('lunch')) return 'main';
    if (has('side') || has('salad') || has('soup')) return 'side';
    return 'other';
  }

  /* raw scores for one recipe, before spreading */
  function score(r) {
    var title = lower(r.t), ing = lower(r.g), tags = tagsOf(r);

    var rx = words(title, RICH_TITLE) + words(ing, RICH_INGREDIENTS) + tagSum(tags, RICH_TAGS);

    var time = Number(r.time) || 0;
    var n = Number(r.n) || 0, s = Number(r.s) || 0;
    var ey = 0;
    if (time > 0) ey += Math.log(Math.min(time, 24 * 60) / 40) / Math.LN2 * 1.6;
    else ey += (n - 10) * 0.12 + (s - 5) * 0.15; /* no time given: lean harder on the recipe's size */
    ey += (n - 10) * 0.1 + (s - 5) * 0.18;
    ey += DIFFICULTY[lower(r.d)] || 0;
    ey += words(title, EFFORT_TITLE) + tagSum(tags, EFFORT_TAGS);

    return { x: rx, y: ey };
  }

  /* small stable offset so recipes with identical scores don't sit on top of each other */
  function jitter(text, salt) {
    var h = 2166136261 ^ salt;
    for (var i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return ((h >>> 0) / 4294967295 - 0.5) * 0.3;
  }

  /* spread raw values over [-SPREAD, SPREAD] by rank, blended with a squashed copy of the raw value */
  function spread(values, scale) {
    var order = values.map(function (v, i) { return i; }).sort(function (a, b) { return values[a] - values[b]; });
    var out = new Array(values.length), n = values.length;
    for (var r = 0; r < n;) {
      /* ties share their average rank */
      var end = r;
      while (end + 1 < n && values[order[end + 1]] === values[order[r]]) end++;
      var rank = n > 1 ? ((r + end) / 2) / (n - 1) : 0.5;
      for (var j = r; j <= end; j++) {
        var v = values[order[j]];
        out[order[j]] = RANK_WEIGHT * (rank * 2 - 1) * SPREAD + (1 - RANK_WEIGHT) * SPREAD * Math.tanh(v / scale);
      }
      r = end + 1;
    }
    return out;
  }

  function pinOf(r) {
    var m = r.m;
    if (!m) return null;
    var x = Array.isArray(m) ? m[0] : m.x, y = Array.isArray(m) ? m[1] : m.y;
    if (x == null || y == null || x === '' || y === '' || !isFinite(x) || !isFinite(y)) return null;
    return [clamp(Number(x)), clamp(Number(y))];
  }

  function round(v) { return Math.round(v * 100) / 100; }

  /* -> [{recipe, x, y, course, pinned}] in the same order as `recipes` */
  function layout(recipes) {
    var raw = recipes.map(score);
    var free = [];
    recipes.forEach(function (r, i) { if (!pinOf(r)) free.push(i); });
    var xs = spread(free.map(function (i) { return raw[i].x; }), 3);
    var ys = spread(free.map(function (i) { return raw[i].y; }), 3);
    var placed = {};
    free.forEach(function (i, k) {
      var t = String(recipes[i].t || i);
      placed[i] = [clamp(xs[k] + jitter(t, 1)), clamp(ys[k] + jitter(t, 2))];
    });
    return recipes.map(function (r, i) {
      var pin = pinOf(r);
      var p = pin || placed[i];
      return { recipe: r, x: round(p[0]), y: round(p[1]), course: course(r), pinned: !!pin };
    });
  }

  /* the n points closest to (x, y) */
  function nearest(points, x, y, n) {
    return points
      .map(function (p) { return { p: p, d: (p.x - x) * (p.x - x) + (p.y - y) * (p.y - y) }; })
      .sort(function (a, b) { return a.d - b.d; })
      .slice(0, n)
      .map(function (o) { return o.p; });
  }

  /* the four quadrants, each named after what tends to live there */
  var NEIGHBOURHOODS = [
    { id: 'market-day', name: 'Market Day', x: -2.5, y: 2.5,
      blurb: 'Fresh and worth the effort. Big salads, rolls, dumplings and dishes built around the produce.' },
    { id: 'sunday-supper', name: 'Sunday Supper', x: 2.5, y: 2.5,
      blurb: 'Rich and slow. Braises, bakes, roasts and pies for when there’s time to cook.' },
    { id: 'fast-fresh', name: 'Fast & Fresh', x: -2.5, y: -2.5,
      blurb: 'Bright and quick. Salads, slaws, stir-fries and noodle bowls for busy nights.' },
    { id: 'cozy-weeknight', name: 'Cozy Weeknight', x: 2.5, y: -2.5,
      blurb: 'Comfort without the wait. Curries, skillet pastas and cheesy things on a school night.' }
  ];

  function neighbourhood(x, y) {
    return NEIGHBOURHOODS[(x >= 0 ? 1 : 0) + (y >= 0 ? 0 : 2)];
  }

  return {
    LIMIT: LIMIT, NEIGHBOURHOODS: NEIGHBOURHOODS, COURSES: COURSES,
    score: score, layout: layout, nearest: nearest, neighbourhood: neighbourhood, course: course
  };
});
