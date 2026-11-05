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

# Writing a Recipe

The recipes are stored in the collection "Recipes" (the folder /_recipes).

They are written in Markdown and contain a few special sections:

- The frontmatter, which contains:
 - Title, Image, and Layout (which is "recipe")
 - Ingredients (a list of things in the dish)
 - Directions (a list of steps for the dish)
- Body content (for intros, stories, written detail)

If you need help with Markdown, here's a [handy cheatsheet](https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet).

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

# Writing a component recipe

A component recipe is a special recipe made up of other recipes. To make a new component recipe:

- place your smaller, single recipes into the /_components folder
- make a new recipe like normal in the /_recipes folders
- in the frontmatter of this new recipe, include your recipes from the /_components folder (instead of the usual Ingredeints list)

You can an example on the Red Berry Tart recipe. 

- [example Markdown](https://raw.githubusercontent.com/clarklab/chowdown/gh-pages/_recipes/red-berry-tart.md)
- [example recipe page](http://chowdown.io/recipes/red-berry-tart.html)