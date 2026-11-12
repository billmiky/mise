#!/usr/bin/env python3
"""Check _data/salads.yml, the Salad Maker's slots and saved salads.

Fails on: missing or duplicate slot keys/options, a bad `pick` range, a `recipe:`
that isn't in _recipes/, or a saved salad with no name, a duplicate name, an
unknown slot, or more than one pick in a single-choice slot.

Run: python3 tools/test_salads.py
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "_data" / "salads.yml"


def check(data, recipe_slugs):
    errors = []
    slots = data.get("slots") or []
    if not slots:
        errors.append("no slots")
    keys = set()
    singles = set()
    for i, slot in enumerate(slots):
        key = slot.get("key")
        where = f"slot {key or i}"
        if not key or not slot.get("name"):
            errors.append(f"{where}: needs a key and a name")
        if key in keys:
            errors.append(f"{where}: key used twice")
        keys.add(key)
        if slot.get("single"):
            singles.add(key)
        pick = slot.get("pick", [1, 1])
        if not (isinstance(pick, list) and len(pick) == 2 and all(isinstance(n, int) for n in pick)
                and 0 <= pick[0] <= pick[1]):
            errors.append(f"{where}: pick should be [min, max], got {pick!r}")
        options = slot.get("options") or []
        if not options:
            errors.append(f"{where}: no options")
        elif isinstance(pick, list) and len(pick) == 2 and isinstance(pick[1], int) and pick[1] > len(options):
            errors.append(f"{where}: pick max {pick[1]} is more than its {len(options)} options")
        seen = set()
        for o in options:
            name = str(o.get("name") or "").strip()
            if not name:
                errors.append(f"{where}: an option has no name")
                continue
            if name.lower() in seen:
                errors.append(f"{where}: '{name}' listed twice")
            seen.add(name.lower())
            if o.get("recipe") and o["recipe"] not in recipe_slugs:
                errors.append(f"{where}: '{name}' links to recipe '{o['recipe']}', which isn't in _recipes/")
            buy = o.get("buy")
            if buy is not None and not (isinstance(buy, list) and all(isinstance(b, str) and b.strip() for b in buy)):
                errors.append(f"{where}: '{name}' buy should be a list of items")

    names = set()
    for i, entry in enumerate(data.get("saved") or []):
        name = str(entry.get("name") or "").strip()
        where = f"saved salad '{name or i}'"
        if not name:
            errors.append(f"saved salad {i}: no name")
        if name.lower() in names:
            errors.append(f"{where}: name used twice")
        names.add(name.lower())
        for k, v in entry.items():
            if k == "name":
                continue
            if k not in keys:
                errors.append(f"{where}: unknown slot '{k}'")
            elif not isinstance(v, list):
                errors.append(f"{where}: {k} should be a list")
            elif k in singles and len(v) > 1:
                errors.append(f"{where}: only one {k} allowed")
    return errors


def main():
    data = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    slugs = {p.stem for p in (ROOT / "_recipes").glob("*.md")}
    errors = check(data, slugs)

    # The checker itself catches what it should
    bad = {"slots": [{"key": "d", "name": "D", "single": True, "pick": [1, 1],
                      "options": [{"name": "A", "recipe": "nope"}, {"name": "a"}]}],
           "saved": [{"name": "X", "d": ["A", "a"], "zz": []}, {"name": "x"}]}
    found = "\n".join(check(bad, slugs))
    for expect in ["isn't in _recipes/", "listed twice", "only one d", "unknown slot 'zz'", "name used twice"]:
        assert expect in found, f"checker missed: {expect}\n{found}"

    for e in errors:
        print("ERROR", e)
    print(f"{len(data.get('slots') or [])} slots, {len(data.get('saved') or [])} saved salads")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
