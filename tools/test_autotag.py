#!/usr/bin/env python3
"""Checks for tools/autotag.py. Run: python3 tools/test_autotag.py

Most cases are mistakes the tagger actually made while it was being written.
"""
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autotag  # noqa: E402


def tags(title, ingredients, directions=("Cook it.",), **kw):
    return autotag.suggest(title, list(ingredients), list(directions), **kw)


FAILED = []


def check(name, condition):
    if not condition:
        FAILED.append(name)


# --- diet: never claim vegetarian/vegan when it isn't -----------------------
CHEESE = ["1 shallot", "2 tbsp white balsamic vinegar", "3 watermelon radishes", "2 oranges", "goat cheese to taste"]
t = tags("Radish & Goat Cheese Salad", CHEESE)
check("goat cheese is vegetarian but not vegan ('goat' is not 'oat')", "Vegetarian" in t and "Vegan" not in t)

t = tags("Fluke with Coconut Rice", ["1 medium red onion", "1 1/2 cups jasmine rice", "3/4 cup coconut cream",
                                     "four 6-ounce fluke fillets", "salt"])
check("fish the list doesn't know by name is still fish", "Vegetarian" not in t and "Fish" in t and "Seafood" in t)

t = tags("Peanut Chicken Bowls", ["2 chicken breasts", "1 sweet potato", "1/4 cup peanut butter"],
         cuisine="Poultry Cuisine,Vegetarian Diet Cuisine")
check("keyword spam in the source's cuisine field is not a diet claim", "Vegetarian" not in t and "Chicken" in t)

t = tags("Noodle Soup", ["8 oz noodles", "6 cups chicken stock", "2 carrots", "1 onion"])
check("chicken stock: not vegetarian, and not tagged Chicken just for the stock", "Vegetarian" not in t and "Chicken" not in t)

t = tags("Carrot Soup", ["2 lb carrots", "3 cups vegetable broth", "1 onion", "salt"])
check("vegetable broth is fine", "Vegetarian" in t and "Vegan" in t)

t = tags("Tofu Curry", ["1 block tofu", "2 tbsp red curry paste", "1 can coconut milk", "1 cup rice"])
check("curry paste can hide shrimp paste, so no inferred diet tag", "Vegetarian" not in t and "Curry" in t)

t = tags("Tofu Curry", ["1 block tofu", "2 tbsp red curry paste", "1 can coconut milk"], cuisine="Gluten-Free,Vegan")
check("an explicit vegan claim is believed", "Vegan" in t and "Vegetarian" in t and "Gluten-Free" in t)

t = tags("Chickpea Tuna Salad", ["1 can chickpeas", "3 tbsp vegan mayonnaise", "celery", "dill pickles"])
check("a 'tuna' in the title that the ingredients lack: leave the diet to a person", "Vegetarian" not in t)

t = tags("Brownies", ["1 cup butter", "2 eggs", "1 cup sugar", "1/2 cup flour", "cocoa powder"])
check("brownies are vegetarian, not vegan", "Vegetarian" in t and "Vegan" not in t)

t = tags("Marshmallow Treats", ["3 tbsp butter", "10 oz marshmallows", "6 cups crisp rice cereal"])
check("marshmallows contain gelatin", "Vegetarian" not in t)

t = tags("Peanut Noodles", ["8 oz spaghetti", "1/4 cup peanut butter", "2 tbsp soy sauce", "1 tbsp rice vinegar"])
check("peanut butter and eggplant-style words don't count as dairy/egg", "Vegan" in t)

check("gluten-free is never inferred", "Gluten-Free" not in tags("Rice Bowl", ["1 cup rice", "1 egg", "soy sauce"]))

# --- main ingredients ---------------------------------------------------------
t = tags("Pad See Ew", ["8 oz rice noodles", "3 tbsp fish sauce", "2 tbsp oyster sauce", "1 egg", "broccoli"])
check("fish/oyster sauce is a seasoning, not a Fish or Seafood recipe", not ({"Fish", "Seafood", "Shrimp"} & t))

t = tags("Lemon Cake", ["1 cup flour", "1 cup sugar", "2 eggs", "1 lemon"], ["Preheat the oven. Bake 40 minutes."])
check("cake is a dessert and baking, not dinner", {"Dessert", "Baking"} <= t and "Dinner" not in t)

t = tags("Chile-Crisp Shrimp and Green Beans", ["1 lb shrimp", "1 lb green beans", "2 tbsp chile crisp"])
check("'chile crisp' is not a crisp (dessert)", "Dessert" not in t and "Baking" not in t and "Shrimp" in t)

t = tags("Turkey Shepherd's Pie", ["1 lb ground turkey", "2 lb potatoes", "1 cup peas"])
check("shepherd's pie is not a dessert", "Dessert" not in t and "Turkey" in t)

t = tags("Aloo Tikki (Indian Potato Cakes with Green Chutney)", ["2 potatoes", "2 tsp curry powder", "1 tbsp vegan butter"])
check("potato cakes are not dessert/baking, and curry powder alone is not a curry",
      not ({"Dessert", "Baking", "Curry", "Sauce"} & t))

t = tags("Baked Tofu with Peanut Sauce and Rice", ["1 block tofu", "1/4 cup peanut butter", "1 cup rice"])
check("a dish 'with X Sauce' is not a sauce", "Sauce" not in t and "Tofu" in t and "Rice" in t)

