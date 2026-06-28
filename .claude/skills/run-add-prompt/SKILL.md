---
name: run-add-prompt
description: Add a new AI prompt entry with its image to the correct category JSON file and image folder. Use when the user says "add prompt", "new prompt", "add to category", or provides a prompt + image to add.
---

# Add Prompt to Category

This skill adds a new prompt entry to the AI Prompt Book content CMS. The user provides:
- A **prompt** (title, prompt text, tool, tags — or raw text for you to parse)
- An **image** file
- A **category** (or you infer it from the prompt/tags)

All paths below are relative to the repo root: `C:\zMyData\GitHub\ai-prompt-book-content`.

## Existing Categories

| Slug | Name | JSON File | Image Folder |
|------|------|-----------|--------------|
| wallpapers | Wallpapers | wallpapers.json | images/wallpapers/ |
| anime | Anime | anime.json | images/anime/ |
| fantasy | Fantasy | fantasy.json | images/fantasy/ |
| characters | Characters | characters.json | images/characters/ |
| logos | Logos | logos.json | images/logos/ |

## Steps

### 1. Determine the category

Ask the user or infer from prompt content/tags. The category must match a slug in `categories.json`. If the category doesn't exist yet, create it (see "New Category" below).

### 2. Gather prompt details

Required fields for each prompt entry:

```json
{
  "id": <next-integer>,
  "title": "<Short Title>",
  "category": "<slug>",
  "imageUrl": "images/<slug>/<kebab-case-name>.webp",
  "tool": "<Midjourney|Stable Diffusion|DALL-E|Leonardo AI|Firefly>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "prompt": "<the full generation prompt text>"
}
```

- **id**: Read the category JSON, find the max `id`, add 1.
- **title**: Short, descriptive (2-4 words).
- **imageUrl**: `images/{slug}/{kebab-case-title}.webp` — derive from title.
- **tool**: One of: Midjourney, Stable Diffusion, DALL-E, Leonardo AI, Firefly.
- **tags**: 2-3 relevant tags, first tag should match the category slug.
- **prompt**: The full AI image generation prompt. Must be family-friendly.

### 3. Save the image

Copy/move the user-provided image to `images/{category}/{kebab-case-name}.webp`.

If the image is not `.webp`, convert it or save as-is with the `.webp` extension (the app expects `.webp`). If the user provides a path, copy from there. If provided as an attachment, save it directly.

```powershell
Copy-Item "<source-image-path>" "images/<category>/<kebab-case-name>.webp"
```

### 4. Add the entry to the category JSON

Read `{category}.json`, append the new entry, write back with 2-space indentation:

```powershell
# Read, parse, append, write
$json = Get-Content "<category>.json" -Raw | ConvertFrom-Json
# ... append new entry ...
$json | ConvertTo-Json -Depth 10 | Set-Content "<category>.json" -Encoding utf8
```

Or use the Edit tool to insert the new entry before the closing `]`.

### 5. Update categories.json

Increment `promptCount` for the matching category entry.

### 6. Update version.json

- Increment `totalPrompts` by 1.
- Set `lastUpdated` to today's date (YYYY-MM-DD format).
- Increment `contentVersion` by 1.

### 7. Verify

- Confirm the JSON is valid (no trailing commas, proper structure).
- Confirm the image file exists at the expected path.
- Show the user the new entry for confirmation.

## New Category (if needed)

If the prompt doesn't fit any existing category:

1. Create `images/{new-slug}/` folder.
2. Create `{new-slug}.json` with an empty array `[]`, then add the entry.
3. Add a new entry to `categories.json` with the next `id`, a `cover.webp` placeholder note, and `promptCount: 1`.
4. Update `version.json`: increment `totalCategories` and `totalPrompts`.
5. Ask the user to provide a `cover.webp` for the new category.

## Gotchas

- JSON files use 2-space indentation. PowerShell's `ConvertTo-Json` defaults to 2-space, which is correct.
- Image filenames are kebab-case, lowercase, `.webp` extension.
- The `imageUrl` field does NOT have a leading `/` — it's a relative path like `images/anime/foo.webp`.
- The `category` field in each prompt entry must exactly match the slug in `categories.json`.
- All prompts must be family-friendly (Google Play Store policy).
- PowerShell `ConvertTo-Json` wraps arrays in an object if depth is insufficient — always use `-Depth 10`.
- Use `-Encoding utf8` when writing JSON to avoid BOM issues.
