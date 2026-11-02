#!/usr/bin/env python3
"""Suggest consistent tags for recipes from their title, ingredients and directions.

The home-page search already matches a recipe's title and ingredients, so tags
are aimed at what plain text search can't find: meal type, cuisine, diet,
broad ingredient groups (Seafood, Pasta, Beans...) and cooking style
(Instant Pot, Sheet Pan...). Rules are deterministic: no network, no model.

Existing tags are always kept (only their capitalisation is tidied); this only
ever adds tags.

    python3 tools/autotag.py                  # dry run: summary of what would change
    python3 tools/autotag.py --diff           # ...and the tags added to each recipe
    python3 tools/autotag.py --write          # apply to _recipes/*.md
    python3 tools/autotag.py --write apple-squares.md   # just some recipes

Diet tags are inferred from the ingredient text, which cannot see hidden
ingredients, so Vegetarian/Vegan are only added when there is nothing
doubtful in the list. Gluten-Free is never inferred, only copied when the
recipe or its source says so.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Display order on the recipe page: meal, cuisine, main ingredient, diet, style.
MEAL = ["Breakfast", "Brunch", "Lunch", "Dinner", "Side", "Snack", "Dessert", "Beverage", "Soup", "Salad", "Sauce"]
MAIN = ["Chicken", "Beef", "Pork", "Turkey", "Lamb", "Fish", "Shrimp", "Seafood", "Tofu", "Eggs",
        "Beans", "Lentils", "Pasta", "Noodles", "Rice", "Grains"]
DIET = ["Vegetarian", "Vegan", "Gluten-Free"]
STYLE = ["Baking", "Curry", "Sandwich", "One-Pot", "Sheet Pan", "Instant Pot", "Slow Cooker", "Air Fryer", "Grill"]

CUISINES = {
    "american": "American", "southern": "Southern", "mexican": "Mexican", "italian": "Italian", "french": "French",
    "greek": "Greek", "mediterranean": "Mediterranean", "spanish": "Spanish", "peruvian": "Peruvian",
    "middle eastern": "Middle Eastern", "lebanese": "Middle Eastern", "turkish": "Middle Eastern",
    "persian": "Middle Eastern", "israeli": "Middle Eastern", "moroccan": "Moroccan", "ethiopian": "Ethiopian",
    "indian": "Indian", "sri lankan": "Sri Lankan", "chinese": "Chinese", "taiwanese": "Taiwanese",
    "japanese": "Japanese", "korean": "Korean", "thai": "Thai", "vietnamese": "Vietnamese",
    "malaysian": "Malaysian", "indonesian": "Indonesian", "burmese": "Burmese", "filipino": "Filipino",
    "hawaiian": "Hawaiian", "caribbean": "Caribbean", "haitian": "Haitian", "asian": "Asian", "asia": "Asian",
    "north american": "American",
}
CUISINE_ORDER = sorted(set(CUISINES.values()))

# Tags people already use, mapped to the one spelling we keep.
SYNONYMS = {
    "side dish": "Side", "side dishes": "Side", "sides": "Side", "side-dish": "Side",
    "mains": "Dinner", "main": "Dinner", "main course": "Dinner", "entree": "Dinner",
    "desserts": "Dessert", "soups": "Soup", "salads": "Salad", "sauces": "Sauce", "snacks": "Snack",
    "gluten free": "Gluten-Free", "glutenfree": "Gluten-Free", "one pot": "One-Pot", "one-pot": "One-Pot",
    "sheet-pan": "Sheet Pan", "sheet pan": "Sheet Pan", "instapot": "Instant Pot", "crockpot": "Slow Cooker",
    "stir fry": "Stir-Fry", "kid friendly": "Kid Friendly", "kid-friendly": "Kid Friendly",
}
CANONICAL = {t.lower(): t for t in MEAL + MAIN + DIET + STYLE + CUISINE_ORDER}


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

def fold(text) -> str:
    """Lower-case and strip accents so 'jalapeño' and 'bánh mì' match plain patterns."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return text.lower().replace("’", "'")


def rx(pattern: str, plural: bool = True) -> re.Pattern:
    return re.compile(r"\b(?:%s)%s\b" % (pattern, r"(?:e?s)?" if plural else ""))


