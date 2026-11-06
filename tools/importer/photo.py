"""
Cookbook photo / screenshot importer — called by the photo-extract and photo-save workflows.

Two steps, so a person can check the recipe between them (import.html, "From a photo"):

  extract  Read 1-4 page photos with Claude and write a result file the Import page picks up:
             python tools/importer/photo.py extract --out result.json page-1.jpg page-2.jpg
           The result is {"status": "ok", "recipe": {...}, "cover": {...} | null},
           {"status": "no_key"} when the ANTHROPIC_API_KEY secret isn't set (the page then
           falls back to reading the photo on the device), or {"status": "error", "message": ...}.
           It always writes the file and exits 0, so the page gets an answer instead of a timeout.

  save     Write the reviewed recipe to _recipes/<slug>.md (and the picture to images/):
             python tools/importer/photo.py save --recipe recipe.json [--cover cover.jpg]
           recipe.json is what the review form sends: title, ingredients, directions, yield,
           prep_time, cook_time, total_time, cookbook, cookbook_author, cookbook_page, source,
           notes, tags, season, rating, difficulty, kid_friendly.
"""
import argparse
import base64
import json
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrape  # noqa: E402  (slugify, build_markdown, unique_slug, sniff_extension)

MODEL = "claude-opus-5-5"
MAX_PAGES = 4

# What Claude returns. Kept flat and all-required so structured outputs can enforce it.
RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_recipe": {"type": "boolean"},
        "title": {"type": "string"},
        "yield": {"type": "string"},
        "prep_time": {"type": "string"},
        "cook_time": {"type": "string"},
        "total_time": {"type": "string"},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "directions": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
        "cookbook_title": {"type": "string"},
        "cookbook_author": {"type": "string"},
        "cookbook_page": {"type": "string"},
        "source": {"type": "string"},
        "dish_photo": {
            "type": "object",
            "properties": {
                "present": {"type": "boolean"},
                "image": {"type": "integer"},
                "left": {"type": "number"},
                "top": {"type": "number"},
                "right": {"type": "number"},
                "bottom": {"type": "number"},
            },
            "required": ["present", "image", "left", "top", "right", "bottom"],
            "additionalProperties": False,
        },
    },
    "required": ["is_recipe", "title", "yield", "prep_time", "cook_time", "total_time",
                 "ingredients", "directions", "notes", "cookbook_title", "cookbook_author",
                 "cookbook_page", "source", "dish_photo"],
    "additionalProperties": False,
}

PROMPT = """These {n} image(s) are photos or screenshots of one recipe, usually from a cookbook \
(the recipe may continue from one image to the next, in order). Transcribe it for a family recipe site.

- Copy ingredients and directions faithfully, in order, one list item per ingredient and per step. \
Keep quantities, units and fractions exactly as printed (use ½, ¼ etc. if the book does). \
Don't invent, convert, or "improve" anything.
- Ingredient sub-headings (e.g. "For the sauce") become their own ingredient line ending in a colon.
- Join words that a page break or hyphenation split. Drop page numbers, running headers and \
anything that belongs to a different recipe on the same page.
- Steps: drop the printed step numbers.
- Times are whole minutes as plain numbers ("1 hour 15 minutes" -> "75"); empty string if the \
page doesn't say. Yield as printed ("Serves 4", "12 muffins"), or empty.
- notes: the headnote or tips, briefly, or empty.
- cookbook_title / cookbook_author / cookbook_page: the book this is from, its author, and the \
page number, as far as the images show them (running headers and footers often name the book or \
chapter and carry the page number). Title in normal title case, page as just the number(s) ("112" \
or "112-113"). Empty strings for anything not visible; don't guess.
- source: only if it's not from a book, the magazine, newspaper or person it credits; else empty.
- dish_photo: if an image contains a photo of the finished dish, give that image's 0-based index \
and the photo's edges as fractions (0-1) of the image width/height; otherwise present=false and zeros.
- If the images don't contain a recipe, set is_recipe=false and leave the rest empty."""


# ---------------------------------------------------------------------------
# Shared cleanup (also used on what the review form sends back)
# ---------------------------------------------------------------------------

