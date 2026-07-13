#!/usr/bin/env python3
"""Local admin panel for the AI Prompt Book CMS...

Run:  python admin/serve.py   → opens http://localhost:8765
Zero-cost: edits the JSON/images in this repo directly; the Publish
button validates content, bumps contentVersion, and git commit+pushes.
"""
import base64
import io
import json
import re
import shutil
import subprocess
import sys
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765
MAX_KB = 290          # keep under the validator's 300 KB cap
MAX_SIDE = 1536


def read_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def write_json(name, data):
    (ROOT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def kebab(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def save_webp(b64data, out_path: Path):
    """Decode base64 image, resize, and compress to webp under MAX_KB."""
    img = Image.open(io.BytesIO(base64.b64decode(b64data.split(",")[-1])))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for q in (85, 75, 65, 50):
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() / 1024 <= MAX_KB:
            break
    out_path.write_bytes(buf.getvalue())
    return buf.tell() // 1024


def recount(slug):
    cats = read_json("categories.json")
    for c in cats:
        if c["slug"] == slug:
            c["promptCount"] = len(read_json(f"{slug}.json"))
    write_json("categories.json", cats)


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, shell=False)
    return r.returncode, (r.stdout + r.stderr).strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (ROOT / "admin" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/images/"):
            p = (ROOT / self.path.lstrip("/")).resolve()
            if p.is_file() and ROOT in p.parents:
                self.send_response(200)
                self.send_header("Content-Type", "image/webp")
                self.end_headers()
                self.wfile.write(p.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == "/api/content":
            cats = read_json("categories.json")
            self._send({
                "version": read_json("version.json"),
                "categories": cats,
                "prompts": {c["slug"]: read_json(f"{c['slug']}.json") for c in cats},
                "gitStatus": run(["git", "status", "--short"])[1],
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # CSRF guard: browsers set Origin on cross-site requests; only
        # accept requests from our own page (or none, e.g. curl).
        origin = self.headers.get("Origin", "")
        if origin and not origin.startswith(("http://localhost", "http://127.0.0.1")):
            self._send({"error": "forbidden origin"}, 403)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            self._send(self._dispatch(self.path, body))
        except Exception as e:
            self._send({"error": str(e)}, 400)

    def _dispatch(self, path, b):
        if path == "/api/prompt/add":
            slug = b["category"]
            prompts = read_json(f"{slug}.json")
            new_id = max((p["id"] for p in prompts), default=0) + 1
            img_rel = f"images/{slug}/{kebab(b['title'])}.webp"
            kb = save_webp(b["imageBase64"], ROOT / img_rel)
            prompts.append({
                "id": new_id, "title": b["title"], "category": slug,
                "imageUrl": img_rel, "tool": b["tool"],
                "tags": b["tags"], "prompt": b["prompt"],
            })
            write_json(f"{slug}.json", prompts)
            recount(slug)
            return {"ok": True, "id": new_id, "imageKb": kb}

        if path == "/api/prompt/update":
            slug = b["category"]
            prompts = read_json(f"{slug}.json")
            for p in prompts:
                if p["id"] == b["id"]:
                    for f in ("title", "tool", "tags", "prompt"):
                        p[f] = b[f]
                    if b.get("imageBase64"):
                        save_webp(b["imageBase64"], ROOT / p["imageUrl"])
            write_json(f"{slug}.json", prompts)
            return {"ok": True}

        if path == "/api/prompt/delete":
            slug = b["category"]
            prompts = read_json(f"{slug}.json")
            victim = next((p for p in prompts if p["id"] == b["id"]), None)
            if victim:
                img = ROOT / victim["imageUrl"]
                if img.is_file():
                    img.unlink()
            prompts = [p for p in prompts if p["id"] != b["id"]]
            write_json(f"{slug}.json", prompts)
            recount(slug)
            return {"ok": True}

        if path == "/api/category/add":
            slug = kebab(b["name"])
            cats = read_json("categories.json")
            if any(c["slug"] == slug for c in cats):
                raise ValueError(f"category '{slug}' already exists")
            img_rel = f"images/{slug}/cover.webp"
            save_webp(b["imageBase64"], ROOT / img_rel)
            cats.append({
                "id": max((c["id"] for c in cats), default=0) + 1,
                "name": b["name"], "slug": slug,
                "image": img_rel, "promptCount": 0,
            })
            write_json("categories.json", cats)
            write_json(f"{slug}.json", [])
            return {"ok": True, "slug": slug}

        if path == "/api/category/update":
            slug = b["slug"]
            cats = read_json("categories.json")
            cat = next((c for c in cats if c["slug"] == slug), None)
            if cat is None:
                raise ValueError(f"category '{slug}' not found")
            if b.get("name"):
                cat["name"] = b["name"]
            if b.get("imageBase64"):
                save_webp(b["imageBase64"], ROOT / cat["image"])
            write_json("categories.json", cats)
            return {"ok": True}

        if path == "/api/category/delete":
            slug = b["slug"]
            cats = read_json("categories.json")
            if not any(c["slug"] == slug for c in cats):
                raise ValueError(f"category '{slug}' not found")
            cats = [c for c in cats if c["slug"] != slug]
            write_json("categories.json", cats)
            (ROOT / f"{slug}.json").unlink(missing_ok=True)
            shutil.rmtree(ROOT / "images" / slug, ignore_errors=True)
            return {"ok": True}

        if path == "/api/publish":
            cats = read_json("categories.json")
            v = read_json("version.json")
            v["contentVersion"] += 1
            v["lastUpdated"] = date.today().isoformat()
            v["totalCategories"] = len(cats)
            v["totalPrompts"] = sum(c["promptCount"] for c in cats)
            write_json("version.json", v)

            code, out = run([sys.executable, "scripts/validate_content.py"])
            if code != 0:
                return {"ok": False, "step": "validate", "output": out}
            for cmd in (["git", "add", "-A"],
                        ["git", "commit", "-m", b.get("message") or f"Content update v{v['contentVersion']}"],
                        ["git", "push"]):
                code, out = run(cmd)
                if code != 0:
                    return {"ok": False, "step": " ".join(cmd[:2]), "output": out}
            return {"ok": True, "version": v["contentVersion"]}

        raise ValueError(f"unknown endpoint {path}")


if __name__ == "__main__":
    print(f"Admin panel: http://localhost:{PORT}  (Ctrl+C to stop)")
    webbrowser.open(f"http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