# Phrases that look like an animal product but aren't (or say so outright).
SAFE = re.compile(r"""
    \b(?:
    (?:peanut|almond|cashew|nut|seed|sunflower|cocoa|shea|apple|sesame)\s+butter
  | butternut | butter\s+(?:beans?|lettuce|leaf|leaves) | cream\s+of\s+tartar
  | (?:coconut|cashew|oat|almond|soy|soya|rice|hemp|plant|nut|flax|macadamia)\s*
        (?:milk|cream|yogh?urt|cheese|butter|mayo|mayonnaise|creamer|whipped\s+cream)
  | (?:non-?dairy|dairy-?free|vegan|vegetarian|plant-based|meatless|imitation|faux|mock)\s+\w+(?:\s+\w+)?
  | egg(?:plant|-?free) | (?:flax|chia)\s+eggs? | egg\s+(?:replacer|substitute)
  | oyster\s+mushrooms?
  | (?:vegetable|veggie|mushroom|miso|kombu)\s+(?:stock|broth|bouillon|base)
  | coconut\s+meat
    )
""", re.X)

FLESH = rx(
    r"chicken|beef|pork|turkey|lamb|mutton|veal|duck|goose|venison|bison|rabbit|steak|brisket|short\s+rib|"
    r"ham|bacon|prosciutto|pancetta|guanciale|chorizo|sausage|salami|pepperoni|meatball|meatloaf|hot\s+dog|"
    r"kielbasa|pastrami|oxtail|drumstick|"
    r"fish|salmon|tuna|cod|halibut|tilapia|trout|mackerel|sardine|anchov(?:y|ie)|snapper|haddock|sea\s+bass|"
    r"swordfish|mahi|catfish|herring|eel|bonito|katsuobushi|roe|caviar|"
    r"shrimp|prawn|crab|lobster|scallop|clam|mussel|oyster|squid|calamari|octopus|crawfish|"
    r"fluke|flounder|sole|grouper|monkfish|pollock|perch|arctic\s+char|whitefish|hake|yellowtail|hamachi|"
    r"branzino|barramundi|pompano|bream|carp|pike|smelt|turbot|lox|ahi|unagi|surimi|shellfish|seafood|"
    r"fillets?|filets?|meat|poultry|liver|foie|jerky|chuck|sirloin|ribeye|flank|carnitas|bulgogi|galbi|kalbi|"
    r"tripe|offal|gizzard|spare\s+ribs|baby\s+back|"
    r"worcestershire|gelatin|marshmallow|lard|suet|tallow|schmaltz|aspic|jell-?o|gumm(?:y|ies)|bone\s+broth"
)
# Can't tell if these are animal-free from the name alone.
DOUBTFUL = rx(r"stock|broth|bouillon|(?:hon)?dashi|curry\s+paste|kimchi|caesar|xo\s+sauce|demi-?glace")
DAIRY_EGG = rx(
    r"milk|buttermilk|butter|cream|cheese|yogh?urt|ghee|eggs?|honey|mayo|mayonnaise|whey|casein|custard|"
    r"ricotta|paneer|feta|parmesan|parmigiano|pecorino|mozzarella|cheddar|gruyere|mascarpone|halloumi|"
    r"cotija|queso|half(?:-|\s+)and(?:-|\s+)half|creme\s+fraiche|kefir|pesto|naan|white\s+chocolate|"
    r"milk\s+chocolate|chocolate\s+chips?|chocolate\s+chunks?|semi-?sweet|bittersweet",
    plural=False,
)

PROTEIN = {
    "Chicken": rx(r"chicken"),
    "Beef": rx(r"beef|steak|brisket|short\s+rib|sirloin|ribeye|flank"),
    "Pork": rx(r"pork"),
    "Turkey": rx(r"turkey"),
    "Lamb": rx(r"lamb|mutton"),
    "Fish": rx(r"fish|salmon|tuna|cod|halibut|tilapia|trout|mackerel|sardine|snapper|haddock|sea\s+bass|"
               r"swordfish|mahi|catfish|fluke|flounder|sole|grouper|monkfish|pollock|perch|arctic\s+char|"
               r"whitefish|hake|yellowtail|hamachi|branzino|barramundi|pompano|bream|turbot|lox|ahi|unagi"),
    "Shrimp": rx(r"shrimp|prawn"),
    "Tofu": rx(r"tofu"),
}
TITLE_ONLY_PORK = rx(r"ham|bacon|prosciutto|pancetta|chorizo|sausage|carnitas")
OTHER_SHELLFISH = rx(r"crab|lobster|scallop|clam|mussel|oyster|squid|calamari|octopus|crawfish")
BROTH_LINE = rx(r"stock|broth|bouillon|base")
SEASONING = rx(r"fish\s+(?:sauce|stock|flakes?)|bonito|anchov(?:y|ie)|oyster\s+sauce|shrimp\s+paste|dried\s+shrimp|"
               r"worcestershire", plural=False)

