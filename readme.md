# Mise

Our family's recipes, weekly meal plan, grocery list and pantry, in one site:
[billmiky.github.io/mise](https://billmiky.github.io/mise/)

Started as a fork of [Chowdown](https://github.com/clarklab/chowdown), a plaintext recipe database for hackers.

# Getting Started

This is a Jekyll build. Make sure you have Jekyll [installed](https://jekyllrb.com/). To install, run this command in the terminal (or iTerm, etc):

```gem install bundler jekyll```

or to check if you've got it installed already:

```jekyll -v```

Clone or download this repo. Navigate to the folder in terminal (or iTerm, etc), and then run:

```jekyll serve```

With default settings, you should be able to view the site locally at `http://127.0.0.1:4000/`

# Deploying

The site is built and published by `.github/workflows/deploy.yml` (in the repo's Settings → Pages, set **Source** to **GitHub Actions**). It runs on every push to `main`, and also after the site's own workflows (imports, plan, grocery, pantry...) save something. Those workflows push with the built-in token, which can't start another workflow, so `deploy.yml` lists them under `workflow_run`. If you add a workflow that pushes to `main`, add its name there too; `tools/check_deploy_triggers.py` fails the checks if you forget.

# Writing a Recipe

The recipes are stored in the collection "Recipes" (the folder /_recipes).

They are written in Markdown and contain a few special sections:

- The frontmatter, which contains:
 - Title, Image, and Layout (which is "recipe")
 - Ingredients (a list of things in the dish)
 - Directions (a list of steps for the dish)
- Body content (for intros, stories, written detail)

If you need help with Markdown, here's a [handy cheatsheet](https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet).

# Cookbook recipes

For a recipe from a book, add these to its front matter (or fill in **Cookbook** in the recipe's Edit form):

```yaml
cookbook: Salt Fat Acid Heat
cookbook_author: Samin Nosrat
cookbook_page: 112
```

The recipe page then shows a **From the cookbook** card with the title, author and page. When more than one recipe shares the same `cookbook`, the card links to `/recipes/?book=…`, which lists just that book's recipes. Book titles and authors are searchable from the Recipes tab too. The edit form and the photo importer suggest books you've already used, so the spelling stays the same. `source:` stays for websites (shown as a link) and other credits like a magazine.

# Importing from a cookbook photo

The Import page has a **From a photo** tab: choose (or take, or paste) up to 4 photos or screenshots of a recipe, in page order, then:

- **Read with Claude**: the photos go to the `photo-imports` scratch branch and the `photo-extract.yml` workflow sends them to Claude, which transcribes the title, ingredients, steps, times, yield and the book/page, and finds the photo of the finished dish. It needs an `ANTHROPIC_API_KEY` secret (repo Settings → Secrets and variables → Actions); each recipe costs roughly 1–3¢.
- **Read on this device**: free, with no key. Tesseract.js reads the text in the browser and `assets/js/photo-import.js` guesses which lines are ingredients and which are steps. It's rougher, so expect to tidy the lines. If no key is set up, *Read with Claude* switches to this on its own.

Either way you review everything in a form (including the book title, author and page, which Claude reads from the page headers when it can; *Same book* re-fills the last one for a batch from one book) and pick the recipe picture: the cropped dish photo, a whole page, or a photo of your own) before **Save Recipe** runs `photo-save.yml`, which writes `_recipes/<slug>.md` and `images/<slug>.jpg` to main (auto-tagged like URL imports) and clears the scratch folder. The `photo-imports` branch never deploys and is safe to delete.

# Typing a recipe in

The Import page's **Type it in** tab opens the same review form blank, for sites the link importer can't read or anything else you want to add by hand: title, ingredients (one per line), steps (a blank line between them), times, a dish photo you choose or take, and optionally a link or credit under **Source**, plus the cookbook fields. It saves through the same `photo-save.yml` workflow, so the recipe is auto-tagged and checked like the others, and the form stays open and blank for the next one.

Tests: `python3 tools/test_photo_import.py` and `node --test tools/test_photo_import.mjs`.

# Tags

Tags make recipes findable (the home page search matches them, and each tag on a recipe page links to that search). `tools/autotag.py` suggests them from a recipe's title, ingredients and directions: meal type (Dinner, Dessert...), cuisine, main ingredient (Chicken, Seafood, Beans, Pasta...), diet (Vegetarian, Vegan) and cooking style (Instant Pot, Sheet Pan...).

```
python3 tools/autotag.py            # dry run: what would change
python3 tools/autotag.py --diff     # ...and the tags each recipe would gain
python3 tools/autotag.py --write    # apply it
```

It only ever adds tags and keeps yours, and the importer runs it for new recipes. Vegetarian/Vegan are only added when nothing in the ingredient list is doubtful, and Gluten-Free is never guessed, only copied when a recipe says so. These come from ingredient text, so check the list if it matters.

# Recipe map

The top of the Recipes tab is a map with every recipe on one plane: left to right from fresh, bright & light to rich, hearty & comforting, bottom to top from quick & easy to slow & involved. The four quadrants are Market Day (fresh, worth the effort), Sunday Supper (rich and slow), Fast & Fresh and Cozy Weeknight. Tap the map, drag the pin or pick a quadrant to list the closest recipes; the course chips (mains, sides & salads, breakfast, sweets, snacks & sauces) hide or show a course, and the search box and filter chips narrow the map too. **Hide map** folds it away and the page remembers that.

Spots are worked out in the browser by `assets/js/recipe-matrix.js` from the title, tags, ingredients, total time, difficulty and the number of ingredients and steps (tested by `node --test tools/test_recipe_matrix.mjs`). If a recipe lands somewhere wrong, pin it in its front matter with `matrix: {x: 2.5, y: -3}` (each from -5 to 5); `tools/validate_recipes.py` checks the value.

# Salad Maker

The **Salads** tab (`/salad-maker/`) builds a grain-bowl salad one layer at a time: **Base**, **Light Leaves**, **Veggies**, **Protein**, **Crunch** and **Dressing**. Tap chips to fill the bowl, type your own into any slot, press ↻ to reshuffle one layer, or **Surprise Me** for a whole bowl. Your bowl is kept on the device until you start over.

- **Save Salad** names the bowl and adds it to **Saved Salads** (tap one to load it). Saving a name that already exists asks before replacing it.
- **Add to Grocery List** puts what the bowl needs in a **Salad** section of the grocery list (a rebuild keeps it). Anything the pantry already has goes under *on hand*; a teal dot on a chip means you have it.
- Dressings and crunches that are recipes in Mise (Nuoc Cham, Bibimbap sauce, Fried Shallots, Japanese Carrot Ginger…) link to them from the bowl.

Everything lives in `_data/salads.yml`: the slots and their options (with an optional `recipe:` slug to link and `buy:` list for the grocery list), and the saved salads, which started from the Notion *Salad Planner*. Edit it by hand to add or rename options. Saving and grocery adds use the same GitHub token as the rest of the site.

Tests: `python3 tools/test_salads.py` (checks the data file) and `node --test tools/test_salad_maker.mjs`.

# Writing a component recipe

A component recipe is a special recipe made up of other recipes. To make a new component recipe:

- place your smaller, single recipes into the /_components folder
- make a new recipe like normal in the /_recipes folders
- in the frontmatter of this new recipe, include your recipes from the /_components folder (instead of the usual Ingredeints list)

You can an example on the Red Berry Tart recipe. 

- [example Markdown](https://raw.githubusercontent.com/clarklab/chowdown/gh-pages/_recipes/red-berry-tart.md)
- [example recipe page](http://chowdown.io/recipes/red-berry-tart.html)