def _minutes(value) -> str:
    """'75', '1 hr 15 min', '45 minutes' -> '75' / '75' / '45'; '' when there's no number."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    if not s:
        return ""
    if s.isdigit():
        return str(int(s)) if int(s) else ""
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", s)
    mins = re.search(r"(\d+)\s*(?:m|min|mins|minute|minutes)\b", s)
    if hours or mins:
        total = round(float(hours.group(1)) * 60) if hours else 0
        total += int(mins.group(1)) if mins else 0
        return str(total) if total else ""
    m = re.match(r"(\d+)", s)
    return m.group(1) if m else ""


def _lines(value) -> list:
    if isinstance(value, str):
        value = value.split("\n")
    if not isinstance(value, list):
        return []
    return [scrape.clean_text(v) for v in value if isinstance(v, str) and scrape.clean_text(v)]


def normalize_recipe(data: dict) -> dict:
    """Clean a recipe dict from Claude or the review form into the shape build_markdown expects."""
    recipe = {
        "title": scrape.clean_text(data.get("title") or "") or "Untitled Recipe",
        "ingredients": _lines(data.get("ingredients")),
        "instructions": [re.sub(r"^(?:step\s*)?\d+[\.\):]\s*", "", s, flags=re.I)
                         for s in _lines(data.get("directions"))],
        "yield": scrape.clean_text(data.get("yield") or ""),
    }
    for key in ("prep_time", "cook_time", "total_time"):
        recipe[key] = _minutes(data.get(key))
    if not recipe["total_time"] and recipe["prep_time"] and recipe["cook_time"]:
        recipe["total_time"] = str(int(recipe["prep_time"]) + int(recipe["cook_time"]))
    recipe["instructions"] = [s for s in recipe["instructions"] if s]
    return recipe


def cookbook_fields(data: dict) -> dict:
    """cookbook / cookbook_author / cookbook_page from a dict, cleaned; missing ones are ''."""
    out = {}
    for key in ("cookbook", "cookbook_author", "cookbook_page"):
        out[key] = scrape.clean_text(data.get(key) or "")
    # "p. 112", "Page 112" -> "112"
    out["cookbook_page"] = re.sub(r"^(?:pages?|pp?)\.?\s*", "", out["cookbook_page"], flags=re.I)
    return out


def cover_box(dish_photo, n_images: int):
    """Claude's dish-photo box -> {"image", "box": [l, t, r, b]} or None if absent or implausible."""
    if not isinstance(dish_photo, dict) or not dish_photo.get("present"):
        return None
    try:
        idx = int(dish_photo["image"])
        box = [max(0.0, min(1.0, float(dish_photo[k]))) for k in ("left", "top", "right", "bottom")]
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= idx < n_images:
        return None
    # Too small to be a dish photo, or inverted
    if box[2] - box[0] < 0.15 or box[3] - box[1] < 0.15:
        return None
    return {"image": idx, "box": [round(v, 4) for v in box]}


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def media_type(content: bytes) -> str:
    ext = scrape.sniff_extension(content)
    return {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "")