BEANS = rx(r"beans?|chickpea|garbanzo|edamame|hummus|falafel|chana")
NOT_BEANS = rx(r"green\s+beans?|string\s+beans?|vanilla\s+beans?|coffee\s+beans?|cocoa\s+beans?|bean\s+sprouts?|"
               r"jelly\s+beans?|beans?\s+sprouts?|jelly\s*bean|bean\s+thread|snap\s+beans?|runner\s+beans?")
LENTILS = rx(r"lentil|dal|dhal|dahl")
PASTA = rx(r"pasta|spaghetti|linguine|fettuccine|penne|rigatoni|orzo|macaroni|lasagn[ae]|orecchiette|farfalle|"
           r"tagliatelle|ziti|rotini|gnocchi|ravioli|tortellini|capellini|fusilli|cavatappi|pappardelle")
NOODLES = rx(r"noodle|ramen|udon|soba|vermicelli|lo\s+mein|chow\s+mein|pad\s+thai|somen|laksa|japchae")
RICE = rx(r"rice|risotto|congee|bibimbap|biryani|pilaf|sushi|onigiri|paella|jollof")
NOT_RICE = rx(r"rice\s+(?:vinegar|wine|flour|paper|milk|syrup|bran|cakes?|cereal|krispies|noodles?|sticks?)|"
              r"crisp(?:y)?\s+rice\s+cereal|puffed\s+rice")
NOT_PASTA = rx(r"pasta\s+(?:sauce|water)")
GRAINS = rx(r"quinoa|farro|millet|bulgur|barley|couscous|freekeh|polenta|grits|buckwheat|amaranth|sorghum")

BAKING_TITLE = rx(
    r"cakes?|cookies?|brownies?|blondies?|muffins?|bread|biscuits?|scones?|pie|tart|cobbler|crisp|crumble|loaf|"
    r"cupcakes?|donuts?|doughnuts?|dinner\s+rolls?|cinnamon\s+rolls?|sweet\s+rolls?|focaccia|bagels?|pretzels?|"
    r"baguette|cornbread|shortbread|galette|pastr(?:y|ies)|croissants?|pizza\s+dough|flatbread|naan|hush\s+puppies",
    plural=False,
)

SAVORY_PIE_CAKE = rx(
    r"(?:crab|fish|salmon|tuna|potato|rice|corn|zucchini|veggie|vegetable|lentil|chickpea|carrot|quinoa|polenta|pea|"
    r"cauliflower|turnip|radish|pot|cottage|meat|chicken|turkey|beef|savou?ry)\s+(?:cakes?|pies?)|"
    r"shepherd'?s\s+pie|chil(?:i|e)[\s-]+crisp|crispy|crisp\s+(?:rice|garlic|shallots?|onions?)", plural=False)
SAUCE_WORDS = rx(r"dressing|sauce|vinaigrette|dip|chutney|salsa|marinade|relish|pesto|aioli|gremolata|spread|"
                 r"hummus|pikliz|chimichurri|compote|jam|syrup|seasoning|rub|tahini|slaw\s+dressing", plural=False)
SNACK_TITLE = rx(r"energy\s+balls?|granola\s+bars?|popcorn|trail\s+mix|crackers?|chips|snack|spiced\s+(?:nuts|cashews)|"
                 r"roasted\s+chickpeas|bites?", plural=False)

