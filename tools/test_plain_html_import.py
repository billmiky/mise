#!/usr/bin/env python3
"""Tests for the plain-HTML fallback in tools/importer/scrape.py (no network needed).

Run: python3 tools/test_plain_html_import.py
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "importer"))
import scrape  # noqa: E402

# Ingredients as <br>-separated paragraphs under an <h2>, like thescienceofbaking.ca
BR_PAGE = """<html><head><title>Homemade No-Rise Donuts | The Science of Baking</title>
<meta property="og:image" content="https://example.com/donut.jpg"></head><body>
<h1>Homemade No-Rise Donuts</h1>
<div class="entry-content">
<h2>Ingredients</h2>
<h3>For the donuts:</h3>
<p>3 1/2 cups flour<br>3/4 cup sugar<br>2 eggs</p>
<h2>Directions:</h2>
<p>Combine the flour and sugar.</p><p></p>
<p>Fry for 2 minutes per side.</p>
</div>
<div class="comments"><h2>Comments</h2><p>Great, thanks!</p></div>
</body></html>"""

LIST_PAGE = """<html><head><meta property="og:title" content="Lemon Bars - Some Blog"></head><body>
<h2>Ingredients</h2><ul><li>1 cup flour</li><li>2 lemons</li></ul>
<h2>Instructions</h2><ol><li>Mix.</li><li>Bake 25 minutes.</li></ol>
<h2>Notes</h2><p>Keeps for 3 days.</p>
</body></html>"""

PLUGIN_PAGE = """<html><body><h1>Plugin Soup</h1>
<ul><li class="wprm-recipe-ingredient">1 onion, diced</li><li class="wprm-recipe-ingredient">2 cups stock</li></ul>
<div class="wprm-recipe-instruction-text">Saute the onion.</div>
<div class="wprm-recipe-instruction-text">Add stock and simmer.</div></body></html>"""

NO_RECIPE_PAGE = "<html><body><h1>About us</h1><p>We like food.</p></body></html>"


class PlainHtmlTest(unittest.TestCase):
    def test_br_separated_ingredients_and_paragraph_steps(self):
        d = scrape.parse_plain_html(BR_PAGE)
        self.assertEqual(d["title"], "Homemade No-Rise Donuts")
        self.assertEqual(d["ingredients"], ["3 1/2 cups flour", "3/4 cup sugar", "2 eggs"])
        self.assertEqual(d["instructions"], ["Combine the flour and sugar.", "Fry for 2 minutes per side."])
        self.assertEqual(d["image_url"], "https://example.com/donut.jpg")

    def test_sections_stop_before_comments(self):
        d = scrape.parse_plain_html(BR_PAGE)
        self.assertNotIn("Great, thanks!", d["instructions"])

    def test_lists_and_notes_heading_and_title_suffix(self):
        d = scrape.parse_plain_html(LIST_PAGE)
        self.assertEqual(d["title"], "Lemon Bars")
        self.assertEqual(d["ingredients"], ["1 cup flour", "2 lemons"])
        self.assertEqual(d["instructions"], ["Mix.", "Bake 25 minutes."])

    def test_recipe_plugin_markup(self):
        d = scrape.parse_plain_html(PLUGIN_PAGE)
        self.assertEqual(d["title"], "Plugin Soup")
        self.assertEqual(d["ingredients"], ["1 onion, diced", "2 cups stock"])
        self.assertEqual(d["instructions"], ["Saute the onion.", "Add stock and simmer."])

    def test_page_without_a_recipe_gives_nothing(self):
        self.assertIsNone(scrape.parse_plain_html(NO_RECIPE_PAGE))


class FetchRecipeTest(unittest.TestCase):
    def test_falls_back_when_scrapers_and_json_ld_find_nothing(self):
        with mock.patch.object(scrape, "fetch_html", return_value=BR_PAGE):
            d = scrape.fetch_recipe("http://example.com/donuts")
        self.assertEqual(d["title"], "Homemade No-Rise Donuts")
        self.assertEqual(len(d["ingredients"]), 3)

    def test_still_reports_a_page_with_no_recipe(self):
        with mock.patch.object(scrape, "fetch_html", return_value=NO_RECIPE_PAGE):
            with self.assertRaises(scrape.ImportError_) as ctx:
                scrape.fetch_recipe("http://example.com/about")
        self.assertIn("No recipe found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