def read_with_claude(paths: list) -> dict:
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"status": "no_key"}
    import anthropic

    content = []
    for i, path in enumerate(paths):
        data = Path(path).read_bytes()
        mt = media_type(data)
        if not mt:
            return {"status": "error", "message": f"Photo {i + 1} isn't a JPEG, PNG, WebP or GIF image."}
        content.append({"type": "text", "text": f"Image {i}:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mt, "data": base64.standard_b64encode(data).decode()}})
    content.append({"type": "text", "text": PROMPT.format(n=len(paths))})

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RECIPE_SCHEMA}},
            # If a safety check declines (very unlikely for recipes), let the API retry on another model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError:
        return {"status": "error", "message": "The ANTHROPIC_API_KEY secret was rejected — check it in the repo's Actions secrets."}
    except anthropic.RateLimitError:
        return {"status": "error", "message": "Claude is rate-limited right now — try again in a minute."}
    except anthropic.APIStatusError as e:
        return {"status": "error", "message": f"Claude API error ({e.status_code}): {e.message}"}
    except anthropic.APIConnectionError:
        return {"status": "error", "message": "Couldn't reach the Claude API — try again."}

    if response.stop_reason == "refusal":
        return {"status": "error", "message": "Claude declined to read these photos."}
    if response.stop_reason == "max_tokens":
        return {"status": "error", "message": "The recipe was too long to read in one go — try fewer photos."}
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError:
        return {"status": "error", "message": "Claude's answer wasn't valid JSON — try again."}

    print(f"Claude usage: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    return result_from_claude(data, len(paths))


def result_from_claude(data: dict, n_images: int) -> dict:
    if not data.get("is_recipe") or not (data.get("ingredients") or data.get("directions")):
        return {"status": "error", "message": "Couldn't find a recipe in those photos. Try a sharper, straight-on photo of the page."}
    recipe = normalize_recipe(data)
    # The review form edits these as they came from the page
    recipe["directions"] = recipe.pop("instructions")
    recipe["notes"] = scrape.clean_text(data.get("notes") or "")
    recipe["source"] = scrape.clean_text(data.get("source") or "")
    recipe.update(cookbook_fields({
        "cookbook": data.get("cookbook_title"), "cookbook_author": data.get("cookbook_author"),
        "cookbook_page": data.get("cookbook_page")}))
    return {"status": "ok", "recipe": recipe, "cover": cover_box(data.get("dish_photo"), n_images)}


def cmd_extract(args) -> int:
    paths = args.images[:MAX_PAGES]
    try:
        if not paths:
            result = {"status": "error", "message": "No photos were uploaded."}
        else:
            result = read_with_claude(paths)
    except Exception as e:  # always answer the page
        result = {"status": "error", "message": f"Reading failed: {type(e).__name__}: {e}"}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{result['status']}: " + (result.get("recipe", {}).get("title") or result.get("message", "")))
    return 0


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def body_text(notes: str) -> str:
    notes = (notes or "").strip()
    return f"\n{notes}\n" if notes else ""


def cmd_save(args) -> int:
    data = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
    recipe = normalize_recipe(data)
    if not recipe["ingredients"] or not recipe["instructions"]:
        print("ERROR: the recipe needs at least one ingredient and one step", file=sys.stderr)
        return 1

    recipes_dir = REPO_ROOT / "_recipes"
    slug = scrape.unique_slug(recipes_dir, scrape.slugify(recipe["title"]) or "recipe")

    image_ref = ""
    if args.cover and Path(args.cover).is_file():
        content = Path(args.cover).read_bytes()
        ext = scrape.sniff_extension(content)
        if ext:
            image_ref = f"{slug}{ext}"
            (REPO_ROOT / "images").mkdir(exist_ok=True)
            shutil.copyfile(args.cover, REPO_ROOT / "images" / image_ref)
    if not image_ref:
        print("ERROR: no recipe picture (every recipe needs one)", file=sys.stderr)
        return 1

    rating = data.get("rating")
    rating = int(rating) if str(rating or "").strip().isdigit() and 1 <= int(rating) <= 5 else None
    difficulty = str(data.get("difficulty") or "easy").lower()
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "easy"
    tags = [t for t in re.split(r"[\s,]+", str(data.get("tags") or "")) if t]
    md = scrape.build_markdown(
        recipe, image_ref, tags,
        season=str(data.get("season") or "all"), rating=rating, difficulty=difficulty,
        kid_friendly=str(data.get("kid_friendly")).lower() in ("true", "1", "yes", "on"),
        source_url=scrape.clean_text(data.get("source") or ""),
        extra={k: v for k, v in cookbook_fields(data).items() if v},
    )
    out = recipes_dir / f"{slug}.md"
    out.write_text(md + body_text(data.get("notes")), encoding="utf-8")
    print(f"Written: _recipes/{slug}.md (image images/{image_ref})")
    if args.slug_file:
        Path(args.slug_file).write_text(slug, encoding="utf-8")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract")
    p.add_argument("--out", required=True)
    p.add_argument("images", nargs="*")
    p = sub.add_parser("save")
    p.add_argument("--recipe", required=True)
    p.add_argument("--cover", default="")
    p.add_argument("--slug-file", default="")
    args = parser.parse_args(argv)
    return cmd_extract(args) if args.cmd == "extract" else cmd_save(args)


if __name__ == "__main__":
    sys.exit(main())