MEAL_TITLE = [
    ("Beverage", rx(r"lemonade|latte|smoothie|tea|cocktail|spritzer|juice|punch|sangria|margarita|milkshake|cider|"
                    r"mocktail|horchata|lassi|cold\s+brew|coffee")),
    ("Dessert", rx(r"cakes?|cookies?|brownies?|blondies?|pie|tart|cobbler|crisp|crumble|pudding|ice\s+cream|sorbet|"
                   r"sherbet|mousse|cheesecake|fudge|truffles?|cupcakes?|macarons?|custard|gelato|popsicles?|"
                   r"rice\s+krispies\s+treats|krispie\s+treats|bundt|shortbread|candy|candies|gummies|"
                   r"mochi|brittle|bark|galette|trifle|pavlova|meringue|bars?|donuts?|doughnuts?|scones?|banana\s+bread|zucchini\s+bread|pumpkin\s+bread", plural=False)),
    ("Breakfast", rx(r"pancakes?|waffles?|french\s+toast|oatmeal|overnight\s+oats|granola|breakfast|brunch|frittata|"
                     r"omelet|omelette|scramble|hash\s+browns?|muffins?|scones?|shakshuka|crepes?|quiche|"
                     r"huevos|chilaquiles|banana\s+bread", plural=False)),
    ("Soup", rx(r"soup|stew|chowder|bisque|chili|pozole|broth", plural=False)),
    ("Salad", rx(r"salad|slaw|tabbouleh|panzanella", plural=False)),
]
# Whole entries only: "dinner party" or "stuffing and dressing" must not count.
MEAL_CATEGORY = {
    "breakfast": "Breakfast", "brunch": "Breakfast", "lunch": "Lunch",
    "dinner": "Dinner", "dinners": "Dinner", "main": "Dinner", "mains": "Dinner", "main course": "Dinner",
    "main courses": "Dinner", "main dish": "Dinner", "main dishes": "Dinner", "entree": "Dinner",
    "entrees": "Dinner", "supper": "Dinner",
    "side": "Side", "sides": "Side", "side dish": "Side", "side dishes": "Side", "appetizer": "Side",
    "appetizers": "Side", "starter": "Side", "starters": "Side",
    "snack": "Snack", "snacks": "Snack",
    "dessert": "Dessert", "desserts": "Dessert", "baked goods": "Dessert", "sweets": "Dessert",
    "desserts or baked goods": "Dessert",
    "beverage": "Beverage", "beverages": "Beverage", "drink": "Beverage", "drinks": "Beverage",
    "cocktail": "Beverage", "cocktails": "Beverage",
    "salad": "Salad", "salads": "Salad", "soup": "Soup", "soups": "Soup",
    "sauce": "Sauce", "sauces": "Sauce", "condiment": "Sauce", "condiments": "Sauce",
    "salad dressing": "Sauce", "sauces and dressings": "Sauce", "condiments and sauces": "Sauce",
}

# Cuisine hints from the ingredient list: a cuisine needs two different clues
# (a name in the title counts as two).
CUISINE_CLUES = {
    "Korean": [r"gochujang", r"gochugaru", r"kimchi", r"doenjang", r"bulgogi", r"bibimbap", r"korean", r"tteok"],
    "Japanese": [r"miso", r"mirin", r"dashi", r"nori", r"sushi", r"ponzu", r"tonkatsu", r"udon", r"soba",
                 r"teriyaki", r"furikake", r"kewpie", r"shichimi", r"onigiri", r"katsu", r"japanese", r"sake"],
    "Thai": [r"thai\s+basil", r"lemongrass", r"galangal", r"kaffir|makrut", r"thai", r"tom\s+(?:kha|yum)",
             r"pad\s+(?:thai|kee\s+mao)", r"red\s+curry\s+paste", r"green\s+curry\s+paste"],
    "Vietnamese": [r"banh\s+mi", r"pho\b", r"nuoc\s+cham", r"vietnamese", r"rice\s+paper", r"vermicelli",
                   r"nuoc\s+mam", r"goi\b"],
    "Indian": [r"garam\s+masala", r"tikka", r"paneer", r"ghee", r"curry\s+leaves?", r"\bdal\b", r"masala", r"tandoori",
               r"naan", r"chaat", r"samosa", r"saag", r"aloo", r"sabzi", r"chana", r"indian", r"turmeric"],
    "Mexican": [r"tortilla", r"chipotle", r"adobo", r"cotija", r"queso", r"taco", r"enchilada", r"quesadilla",
                r"tostada", r"mole\b", r"pozole", r"elote", r"mexican", r"salsa", r"poblano", r"tomatillo"],
    "Italian": [r"parmesan|parmigiano", r"pecorino", r"mozzarella", r"marinara", r"risotto", r"prosciutto",
                r"pancetta", r"gnocchi", r"focaccia", r"italian", r"pesto", r"ricotta", r"basil"],
    "Chinese": [r"shaoxing", r"hoisin", r"five-?spice", r"bok\s+choy", r"doubanjiang", r"sichuan|szechuan",
                r"oyster\s+sauce", r"chinese", r"mapo", r"kung\s+pao", r"lo\s+mein", r"dumpling", r"wonton",
                r"black\s+vinegar", r"chili\s+crisp"],
    "Middle Eastern": [r"tahini", r"za'atar", r"sumac", r"harissa", r"labneh", r"falafel", r"hummus",
                       r"pomegranate\s+molasses", r"shawarma", r"middle\s+eastern", r"ras\s+el\s+hanout"],
    "Greek": [r"greek", r"tzatziki", r"gyro", r"souvlaki", r"kalamata", r"feta"],
}
CUISINE_TITLE = {  # one title hit is enough
    "Korean": r"korean|bulgogi|bibimbap|kimchi|gochujang|dakgalbi|bo\s+ssam|japchae|tteok",
    "Japanese": r"japanese|miso|teriyaki|katsu|udon|soba|sushi|onigiri|ramen|poke|matcha|yakisoba|tonkatsu|furikake",
    "Thai": r"thai|pad\s+(?:thai|kee\s+mao)|tom\s+(?:kha|yum)|larb|som\s+tum|massaman|panang",
    "Vietnamese": r"vietnamese|banh\s+mi|pho|goi\b|bun\s+cha|nuoc\s+cham|bun\s+bo",
    "Indian": r"indian|tikka|masala|saag|paneer|dal\b|dhal|biryani|chana|aloo|samosa|tandoori|korma|vindaloo|chaat",
    "Mexican": r"mexican|taco|enchilada|quesadilla|burrito|tostada|guacamole|elote|carnitas|chilaquiles|pozole",
    "Italian": r"italian|risotto|gnocchi|pesto|lasagn|focaccia|marinara|parmesan|carbonara|bruschetta",
    "Chinese": r"chinese|kung\s+pao|mapo|lo\s+mein|chow\s+mein|dumpling|wonton|szechuan|sichuan|dan\s+dan",
    "Middle Eastern": r"shawarma|falafel|hummus|tabbouleh|shakshuka|za'atar|labneh|baba\s+ghanoush",
    "Greek": r"greek|tzatziki|gyro|souvlaki|spanakopita",
}


