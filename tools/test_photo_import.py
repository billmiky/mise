#!/usr/bin/env python3
"""Tests for tools/importer/photo.py (no network or API key needed).

Run: python3 tools/test_photo_import.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "importer"))
import photo  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 2048

CLAUDE_ANSWER = {
    "is_recipe": True,
    "title": "Weeknight  Dal",
    "yield": "Serves 4",
    "prep_time": "10 minutes",
    "cook_time": "1 hr 5 min",
    "total_time": "",
    "ingredients": ["1 cup red lentils", "", "For the tadka:", "2 Tbsp ghee"],
    "directions": ["1. Rinse the lentils.", "Step 2: Simmer until soft.", "  "],
    "notes": "A pantry staple.",
    "cookbook_title": "Some Cookbook",
    "cookbook_author": "A. Cook",
    "cookbook_page": "p. 42",
    "source": "",
    "dish_photo": {"present": True, "image": 1, "left": 0.1, "top": -0.2, "right": 0.9, "bottom": 0.6},
}


class NormalizeTest(unittest.TestCase):
    def test_times_become_minutes(self):
        self.assertEqual(photo._minutes("1 hr 15 min"), "75")
        self.assertEqual(photo._minutes("45 minutes"), "45")
        self.assertEqual(photo._minutes("1.5 hours"), "90")
        self.assertEqual(photo._minutes("30"), "30")
        self.assertEqual(photo._minutes(""), "")
        self.assertEqual(photo._minutes("overnight"), "")

    def test_recipe_cleanup(self):
        r = photo.normalize_recipe(CLAUDE_ANSWER)
        self.assertEqual(r["title"], "Weeknight Dal")
        self.assertEqual(r["ingredients"], ["1 cup red lentils", "For the tadka:", "2 Tbsp ghee"])
        self.assertEqual(r["instructions"], ["Rinse the lentils.", "Simmer until soft."])
        self.assertEqual((r["prep_time"], r["cook_time"], r["total_time"]), ("10", "65", "75"))

    def test_form_text_is_split_into_lines(self):
        r = photo.normalize_recipe({"title": "X", "ingredients": "a\n\nb", "directions": "one\ntwo"})
        self.assertEqual(r["ingredients"], ["a", "b"])
        self.assertEqual(r["instructions"], ["one", "two"])

    def test_cover_box(self):
        self.assertEqual(photo.cover_box(CLAUDE_ANSWER["dish_photo"], 2), {"image": 1, "box": [0.1, 0.0, 0.9, 0.6]})
        self.assertIsNone(photo.cover_box(CLAUDE_ANSWER["dish_photo"], 1), "index out of range")
        self.assertIsNone(photo.cover_box({"present": False}, 2))
        self.assertIsNone(photo.cover_box({"present": True, "image": 0, "left": 0.5, "top": 0.5,
                                           "right": 0.55, "bottom": 0.9}, 1), "too narrow")


class CookbookFieldsTest(unittest.TestCase):
    def test_page_prefixes_are_dropped(self):
        for raw in ("p. 112", "Page 112", "pp. 112-113", "112"):
            self.assertRegex(photo.cookbook_fields({"cookbook_page": raw})["cookbook_page"], r"^112")

    def test_editor_can_change_cookbook_fields(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import update_recipe
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "_recipes").mkdir()
            (root / "_recipes" / "x.md").write_text("---\ntitle: X\nsource: old\n---\nBody\n")
            with mock.patch.object(update_recipe, "ROOT", root):
                update_recipe.apply("x", {"cookbook": " Jerusalem ", "cookbook_page": "88", "source": ""})
            text = (root / "_recipes" / "x.md").read_text()
            self.assertIn("cookbook: Jerusalem\n", text)
            self.assertIn("cookbook_page: '88'\n", text)
            self.assertNotIn("source", text)
            self.assertTrue(text.endswith("Body\n"))


class ExtractTest(unittest.TestCase):
    def run_extract(self, env, images):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", env, clear=True):
            out = Path(d) / "result.json"
            paths = []
            for i, data in enumerate(images):
                p = Path(d) / f"page-{i}.jpg"
                p.write_bytes(data)
                paths.append(str(p))
            self.assertEqual(photo.main(["extract", "--out", str(out), *paths]), 0)
            return json.loads(out.read_text())

    def test_no_key_tells_the_page_to_fall_back(self):
        self.assertEqual(self.run_extract({}, [JPEG]), {"status": "no_key"})

    def test_no_photos(self):
        self.assertEqual(self.run_extract({"ANTHROPIC_API_KEY": "x"}, [])["status"], "error")

    def test_result_shape(self):
        res = photo.result_from_claude(CLAUDE_ANSWER, 2)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["recipe"]["directions"], ["Rinse the lentils.", "Simmer until soft."])
        self.assertEqual(res["recipe"]["cookbook"], "Some Cookbook")
        self.assertEqual(res["recipe"]["cookbook_author"], "A. Cook")
        self.assertEqual(res["recipe"]["cookbook_page"], "42")
        self.assertEqual(res["recipe"]["source"], "")
        self.assertEqual(res["cover"]["image"], 1)

    def test_not_a_recipe(self):
        self.assertEqual(photo.result_from_claude({**CLAUDE_ANSWER, "is_recipe": False}, 1)["status"], "error")


class SaveTest(unittest.TestCase):
    def test_writes_recipe_and_picture(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "_recipes").mkdir()
            (root / "_recipes" / "weeknight-dal.md").write_text("---\n---\n")  # name already taken
            cover = root / "cover.jpg"
            cover.write_bytes(JPEG)
            form = {**CLAUDE_ANSWER, "cookbook": "Some Cookbook", "cookbook_author": "A. Cook",
                    "cookbook_page": "Page 42", "tags": "quick lentils", "season": "fall winter", "rating": "4",
                    "difficulty": "medium", "kid_friendly": "true"}
            (root / "r.json").write_text(json.dumps(form))
            with mock.patch.object(photo, "REPO_ROOT", root):
                rc = photo.main(["save", "--recipe", str(root / "r.json"), "--cover", str(cover),
                                 "--slug-file", str(root / "slug")])
            self.assertEqual(rc, 0)
            slug = (root / "slug").read_text()
            self.assertEqual(slug, "weeknight-dal-2")
            self.assertTrue((root / "images" / "weeknight-dal-2.jpg").is_file())
            md = (root / "_recipes" / f"{slug}.md").read_text()
            import yaml
            fm = yaml.safe_load(md.split("---\n")[1])
            self.assertEqual(fm["image"], "weeknight-dal-2.jpg")
            self.assertEqual((fm["cookbook"], fm["cookbook_author"], fm["cookbook_page"]),
                             ("Some Cookbook", "A. Cook", "42"))
            self.assertNotIn("source", fm, "empty source isn't written")
            self.assertEqual(fm["season"], ["fall", "winter"])
            self.assertEqual((fm["rating"], fm["difficulty"], fm["kid_friendly"]), (4, "medium", True))
            self.assertIn("Quick", fm["tags"])
            self.assertEqual(fm["directions"], ["Rinse the lentils.", "Simmer until soft."])
            self.assertTrue(md.rstrip().endswith("A pantry staple."))

    def test_needs_a_picture_and_content(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "_recipes").mkdir()
            (root / "r.json").write_text(json.dumps(CLAUDE_ANSWER))
            with mock.patch.object(photo, "REPO_ROOT", root):
                self.assertEqual(photo.main(["save", "--recipe", str(root / "r.json")]), 1)
                (root / "r.json").write_text(json.dumps({"title": "X", "ingredients": [], "directions": ["a"]}))
                self.assertEqual(photo.main(["save", "--recipe", str(root / "r.json")]), 1)


if __name__ == "__main__":
    unittest.main()
