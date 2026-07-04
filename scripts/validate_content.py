#!/usr/bin/env python3
"""Validate CMS content integrity before it reaches the app.

Checks:
  1. version.json, categories.json, and every {slug}.json parse as JSON
  2. Every category in categories.json has a {slug}.json file and a cover image
  3. promptCount in categories.json matches the actual prompt array length
  4. version.json totals (totalCategories, totalPrompts) match reality
  5. Prompt ids are unique within each category
  6. Each prompt has all required fields; category field matches its slug
  7. Every imageUrl points to a file that exists in images/
  8. Images referenced are .webp and under the size cap

Exit code 0 = valid, 1 = one or more errors (all are printed).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_IMAGE_KB = 300
REQUIRED_PROMPT_FIELDS = ["id", "title", "category", "imageUrl", "tool", "tags", "prompt"]

errors = []


def err(msg):
    errors.append(msg)
    print(f"ERROR: {msg}")


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(f"{path.name}: file not found")
    except json.JSONDecodeError as e:
        err(f"{path.name}: invalid JSON — {e}")
    return None


def check_image(rel_path, context):
    if not rel_path:
        err(f"{context}: empty image path")
        return
    p = ROOT / rel_path
    if not p.is_file():
        err(f"{context}: image '{rel_path}' does not exist")
        return
    if p.suffix.lower() != ".webp":
        err(f"{context}: image '{rel_path}' is not .webp")
    size_kb = p.stat().st_size / 1024
    if size_kb > MAX_IMAGE_KB:
        err(f"{context}: image '{rel_path}' is {size_kb:.0f} KB (max {MAX_IMAGE_KB} KB)")


def main():
    version = load_json(ROOT / "version.json")
    categories = load_json(ROOT / "categories.json")
    if version is None or categories is None:
        return finish()

    total_prompts = 0
    for cat in categories:
        slug = cat.get("slug", "")
        if not slug:
            err(f"categories.json: category {cat.get('name')!r} has no slug")
            continue
        check_image(cat.get("image", ""), f"categories.json[{slug}]")

        prompts = load_json(ROOT / f"{slug}.json")
        if prompts is None:
            continue
        if not isinstance(prompts, list):
            err(f"{slug}.json: expected a JSON array")
            continue

        if cat.get("promptCount") != len(prompts):
            err(f"categories.json[{slug}]: promptCount={cat.get('promptCount')} "
                f"but {slug}.json has {len(prompts)} prompts")
        total_prompts += len(prompts)

        seen_ids = set()
        for i, p in enumerate(prompts):
            ctx = f"{slug}.json[{i}]"
            missing = [f for f in REQUIRED_PROMPT_FIELDS if f not in p or p[f] in ("", [], None)]
            if missing:
                err(f"{ctx}: missing/empty fields: {', '.join(missing)}")
            pid = p.get("id")
            if pid in seen_ids:
                err(f"{ctx}: duplicate id {pid}")
            seen_ids.add(pid)
            if p.get("category") != slug:
                err(f"{ctx}: category={p.get('category')!r} does not match slug {slug!r}")
            if "imageUrl" in p:
                check_image(p["imageUrl"], ctx)

    if version.get("totalCategories") != len(categories):
        err(f"version.json: totalCategories={version.get('totalCategories')} "
            f"but categories.json has {len(categories)}")
    if version.get("totalPrompts") != total_prompts:
        err(f"version.json: totalPrompts={version.get('totalPrompts')} "
            f"but actual total is {total_prompts}")
    if not isinstance(version.get("contentVersion"), int):
        err("version.json: contentVersion must be an integer")

    return finish()


def finish():
    if errors:
        print(f"\nValidation FAILED with {len(errors)} error(s).")
        return 1
    print("Validation passed: all content files are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