# --------------------------------------------------------------------------
# Tag inference
# --------------------------------------------------------------------------

def _lines(ingredients) -> list:
    return [fold(i) for i in (ingredients or []) if str(i).strip()]


def _clean(line: str) -> str:
    return SAFE.sub(" ", line)


def _split_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        value = ",".join(str(v) for v in value)
    return [p.strip() for p in re.split(r"[,;/]", fold(value)) if p.strip()]


def source_cuisines(value) -> set:
    found = set()
    for part in _split_list(value):
        part = re.sub(r"[- ]?(?:inspired|style)$", "", part).strip()
        if part in CUISINES:
            found.add(CUISINES[part])
    # a list of 3+ cuisines ("American, French, Italian, Mediterranean, Mexican") says nothing useful
    return found if len(found) <= 2 else set()


def meals_from_category(value) -> set:
    found = {MEAL_CATEGORY[t] for t in _split_list(value) if t in MEAL_CATEGORY}
    # A list claiming breakfast, dinner, snack, dessert and side all at once is keyword spam.
    return set() if len(found & {"Breakfast", "Lunch", "Dinner", "Side", "Snack", "Dessert"}) >= 4 else found


def diet_status(title: str, lines: list, claim_values=(), directions: str = "") -> set:
    """Vegetarian / Vegan when the recipe says so or the whole ingredient list is clear.

    A claim only counts if it is a whole entry in the category/cuisine fields (some sites stuff
    those with keyword spam like "Vegetarian Diet Cuisine") or is in the title, and it is
    ignored if the ingredients contain meat or fish. Without a claim, nothing is inferred if the
    title or directions name an animal ingredient the list doesn't (an incomplete list, or a vegan
    "tuna" salad: better to leave it for a person than guess).
    """
    tokens = {t for value in claim_values for t in _split_list(value)}
    ftitle = fold(title)
    claimed = set()
    if "vegan" in tokens or (re.search(r"\bvegan\b", ftitle) and not re.search(r"non-?vegan|not\s+vegan", ftitle)):
        claimed |= {"Vegan", "Vegetarian"}
    elif "vegetarian" in tokens or re.search(r"\bvegetarian\b", ftitle):
        claimed.add("Vegetarian")
    gluten_free = {"Gluten-Free"} if (tokens & {"gluten-free", "gluten free"}
                                      or re.search(r"gluten[- ]free", ftitle)) else set()
    cleaned = [_clean(line) for line in lines]
    if any(FLESH.search(c) for c in cleaned):
        return gluten_free
    if len(lines) < 3 or any(DOUBTFUL.search(c) for c in cleaned) or \
            FLESH.search(_clean(ftitle + " " + fold(directions))):
        return claimed | gluten_free
    result = claimed | gluten_free | {"Vegetarian"}
    if not any(DAIRY_EGG.search(c) for c in cleaned):
        result.add("Vegan")
    return result