check("a real sauce is", "Sauce" in tags("Miso-Ginger Dressing", ["1 tbsp miso", "1 tbsp ginger", "2 tbsp oil"]))

check("rice 'for serving' doesn't make a rice dish",
      "Rice" not in tags("Chickpea Stew", ["1 can chickpeas", "1 onion", "cooked rice, for serving"]))

check("pasta sauce is not pasta", "Pasta" not in tags("Meatballs", ["1 lb ground beef", "1 jar pasta sauce"]))
check("green beans are not Beans", "Beans" not in tags("Side", ["1 lb green beans", "garlic", "oil"]))
check("chickpeas are Beans", "Beans" in tags("Stew", ["2 cans chickpeas", "garlic", "oil"]))

# --- cooking style ------------------------------------------------------------
check("sheet pan only when it's the dish",
      "Sheet Pan" not in tags("Chocolate Chip Cookies", ["flour", "sugar", "butter"],
                              ["Line a sheet pan.", "Bake on the sheet pan."]))
check("sheet-pan dinner", "Sheet Pan" in tags("Sheet-Pan Salmon", ["1 lb salmon", "broccoli", "oil"]))
check("barbecue sauce is not grilling", "Grill" not in tags("BBQ Tacos", ["tortillas", "bbq sauce", "beans"],
                                                             ["Pour the bbq sauce.", "Add bbq sauce.", "More bbq."]))
check("instant pot", "Instant Pot" in tags("Instant Pot Chili", ["beans", "tomatoes", "onion"]))

# --- cuisine and meal type ----------------------------------------------------
check("a dish named in the title beats a mislabelled source",
      "Vietnamese" in tags("Instant Pot Chicken Pho", ["chicken", "rice noodles", "ginger"], cuisine="Thai")
      and "Thai" not in tags("Instant Pot Chicken Pho", ["chicken", "rice noodles", "ginger"], cuisine="Thai"))
check("a source listing 3+ cuisines is ignored",
      not ({"French", "Mexican", "Italian"} & tags("Basic Salad", ["lettuce", "oil", "salt"],
                                                  cuisine="American,French,Italian,Mediterranean,Mexican")))
check("gochujang + kimchi is Korean", "Korean" in tags("Fried Rice", ["2 tbsp gochujang", "1 cup kimchi", "2 cups rice"]))
check("one clue is not enough", "Korean" not in tags("Stew", ["1 tbsp gochujang", "beans", "onion"]))
check("existing cuisine blocks a second guess",
      "Korean" not in tags("Fried Rice", ["2 tbsp gochujang", "1 cup kimchi", "rice"], existing=["Japanese"]))

t = tags("Blueberry Muffins", ["flour", "blueberries", "sugar"],
         category="breakfast, brunch, dinner, easy, quick, snack, weeknight, dessert, side dish")
check("a category claiming every meal is ignored", "Dinner" not in t and "Breakfast" in t)
check("'dinner party' is not dinner", "Dinner" not in tags("Cake", ["flour", "sugar", "eggs"], category="dinner party,dessert"))
check("'stuffing and dressing' is not a sauce", "Sauce" not in tags("Sticky Rice", ["rice", "ginger", "mushrooms"],
                                                                    category="Dinner, Stuffing and Dressing"))

# --- merging ------------------------------------------------------------------
check("existing tags are kept and tidied",
      autotag.merge(["soup", "Crowd Pleaser", "sides", "Side Dish"], {"Dinner"}) == ["Dinner", "Side", "Soup", "Crowd Pleaser"]
      or set(autotag.merge(["soup", "Crowd Pleaser", "sides", "Side Dish"], {"Dinner"})) == {"Dinner", "Side", "Soup", "Crowd Pleaser"})
check("string-typed tags are split", autotag.normalise_existing("side-dish chinese dairy-free vegan")
      == ["Side", "Chinese", "Dairy-Free", "Vegan"])
check("meal, cuisine, ingredient, diet, style order",
      autotag.order_tags({"Instant Pot", "Vegan", "Tofu", "Thai", "Dinner"}) == ["Dinner", "Thai", "Tofu", "Vegan", "Instant Pot"])

# --- rewriting a file ---------------------------------------------------------
RECIPE = """---
layout: recipe
title: "Sheet-Pan Salmon"
image: salmon.jpg
tags: [dinner, Crowd Pleaser]
ingredients:
- 1 lb salmon
- 1 head broccoli
- 2 tbsp olive oil
directions:
- Roast.
rating: 5
---

A note, with ---dashes--- and a tags: line.
"""
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "salmon.md"
    path.write_text(RECIPE)
    autotag.retag_file(path, write=True)
    out = path.read_text()
    fm = yaml.safe_load(autotag.FRONT.match(out).group(1))
    before = yaml.safe_load(autotag.FRONT.match(RECIPE).group(1))
    check("only the tags changed", {k: v for k, v in fm.items() if k != "tags"} == {k: v for k, v in before.items() if k != "tags"})
    check("existing tag kept, new ones added", {"Dinner", "Crowd Pleaser", "Fish", "Seafood", "Sheet Pan"} <= set(fm["tags"]))
    check("body untouched", out.endswith("A note, with ---dashes--- and a tags: line.\n"))
    autotag.retag_file(path, write=True)
    check("running it twice changes nothing more", path.read_text() == out)

if FAILED:
    print("FAILED:\n  " + "\n  ".join(FAILED))
    sys.exit(1)
print("OK: autotag checks")