def suggest(title, ingredients=None, directions=None, category=None, cuisine=None, body="", extra_claims="",
            existing=()) -> set:
    """Tags this recipe qualifies for, as a set of canonical names.

    `existing` are tags the recipe already has; they stop us guessing a second cuisine or a meal type.
    """
    have = set(normalise_existing(existing))
    ftitle = fold(title)
    lines = _lines(ingredients)
    cleaned = [_clean(line) for line in lines]
    steps = fold(" ".join(str(d) for d in (directions or [])))
    # the dish itself: the title before "with ...", so side ingredients don't set the meal type
    head = re.split(r"\bwith\b|\bover\b|\bserved\b|[:+(]", ftitle)[0].strip() or ftitle
    prose = fold(body)
    tags = set()

    # --- diet -------------------------------------------------------------
    diet = diet_status(title, lines, (category, cuisine, extra_claims), steps)
    tags |= diet
    plant_only = "Vegetarian" in diet and not any(FLESH.search(c) for c in cleaned) and len(lines) >= 3

    # --- main ingredient --------------------------------------------------
    meat_lines = [SEASONING.sub(" ", c) for c in cleaned if not BROTH_LINE.search(c)]
    for tag, pattern in PROTEIN.items():
        if any(pattern.search(c) for c in meat_lines) or (not plant_only and pattern.search(ftitle)):
            tags.add(tag)
    if not plant_only and TITLE_ONLY_PORK.search(ftitle):
        tags.add("Pork")
    if "Fish" in tags or "Shrimp" in tags or (not plant_only and OTHER_SHELLFISH.search(ftitle)) or \
            any(OTHER_SHELLFISH.search(c) for c in meat_lines):
        tags.add("Seafood")
    if not plant_only and rx(r"eggs?|frittata|omelet|omelette|quiche|shakshuka|scramble").search(ftitle):
        tags.add("Eggs")

    def hit(pattern, avoid=None):
        for text in [ftitle] + cleaned:
            if avoid:
                text = avoid.sub(" ", text)
            if pattern.search(text):
                return True
        return False

    if hit(BEANS, NOT_BEANS):
        tags.add("Beans")
    if hit(LENTILS):
        tags.add("Lentils")
    if hit(PASTA, NOT_PASTA):
        tags.add("Pasta")
    if hit(NOODLES):
        tags.add("Noodles")
    serving_rice = rx(r"for\s+serving|to\s+serve|serve\s+with|serving|optional|garnish", plural=False)
    rice_lines = [c for c in cleaned if not serving_rice.search(c)]
    if any(RICE.search(NOT_RICE.sub(" ", t)) for t in [ftitle] + rice_lines):
        tags.add("Rice")
    if hit(GRAINS):
        tags.add("Grains")

    # --- style ------------------------------------------------------------
    def mentions(pattern, at_least=2):
        return len(pattern.findall(steps)) >= at_least or bool(pattern.search(ftitle))

    dessertish = bool(MEAL_TITLE[1][1].search(ftitle))
    pantry_bake = any(re.search(r"baking\s+(?:powder|soda)|\byeast\b", c) for c in cleaned) \
        and any(re.search(r"\bflour\b", c) for c in cleaned) \
        and re.search(r"\bbake\b|\bbaked\b|preheat the oven|preheat oven", steps)
    protein_led = bool(set(PROTEIN) & tags)
    if not protein_led and (BAKING_TITLE.search(SAVORY_PIE_CAKE.sub(" ", ftitle)) or pantry_bake):
        tags.add("Baking")
    # a dish built on curry (title, or a curry paste), not one that just has curry powder in a dressing
    if rx(r"curry|korma|massaman|vindaloo|tikka\s+masala|laksa", plural=False).search(ftitle) or \
            any(re.search(r"curry\s+paste", c) for c in cleaned):
        tags.add("Curry")
    if "Curry" in tags and not rx(r"curry|korma|massaman|vindaloo|tikka\s+masala|laksa", plural=False).search(ftitle) \
            and re.search(r"\b(?:soup|salad)\b", head):
        tags.discard("Curry")  # a curry-paste soup or salad is a soup or salad first
    if rx(r"sandwich|burger|wrap|banh\s+mi|slider|hoagie|toastie|panini|onigirazu|sub|gua\s+bao").search(
            re.sub(r"(?:lettuce|cabbage|collard|rice\s+paper|spring)\s+wraps?", " ", ftitle)):
        tags.add("Sandwich")
    if re.search(r"one[- ]pot|one[- ]pan|one[- ]skillet", ftitle + " " + prose + " " + steps):
        tags.add("One-Pot")
    sheet_title = bool(rx(r"sheet[- ]pan", plural=False).search(ftitle))
    if mentions(rx(r"sheet[- ]pan", plural=False)) and not dessertish and \
            (sheet_title or not re.search(r"granola|bars?\b|cookies?|bread|muffins?|crackers?", ftitle)):
        tags.add("Sheet Pan")
    if mentions(rx(r"instant\s+pot|pressure\s+cook(?:er|ing)?|multi-?cooker|electric\s+pressure", plural=False)):
        tags.add("Instant Pot")
    if mentions(rx(r"slow[- ]cooker|crock[- ]?pot|slow[- ]cook", plural=False)):
        tags.add("Slow Cooker")
    if mentions(rx(r"air[- ]fr(?:yer|ied|y)", plural=False)):
        tags.add("Air Fryer")
    if mentions(rx(r"grill(?:ed|ing)?|skewers?", plural=False), 3) and not dessertish and \
            not SAUCE_WORDS.search(ftitle.split(" ")[-1]):
        tags.add("Grill")

    # --- meal type --------------------------------------------------------
    plain_title = SAVORY_PIE_CAKE.sub(" ", head)
    title_meals = set()
    for tag, pattern in MEAL_TITLE:
        if tag == "Beverage" and "Dessert" in title_meals:
            continue  # coffee cake, lemonade bars
        if pattern.search(plain_title):
            title_meals.add(tag)
    from_category = meals_from_category(category)
    if title_meals & {"Dessert", "Beverage", "Sauce"}:
        from_category -= {"Dinner", "Lunch"}  # a cake isn't dinner, whatever the site's category says
    tags |= title_meals | from_category
    if SAUCE_WORDS.search(head.split(",")[0].split(" ")[-1]):
        tags.add("Sauce")
    if SNACK_TITLE.search(ftitle):
        tags.add("Snack")
    if "Salad" in tags and re.search(r"\bslaw\b", head):
        tags.add("Side")
    if "Dessert" in tags and re.search(r"\bbake\b|\bbaked\b|\boven\b", steps) and \
            rx(r"cake|cookie|brownie|blondie|pie|tart|cobbler|crisp|crumble|bars?|scone").search(plain_title):
        tags.add("Baking")
    meals = set(MEAL) & (tags | have)
    if not meals:
        mains = {"Chicken", "Beef", "Pork", "Turkey", "Lamb", "Fish", "Shrimp", "Tofu", "Pasta", "Noodles",
                 "Rice", "Beans", "Lentils", "Curry", "Sandwich"}
        if mains & tags and "Baking" not in tags:
            tags.add("Dinner")

    # --- cuisine ----------------------------------------------------------
    if not (set(CUISINE_ORDER) & have):  # the recipe already has a cuisine: leave it alone
        text = " ".join(cleaned)
        title_hits = {n for n, pat in CUISINE_TITLE.items() if re.search(r"\b(?:%s)" % pat, ftitle)}
        cuisines = source_cuisines(cuisine)
        if title_hits and not cuisines & title_hits:
            cuisines = title_hits  # a dish named in the title beats a mislabelled source ("pho" listed as Thai)
        elif not cuisines:
            scores = {n: sum(1 for c in clues if re.search(r"\b(?:%s)" % c, text)) + (2 if n in title_hits else 0)
                      for n, clues in CUISINE_CLUES.items()}
            scores = sorted(((sc, n) for n, sc in scores.items() if sc >= 2), reverse=True)
            # two clues needed; with a close second place we don't guess
            if scores and (len(scores) == 1 or scores[0][0] - scores[1][0] >= 2):
                cuisines = {scores[0][1]}
        tags |= cuisines
    return tags


# --------------------------------------------------------------------------
# Merging with existing tags
# --------------------------------------------------------------------------

def normalise_existing(existing) -> list:
    """Tidy capitalisation/synonyms of tags already on a recipe; keeps unknown tags."""
    if isinstance(existing, str):
        existing = re.split(r"[,\s]+", existing.strip())
    out = []
    for tag in existing or []:
        tag = str(tag).strip()
        if not tag:
            continue
        tag = tag.lstrip("\U0001F300-\U0001FAFF ").strip()  # a leading emoji, e.g. a turkey on Thanksgiving
        key = tag.lower()
        tag = SYNONYMS.get(key) or CANONICAL.get(key) or CUISINES.get(key) or \
            (tag if any(c.isupper() for c in tag) else re.sub(r"(^|[\s-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), tag))
        if tag.lower() not in {t.lower() for t in out}:
            out.append(tag)
    return out


def order_tags(tags) -> list:
    rank = {}
    for group, names in enumerate([MEAL, CUISINE_ORDER, MAIN, DIET, STYLE]):
        for i, name in enumerate(names):
            rank[name] = (group, i)
    return sorted(tags, key=lambda t: rank.get(t, (9, 0)) + (t.lower(),))


def merge(existing, suggested) -> list:
    base = normalise_existing(existing)
    have = {t.lower() for t in base}
    # Generic tags add nothing next to a specific one the recipe already has.
    merged = base + [t for t in suggested if t.lower() not in have]
    return order_tags(merged)


# --------------------------------------------------------------------------
# Recipe files
# --------------------------------------------------------------------------

FRONT = re.compile(r"^---\n(.*?)\n---[ \t]*(?:\n|$)", re.S)
TAGS_BLOCK = re.compile(r"^tags:(?:[ \t]*\[[^\n]*\]|[ \t]*[^\n\[]*)\n(?:[ \t]*-[^\n]*\n)*", re.M)


def render_tags(tags) -> str:
    import yaml
    if not tags:
        return "tags: []\n"
    return "tags:\n" + yaml.safe_dump(list(tags), default_flow_style=False, allow_unicode=True, width=1000)


def retag_file(path: Path, write: bool):
    """Returns (old_tags, new_tags). Rewrites only the tags block when write is True."""
    import yaml
    text = path.read_text(encoding="utf-8")
    m = FRONT.match(text)
    if not m:
        return None
    fm = yaml.safe_load(m.group(1)) or {}
    old = fm.get("tags") or []
    suggested = suggest(
        fm.get("title", path.stem), fm.get("ingredients"), fm.get("directions"),
        fm.get("category"), fm.get("cuisine"), text[m.end():], existing=old,
    )
    new = merge(old, suggested)
    if write and [str(t) for t in (old if isinstance(old, list) else [old])] != new:
        head = m.group(1) + "\n"
        if TAGS_BLOCK.search(head):
            head = TAGS_BLOCK.sub(lambda _: render_tags(new), head, count=1)
        else:
            head += render_tags(new)
        out = "---\n" + head + "---\n" + text[m.end():]
        check = yaml.safe_load(FRONT.match(out).group(1))
        before = {k: v for k, v in fm.items() if k != "tags"}
        after = {k: v for k, v in check.items() if k != "tags"}
        if before != after or check.get("tags") != new:
            raise RuntimeError(f"{path.name}: rewrite would change more than tags, skipped")
        path.write_text(out, encoding="utf-8")
    return old, new


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", help="recipe files (default: all of _recipes/)")
    ap.add_argument("--write", action="store_true", help="apply changes (default is a dry run)")
    ap.add_argument("--diff", action="store_true", help="print the tags added to each recipe")
    args = ap.parse_args(argv)

    paths = [Path(f) if "/" in f else ROOT / "_recipes" / f for f in args.files] or sorted((ROOT / "_recipes").glob("*.md"))
    changed = added = 0
    counts = {}
    for path in paths:
        result = retag_file(path, args.write)
        if result is None:
            print(f"skip {path.name}: no front matter")
            continue
        old, new = result
        old_names = normalise_existing(old)
        gained = [t for t in new if t.lower() not in {o.lower() for o in old_names}]
        for t in new:
            counts[t] = counts.get(t, 0) + 1
        if gained or [str(t) for t in (old if isinstance(old, list) else [old])] != new:
            changed += 1
            added += len(gained)
            if args.diff:
                print(f"{path.stem}: +{', '.join(gained) if gained else '(tidied)'}")
    verb = "updated" if args.write else "would update"
    print(f"\n{verb} {changed} of {len(paths)} recipes, {added} tags added")
    if not args.write:
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        print("tags after: " + ", ".join(f"{t} {n}" for t, n in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
